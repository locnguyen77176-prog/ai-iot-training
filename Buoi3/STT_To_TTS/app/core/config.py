import os
from dotenv import load_dotenv

load_dotenv()

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "large-v3-turbo")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Piper Local TTS Configurations
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PIPER_MODEL_DIR = os.getenv("PIPER_MODEL_DIR", os.path.join(BASE_DIR, "models", "tts"))
PIPER_VOICE_VI = os.getenv("PIPER_VOICE_VI", "vi_VN-vais1000-medium.onnx")
PIPER_VOICE_EN = os.getenv("PIPER_VOICE_EN", "en_US-lessac-medium.onnx")
