"""
download_models.py — Script tải trước toàn bộ Model AI Local (Whisper STT & Piper TTS).
"""

import os
import sys
import urllib.request
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PIPER_MODEL_DIR = os.path.join(BASE_DIR, "models", "tts")

PIPER_FILES = {
    "vi_VN-vais1000-medium.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx",
    "vi_VN-vais1000-medium.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json",
    "en_US-lessac-medium.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en_US-lessac-medium.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
}


def download_all():
    print("==================================================")
    print("  BẮT ĐẦU TẢI TRƯỚC TOÀN BỘ MODEL AI LOCAL")
    print("==================================================\n")

    # 1. Tải Faster-Whisper Model
    whisper_size = os.getenv("WHISPER_MODEL_SIZE", "large-v3-turbo")
    print(f"[1/2] Tải Faster-Whisper Model ('{whisper_size}')...")
    try:
        from faster_whisper import WhisperModel
        _ = WhisperModel(whisper_size, device="cpu", compute_type="int8")
        print(f"[OK] Đã tải xong Faster-Whisper '{whisper_size}'!\n")
    except Exception as e:
        print(f"[ERROR] Lỗi tải Whisper model: {e}\n")

    # 2. Tải Piper Local TTS Models (Tiếng Việt + Tiếng Anh)
    print("[2/2] Tải Piper Local TTS Models (ONNX)...")
    os.makedirs(PIPER_MODEL_DIR, exist_ok=True)
    for fname, url in PIPER_FILES.items():
        fpath = os.path.join(PIPER_MODEL_DIR, fname)
        if os.path.exists(fpath):
            print(f"  - [ĐÃ CÓ] {fname} ({os.path.getsize(fpath)} bytes)")
        else:
            print(f"  - Đang tải {fname}...")
            try:
                urllib.request.urlretrieve(url, fpath)
                print(f"  - [OK] {fname} ({os.path.getsize(fpath)} bytes)")
            except Exception as e:
                print(f"  - [ERROR] Lỗi tải {fname}: {e}")

    print("\n==================================================")
    print("  HOÀN TẤT TẢI MODEL! BẠN CÓ THỂ CHẠY: python run.py")
    print("==================================================")


if __name__ == "__main__":
    download_all()
