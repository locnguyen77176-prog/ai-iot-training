import os
from dotenv import load_dotenv

load_dotenv()

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "medium")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16")

# Local Translation (Qwen2.5-1.5B CTranslate2 Engine - 100% Offline)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRANSLATION_MODEL_DIR = os.getenv(
    "TRANSLATION_MODEL_DIR",
    os.path.join(BASE_DIR, "models", "translation", "qwen_ct2")
)
TRANSLATION_DEVICE = os.getenv("TRANSLATION_DEVICE", "cuda")
TRANSLATION_COMPUTE_TYPE = os.getenv("TRANSLATION_COMPUTE_TYPE", "int8")

# Piper Local TTS Configurations
PIPER_MODEL_DIR = os.getenv("PIPER_MODEL_DIR", os.path.join(BASE_DIR, "models", "tts"))
PIPER_VOICE_VI = os.getenv("PIPER_VOICE_VI", "vi_VN-vais1000-medium.onnx")
PIPER_VOICE_EN = os.getenv("PIPER_VOICE_EN", "en_US-lessac-medium.onnx")
