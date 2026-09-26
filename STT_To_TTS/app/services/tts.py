import os
import sys
import re
import io
import wave
import struct
import base64
import asyncio
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from piper.voice import PiperVoice
from app.core.config import (
    PIPER_MODEL_DIR,
    PIPER_VOICE_VI,
    PIPER_VOICE_EN
)

# In-memory cache: key=(text, lang) -> raw WAV bytes
_TTS_CACHE: dict = {}
_TTS_CACHE_LOCK = asyncio.Lock()

# Loaded Piper Voice instances (singleton, loaded once at startup)
_VOICE_VI: Optional[PiperVoice] = None
_VOICE_EN: Optional[PiperVoice] = None

# Thread pool cố định để chạy Piper ONNX song song (không tạo thread mới mỗi request)
_TTS_EXECUTOR = ThreadPoolExecutor(max_workers=6, thread_name_prefix="piper-tts")

# Model URLs for auto-download if missing
MODEL_DOWNLOAD_URLS = {
    "vi_VN-vais1000-medium.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx",
    "vi_VN-vais1000-medium.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json",
    "en_US-lessac-medium.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en_US-lessac-medium.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
}

# Sentence splitter: split on . ! ? and newlines while keeping the delimiter
_SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[.!?。！？])\s+')


def _ensure_model_files(model_name: str) -> str:
    """Kiểm tra và tự động tải file ONNX + JSON nếu chưa có."""
    os.makedirs(PIPER_MODEL_DIR, exist_ok=True)
    model_path = os.path.join(PIPER_MODEL_DIR, model_name)
    config_name = f"{model_name}.json"
    config_path = os.path.join(PIPER_MODEL_DIR, config_name)

    for fname, fpath in [(model_name, model_path), (config_name, config_path)]:
        if not os.path.exists(fpath):
            url = MODEL_DOWNLOAD_URLS.get(fname)
            if url:
                print(f"[TTS] Downloading {fname}...")
                urllib.request.urlretrieve(url, fpath)
                print(f"[TTS] Done {fname} ({os.path.getsize(fpath)} bytes).")
            else:
                raise FileNotFoundError(f"Model file not found: {fpath}")

    return model_path


def init_piper_tts():
    """Nạp 2 model giọng đọc vào RAM và Warmup (loại bỏ trễ lần đầu)."""
    global _VOICE_VI, _VOICE_EN

    print("=== Initializing Piper Local TTS Engine (ONNX Runtime)... ===")

    try:
        vi_path = _ensure_model_files(PIPER_VOICE_VI)
        _VOICE_VI = PiperVoice.load(vi_path, use_cuda=False)
        # Warmup: run 3 short sentences to populate ONNX JIT cache
        for warmup_text in ["Khởi động.", "Xin chào.", "Đây là thử nghiệm."]:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                _VOICE_VI.synthesize_wav(warmup_text, wf)
        print(f"[TTS] Vietnamese voice loaded & warmed up ({PIPER_VOICE_VI})")
    except Exception as e:
        print(f"[TTS] Warning: Failed to load Vietnamese TTS model: {e}")

    try:
        en_path = _ensure_model_files(PIPER_VOICE_EN)
        _VOICE_EN = PiperVoice.load(en_path, use_cuda=False)
        for warmup_text in ["Startup.", "Hello.", "This is a test."]:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                _VOICE_EN.synthesize_wav(warmup_text, wf)
        print(f"[TTS] English voice loaded & warmed up ({PIPER_VOICE_EN})")
    except Exception as e:
        print(f"[TTS] Warning: Failed to load English TTS model: {e}")


def _split_into_sentences(text: str) -> List[str]:
    """
    Tách văn bản thành danh sách câu ngắn để xử lý song song.
    Ưu tiên tách theo . ! ?, giới hạn tối đa 150 ký tự mỗi phần.
    """
    # Tách theo dấu câu
    parts = _SENTENCE_SPLIT_PATTERN.split(text.strip())
    sentences = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Nếu câu vẫn quá dài (> 150 chars), tách tiếp theo dấu phẩy
        if len(part) > 150:
            sub_parts = re.split(r'(?<=[,;])\s+', part)
            sentences.extend([s.strip() for s in sub_parts if s.strip()])
        else:
            sentences.append(part)
    return sentences if sentences else [text.strip()]


def _synthesize_sentence(text: str, lang: str) -> bytes:
    """Tổng hợp một câu duy nhất, trả về raw PCM audio data (không có WAV header)."""
    voice = _VOICE_VI if lang == "vi" else _VOICE_EN
    if voice is None:
        return b""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf)
    # Trả về toàn bộ WAV (bao gồm header) cho từng chunk
    return buf.getvalue()


def _merge_wav_chunks(wav_chunks: List[bytes]) -> bytes:
    """
    Gộp nhiều WAV byte-string thành một file WAV hoàn chỉnh.
    Giữ nguyên thông số (samplerate, channels, sampwidth) từ chunk đầu tiên.
    """
    if not wav_chunks:
        return b""
    if len(wav_chunks) == 1:
        return wav_chunks[0]

    # Đọc thông số WAV từ chunk đầu tiên
    first = wave.open(io.BytesIO(wav_chunks[0]))
    nchannels = first.getnchannels()
    sampwidth = first.getsampwidth()
    framerate = first.getframerate()
    first.close()

    # Gộp raw audio frames
    all_frames = bytearray()
    for chunk in wav_chunks:
        try:
            wf = wave.open(io.BytesIO(chunk))
            all_frames.extend(wf.readframes(wf.getnframes()))
            wf.close()
        except Exception:
            continue

    # Tạo WAV output
    out_buf = io.BytesIO()
    with wave.open(out_buf, "wb") as out_wf:
        out_wf.setnchannels(nchannels)
        out_wf.setsampwidth(sampwidth)
        out_wf.setframerate(framerate)
        out_wf.writeframes(bytes(all_frames))
    return out_buf.getvalue()


async def tts_stream_chunks(
    text: str,
    target_lang: str = "en",
    voice: Optional[str] = None
) -> Tuple[str, List[str]]:
    """
    Tổng hợp âm thanh Offline cực nhanh bằng Piper TTS + Parallel Sentence Processing:
    1. Tách văn bản thành câu ngắn (< 150 chars mỗi câu)
    2. Gửi tất cả câu vào ThreadPoolExecutor để xử lý song song
    3. Gộp kết quả thành một file WAV liền mạch
    4. Cache kết quả vào RAM để tái sử dụng tức thì
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        return "", []

    cache_key = (cleaned_text, target_lang)

    # 1. Cache hit
    async with _TTS_CACHE_LOCK:
        if cache_key in _TTS_CACHE:
            b64 = base64.b64encode(_TTS_CACHE[cache_key]).decode('utf-8')
            return b64, [b64]

    lang = "vi" if target_lang == "vi" else "en"

    # 2. Tách câu và xử lý song song
    sentences = _split_into_sentences(cleaned_text)

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(_TTS_EXECUTOR, _synthesize_sentence, sent, lang)
        for sent in sentences
    ]
    wav_chunks = await asyncio.gather(*futures)
    wav_chunks = [c for c in wav_chunks if c]

    if not wav_chunks:
        return "", []

    # 3. Gộp toàn bộ câu thành một file WAV
    audio_bytes = await asyncio.to_thread(_merge_wav_chunks, list(wav_chunks))

    if not audio_bytes:
        return "", []

    # 4. Lưu cache
    async with _TTS_CACHE_LOCK:
        if len(_TTS_CACHE) > 300:
            _TTS_CACHE.clear()
        _TTS_CACHE[cache_key] = audio_bytes

    b64 = base64.b64encode(audio_bytes).decode('utf-8')
    return b64, [b64]
