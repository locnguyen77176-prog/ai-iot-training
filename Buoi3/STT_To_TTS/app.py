import io
import os
import sys
import time
import base64
import asyncio
import subprocess
import site
import shutil
from contextlib import asynccontextmanager
from typing import Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure CUDA DLLs from torch/lib or system PATH are registered on Windows
def setup_cuda_dlls():
    for sp in site.getsitepackages():
        torch_lib = os.path.join(sp, 'torch', 'lib')
        if os.path.exists(torch_lib):
            try:
                os.add_dll_directory(torch_lib)
            except Exception:
                pass
            os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
            
            cublas11 = os.path.join(torch_lib, 'cublas64_11.dll')
            cublas12 = os.path.join(torch_lib, 'cublas64_12.dll')
            if os.path.exists(cublas11) and not os.path.exists(cublas12):
                try:
                    shutil.copyfile(cublas11, cublas12)
                    print("Đã tự động cấu hình cublas64_12.dll cho faster-whisper GPU!")
                except Exception as e:
                    print("Cảnh báo khi sao chép cublas DLL:", e)

setup_cuda_dlls()



from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import torch
import ffmpeg
import edge_tts
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Low-latency tuning
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-JennyNeural")

# Global Whisper Model Reference
whisper_model: Optional[WhisperModel] = None
device_name: str = "cpu"
compute_type: str = "float32"
gemini_client_cache: dict[str, genai.Client] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global whisper_model, device_name, compute_type
    print("=== Khởi tạo ứng dụng & nạp Whisper Model... ===")
    start_init = time.perf_counter()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA không khả dụng. Dịch vụ STT Whisper này bắt buộc chạy trên GPU để tối ưu latency.")

    device_name = "cuda"
    compute_type = "float16"
    print(f"Sử dụng thiết bị: {device_name} (compute_type: {compute_type}, model: {WHISPER_MODEL_SIZE})")

    try:
        whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=device_name, compute_type=compute_type)
        print(f"Đã nạp thành công Whisper Model '{WHISPER_MODEL_SIZE}' trên GPU trong {time.perf_counter() - start_init:.2f}s!")
    except Exception as e:
        raise RuntimeError(f"Không thể khởi tạo Whisper model '{WHISPER_MODEL_SIZE}' trên GPU: {e}") from e

    yield
    print("=== Đóng ứng dụng ===")

app = FastAPI(
    title="Real-time Vi-En Voice & Text Translation",
    description="FastAPI + GPU Whisper STT + Gemini 1.5 Flash + Edge-TTS",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TextTranslateRequest(BaseModel):
    text: str
    api_key: Optional[str] = None

def convert_audio_to_wav(input_bytes: bytes) -> bytes:
    """
    Chuyển đổi dữ liệu âm thanh từ WebM/WAV/OGG sang chuẩn WAV 16kHz 16-bit Mono PCM bằng FFmpeg
    hoàn toàn trong bộ nhớ (Memory Stream).
    """
    try:
        process = (
            ffmpeg
            .input('pipe:0')
            .output('pipe:1', format='wav', ac=1, ar='16000', acodec='pcm_s16le')
            .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
        )
        out, err = process.communicate(input=input_bytes)
        if process.returncode != 0:
            raise RuntimeError(f"Lỗi FFmpeg: {err.decode('utf-8', errors='ignore')}")
        return out
    except Exception as e:
        # Fallback sử dụng trực tiếp subprocess nếu ffmpeg-python gặp sự cố
        cmd = [
            'ffmpeg', '-y', '-i', 'pipe:0',
            '-f', 'wav', '-ac', '1', '-ar', '16000', '-acodec', 'pcm_s16le', 'pipe:1'
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate(input=input_bytes)
        if proc.returncode != 0:
            raise RuntimeError(f"Lỗi FFmpeg subprocess: {err.decode('utf-8', errors='ignore')}")
        return out

def run_whisper_stt(wav_bytes: bytes) -> str:
    """
    Thực hiện Speech-to-Text với faster-whisper GPU
    """
    global whisper_model
    if whisper_model is None:
        raise RuntimeError("Whisper model chưa được khởi tạo!")

    audio_stream = io.BytesIO(wav_bytes)
    segments, _ = whisper_model.transcribe(
        audio_stream,
        language="vi",
        beam_size=1,
        best_of=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        without_timestamps=True,
    )

    text_pieces = [segment.text.strip() for segment in segments]
    full_text = " ".join(piece for piece in text_pieces if piece).strip()
    return full_text

def get_gemini_client(api_key: str) -> genai.Client:
    global gemini_client_cache
    if api_key not in gemini_client_cache:
        gemini_client_cache[api_key] = genai.Client(api_key=api_key)
    return gemini_client_cache[api_key]

async def translate_vi_to_en(text: str, api_key: Optional[str] = None) -> str:
    """
    Dịch Tiếng Việt sang Tiếng Anh bằng Gemini API
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gemini API Key chưa được cung cấp. Vui lòng nhập API Key trên giao diện web hoặc cấu hình GEMINI_API_KEY."
        )

    try:
        client = get_gemini_client(key)
        prompt = f"Dịch tiếng Việt sang tiếng Anh, giữ nguyên ý nghĩa và trả về chỉ câu dịch:\n{text}"

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a professional translator. "
                    "Translate Vietnamese to natural English. "
                    "Return only the translated sentence."
                ),
                temperature=0.1,
                max_output_tokens=128,
            )
        )
        translated = response.text.strip() if getattr(response, "text", None) else ""
        return translated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi Gemini Translation API: {str(e)}"
        )

async def tts_en_to_base64(text: str, voice: Optional[str] = None) -> str:
    """
    Chuyển văn bản Tiếng Anh thành giọng nói trực tiếp trong bộ nhớ bằng edge-tts
    """
    if not text:
        return ""
    selected_voice = voice or EDGE_TTS_VOICE
    try:
        communicate = edge_tts.Communicate(text, selected_voice)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        audio_bytes = audio_stream.getvalue()
        return base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        print(f"Cảnh báo Edge-TTS: {e}")
        return ""

@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "cuda_available": torch.cuda.is_available(),
        "device": device_name,
        "compute_type": compute_type,
        "whisper_loaded": whisper_model is not None
    }

@app.post("/api/text-translate")
async def text_translate(req: TextTranslateRequest, x_api_key: Optional[str] = Header(None)):
    t_start = time.perf_counter()
    api_key = req.api_key or x_api_key or os.environ.get("GEMINI_API_KEY")
    
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản cần dịch không được để trống.")
    
    # 1. Dịch văn bản
    t_trans_start = time.perf_counter()
    en_translation = await translate_vi_to_en(req.text, api_key=api_key)
    t_trans = time.perf_counter() - t_trans_start
    
    # 2. TTS
    t_tts_start = time.perf_counter()
    audio_b64 = await tts_en_to_base64(en_translation)
    t_tts = time.perf_counter() - t_tts_start
    
    t_total = time.perf_counter() - t_start
    
    return {
        "translation": en_translation,
        "audio_b64": f"data:audio/mp3;base64,{audio_b64}" if audio_b64 else "",
        "latency": {
            "translation": round(t_trans, 3),
            "tts": round(t_tts, 3),
            "total": round(t_total, 3)
        }
    }

@app.post("/api/voice-translate")
async def voice_translate(
    audio: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    x_api_key: Optional[str] = Header(None)
):
    t_start = time.perf_counter()
    resolved_api_key = api_key or x_api_key or os.environ.get("GEMINI_API_KEY")
    
    # Read audio bytes
    raw_audio_bytes = await audio.read()
    if not raw_audio_bytes:
        raise HTTPException(status_code=400, detail="File âm thanh rỗng.")
    
    # 1. Standardize Audio via FFmpeg to 16kHz WAV
    try:
        wav_bytes = await asyncio.to_thread(convert_audio_to_wav, raw_audio_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể xử lý file âm thanh: {str(e)}")
    
    # 2. Speech-to-Text (faster-whisper GPU)
    t_stt_start = time.perf_counter()
    vi_text = await asyncio.to_thread(run_whisper_stt, wav_bytes)
    t_stt = time.perf_counter() - t_stt_start
    
    if not vi_text.strip():
        return {
            "stt_text": "",
            "translation": "",
            "audio_b64": "",
            "source_audio_b64": f"data:audio/webm;base64,{base64.b64encode(raw_audio_bytes).decode('utf-8')}",
            "warning": "Không nhận diện được giọng nói tiếng Việt trong file ghi âm.",
            "latency": {
                "stt": round(t_stt, 3),
                "translation": 0.0,
                "tts": 0.0,
                "total": round(time.perf_counter() - t_start, 3)
            }
        }
    
    # 3. Gemini Translation
    t_trans_start = time.perf_counter()
    en_translation = await translate_vi_to_en(vi_text, api_key=resolved_api_key)
    t_trans = time.perf_counter() - t_trans_start
    
    # 4. Edge-TTS
    t_tts_start = time.perf_counter()
    audio_b64 = await tts_en_to_base64(en_translation)
    t_tts = time.perf_counter() - t_tts_start
    
    t_total = time.perf_counter() - t_start
    
    return {
        "stt_text": vi_text,
        "translation": en_translation,
        "audio_b64": f"data:audio/mp3;base64,{audio_b64}" if audio_b64 else "",
        "source_audio_b64": f"data:audio/webm;base64,{base64.b64encode(raw_audio_bytes).decode('utf-8')}",
        "latency": {
            "stt": round(t_stt, 3),
            "translation": round(t_trans, 3),
            "tts": round(t_tts, 3),
            "total": round(t_total, 3)
        }
    }

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Chưa tìm thấy file index.html</h1>"
