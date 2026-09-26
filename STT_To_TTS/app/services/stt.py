import io
import time
import torch
from faster_whisper import WhisperModel
from app.core.config import WHISPER_MODEL_SIZE, WHISPER_COMPUTE_TYPE

whisper_model = None
device_name = "cpu"
compute_type = "float32"


def init_whisper_model():
    global whisper_model, device_name, compute_type

    if torch.cuda.is_available():
        device_name = "cuda"
        compute_type = WHISPER_COMPUTE_TYPE
        print(f"Sử dụng thiết bị: {device_name} (compute_type: {compute_type}, model: {WHISPER_MODEL_SIZE})")
    else:
        device_name = "cpu"
        compute_type = "int8"
        print(f"CUDA không khả dụng. Chuyển sang sử dụng CPU (compute_type: {compute_type}, model: {WHISPER_MODEL_SIZE})")

    try:
        start_init = time.perf_counter()
        try:
            whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=device_name, compute_type=compute_type)
        except Exception as load_err:
            if device_name == "cuda" and compute_type != "int8":
                print(f"[STT Warning] Nạp với compute_type={compute_type} thất bại ({load_err}), thử lại với 'int8'...")
                compute_type = "int8"
                whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=device_name, compute_type=compute_type)
            else:
                raise load_err

        print(f"Đã nạp thành công Whisper Model '{WHISPER_MODEL_SIZE}' trên {device_name} ({compute_type}) trong {time.perf_counter() - start_init:.2f}s!")

        # Warmup CUDA GPU context & cuDNN memory allocator
        try:
            import wave, struct
            dummy_buf = io.BytesIO()
            with wave.open(dummy_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(struct.pack("<" + "h" * 8000, *([0] * 8000)))
            _ = list(whisper_model.transcribe(io.BytesIO(dummy_buf.getvalue()), beam_size=1)[0])
            print(f"[STT] Whisper GPU Model '{WHISPER_MODEL_SIZE}' ({compute_type}) đã được Warmup thành công (CUDA Ready)!")
        except Exception as wu_err:
            print(f"[STT] Warning GPU Warmup: {wu_err}")

    except Exception as e:
        raise RuntimeError(f"Không thể khởi tạo Whisper model '{WHISPER_MODEL_SIZE}': {e}") from e


def get_stt_info():
    return {
        "cuda_available": torch.cuda.is_available(),
        "device": device_name,
        "compute_type": compute_type,
        "whisper_loaded": whisper_model is not None,
    }


VI_CONTEXT_PROMPT = "Hội thoại tiếng Việt chuẩn, rõ ràng: Nguyễn Văn Lộc, Đại học Công nghiệp Hà Nội, HaUI, IoT, IT."
EN_CONTEXT_PROMPT = "Clear natural English conversation with proper punctuation and capitalization."


def run_whisper_stt(wav_bytes: bytes, language: str = "vi") -> str:
    """Nhận diện giọng nói bằng Faster-Whisper GPU (beam_size=1, Greedy Search, Fast Decode)."""
    global whisper_model
    if whisper_model is None:
        raise RuntimeError("Whisper model chưa được khởi tạo!")

    audio_stream = io.BytesIO(wav_bytes)
    lang = language if language in ("vi", "en") else "vi"
    prompt = VI_CONTEXT_PROMPT if lang == "vi" else EN_CONTEXT_PROMPT

    # beam_size=1, temperature=(0.0,) khóa chặt không cho fallback nhiệt độ, vad_filter bảo vệ chống nhiễu
    segments, _ = whisper_model.transcribe(
        audio_stream,
        language=lang,
        beam_size=1,
        best_of=1,
        temperature=(0.0,),
        condition_on_previous_text=False,
        initial_prompt=prompt,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=200, speech_pad_ms=50),
        without_timestamps=True,
    )

    text_pieces = [segment.text.strip() for segment in segments]
    return " ".join(piece for piece in text_pieces if piece).strip()
