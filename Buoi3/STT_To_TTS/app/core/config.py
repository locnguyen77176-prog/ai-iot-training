import os
from dotenv import load_dotenv

load_dotenv()

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
EDGE_TTS_VOICE_EN = os.getenv("EDGE_TTS_VOICE_EN", "en-US-JennyNeural")
EDGE_TTS_VOICE_VI = os.getenv("EDGE_TTS_VOICE_VI", "vi-VN-HoaiMyNeural")
