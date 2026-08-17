import io
import base64
from typing import Optional
import edge_tts
from app.core.config import EDGE_TTS_VOICE_EN, EDGE_TTS_VOICE_VI

async def tts_to_base64(text: str, target_lang: str = "en", voice: Optional[str] = None) -> str:
    """
    Chuyển văn bản thành giọng nói trực tiếp trong bộ nhớ bằng edge-tts
    """
    if not text:
        return ""
    if voice:
        selected_voice = voice
    else:
        selected_voice = EDGE_TTS_VOICE_VI if target_lang == "vi" else EDGE_TTS_VOICE_EN

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
