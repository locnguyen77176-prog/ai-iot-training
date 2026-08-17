import io
import time
import torch
from faster_whisper import WhisperModel
from app.core.config import WHISPER_MODEL_SIZE

whisper_model = None
device_name = "cpu"
compute_type = "float32"

def init_whisper_model():
    global whisper_model, device_name, compute_type
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA không khả dụng. Dịch vụ STT Whisper này bắt buộc chạy trên GPU để tối ưu latency.")

    device_name = "cuda"
    compute_type = "float16"
    print(f"Sử dụng thiết bị: {device_name} (compute_type: {compute_type}, model: {WHISPER_MODEL_SIZE})")

    try:
        start_init = time.perf_counter()
        whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=device_name, compute_type=compute_type)
        print(f"Đã nạp thành công Whisper Model '{WHISPER_MODEL_SIZE}' trên GPU trong {time.perf_counter() - start_init:.2f}s!")
    except Exception as e:
        raise RuntimeError(f"Không thể khởi tạo Whisper model '{WHISPER_MODEL_SIZE}' trên GPU: {e}") from e

def get_stt_info():
    return {
        "cuda_available": torch.cuda.is_available(),
        "device": device_name,
        "compute_type": compute_type,
        "whisper_loaded": whisper_model is not None
    }

def run_whisper_stt(wav_bytes: bytes, language: str = "vi") -> str:
    """
    Thực hiện Speech-to-Text với faster-whisper GPU
    """
    global whisper_model
    if whisper_model is None:
        raise RuntimeError("Whisper model chưa được khởi tạo!")

    audio_stream = io.BytesIO(wav_bytes)
    segments, _ = whisper_model.transcribe(
        audio_stream,
        language=language if language in ("vi", "en") else "vi",
        beam_size=1,
        best_of=1,
        vad_filter=True,
        # [OPT-2] Giảm 500→300ms: Whisper không cần đợi lâu khi phát hiện im lặng
        # giúp giảm latency ~100-200ms đặc biệt với câu nói ngắn
        vad_parameters=dict(min_silence_duration_ms=300),
        without_timestamps=True,
    )

    text_pieces = [segment.text.strip() for segment in segments]
    full_text = " ".join(piece for piece in text_pieces if piece).strip()
    return full_text
