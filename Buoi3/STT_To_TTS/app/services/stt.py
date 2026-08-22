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

    if torch.cuda.is_available():
        device_name = "cuda"
        compute_type = "float16"
        print(f"Sử dụng thiết bị: {device_name} (compute_type: {compute_type}, model: {WHISPER_MODEL_SIZE})")
    else:
        device_name = "cpu"
        compute_type = "float32"
        print(f"CUDA không khả dụng. Chuyển sang sử dụng CPU (compute_type: {compute_type}, model: {WHISPER_MODEL_SIZE})")

    try:
        start_init = time.perf_counter()
        whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=device_name, compute_type=compute_type)
        print(f"Đã nạp thành công Whisper Model '{WHISPER_MODEL_SIZE}' trên {device_name} trong {time.perf_counter() - start_init:.2f}s!")
    except Exception as e:
        raise RuntimeError(f"Không thể khởi tạo Whisper model '{WHISPER_MODEL_SIZE}': {e}") from e


def get_stt_info():
    return {
        "cuda_available": torch.cuda.is_available(),
        "device": device_name,
        "compute_type": compute_type,
        "whisper_loaded": whisper_model is not None,
    }


VI_CONTEXT_PROMPT = (
    "Đây là đoạn hội thoại tiếng Việt chuẩn, rõ ràng, đúng chính tả và có đầy đủ dấu câu. "
    "Bao gồm các danh từ riêng và từ khóa chuyên ngành: Nguyễn Văn Lộc, Đại học Công nghiệp Hà Nội, HaUI, "
    "công nghệ kỹ thuật máy tính, công nghệ thông tin, lập trình nhúng, vi điều khiển, IoT, "
    "phần cứng, phần mềm, vi xử lý, kỹ sư, chuyên viên, định hướng phát triển."
)

EN_CONTEXT_PROMPT = "This is a clear, natural English conversation with proper punctuation, technical terms, and capitalization."


def run_whisper_stt(wav_bytes: bytes, language: str = "vi") -> str:
    """Nhận diện giọng nói bằng Faster-Whisper GPU (beam_size=1, Greedy Search)."""
    global whisper_model
    if whisper_model is None:
        raise RuntimeError("Whisper model chưa được khởi tạo!")

    audio_stream = io.BytesIO(wav_bytes)
    lang = language if language in ("vi", "en") else "vi"
    prompt = VI_CONTEXT_PROMPT if lang == "vi" else EN_CONTEXT_PROMPT

    # beam_size=1 (Greedy search) tăng tốc ~2.5x so với beam_size=5 trên GPU
    segments, _ = whisper_model.transcribe(
        audio_stream,
        language=lang,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=prompt,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
        without_timestamps=True,
    )

    text_pieces = [segment.text.strip() for segment in segments]
    return " ".join(piece for piece in text_pieces if piece).strip()
