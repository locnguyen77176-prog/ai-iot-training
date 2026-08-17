import os
import time
import base64
import asyncio
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, status
from fastapi.responses import HTMLResponse

from app.models.schemas import TextTranslateRequest
from app.services.audio import convert_audio_to_wav
from app.services.stt import run_whisper_stt, get_stt_info
from app.services.translation import translate_text
from app.services.tts import tts_to_base64

router = APIRouter()

@router.get("/api/health")
async def health_check():
    stt_info = get_stt_info()
    return {
        "status": "online",
        **stt_info
    }

@router.post("/api/text-translate")
async def text_translate(req: TextTranslateRequest, x_api_key: Optional[str] = Header(None)):
    t_start = time.perf_counter()
    api_key = req.api_key or x_api_key or os.environ.get("GEMINI_API_KEY")
    
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản cần dịch không được để trống.")
    
    # 1. Dịch văn bản
    t_trans_start = time.perf_counter()
    translation = await translate_text(req.text, source_lang=req.source_lang, target_lang=req.target_lang, api_key=api_key)
    t_trans = time.perf_counter() - t_trans_start
    
    # 2. TTS
    t_tts_start = time.perf_counter()
    audio_b64 = await tts_to_base64(translation, target_lang=req.target_lang)
    t_tts = time.perf_counter() - t_tts_start
    
    t_total = time.perf_counter() - t_start
    
    return {
        "translation": translation,
        "audio_b64": f"data:audio/mp3;base64,{audio_b64}" if audio_b64 else "",
        "latency": {
            "translation": round(t_trans, 3),
            "tts": round(t_tts, 3),
            "total": round(t_total, 3)
        }
    }

@router.post("/api/voice-translate")
async def voice_translate(
    audio: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    source_lang: str = Form("vi"),
    target_lang: str = Form("en"),
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
    stt_text = await asyncio.to_thread(run_whisper_stt, wav_bytes, language=source_lang)
    t_stt = time.perf_counter() - t_stt_start
    
    if not stt_text.strip():
        return {
            "stt_text": "",
            "translation": "",
            "audio_b64": "",
            "source_audio_b64": f"data:audio/webm;base64,{base64.b64encode(raw_audio_bytes).decode('utf-8')}",
            "warning": "Không nhận diện được giọng nói trong file ghi âm.",
            "latency": {
                "stt": round(t_stt, 3),
                "translation": 0.0,
                "tts": 0.0,
                "total": round(time.perf_counter() - t_start, 3)
            }
        }
    
    # 3. Gemini Translation
    t_trans_start = time.perf_counter()
    translation = await translate_text(stt_text, source_lang=source_lang, target_lang=target_lang, api_key=resolved_api_key)
    t_trans = time.perf_counter() - t_trans_start

    # 4. Edge-TTS + encode source audio song song nhau
    # [OPT-5] source_audio_b64 encoding chạy đồng thời với TTS thay vì tuần tự
    t_tts_start = time.perf_counter()
    audio_b64, source_b64 = await asyncio.gather(
        tts_to_base64(translation, target_lang=target_lang),
        asyncio.to_thread(lambda: base64.b64encode(raw_audio_bytes).decode('utf-8')),
    )
    t_tts = time.perf_counter() - t_tts_start

    t_total = time.perf_counter() - t_start

    return {
        "stt_text": stt_text,
        "translation": translation,
        "audio_b64": f"data:audio/mp3;base64,{audio_b64}" if audio_b64 else "",
        "source_audio_b64": f"data:audio/webm;base64,{source_b64}",
        "latency": {
            "stt": round(t_stt, 3),
            "translation": round(t_trans, 3),
            "tts": round(t_tts, 3),
            "total": round(t_total, 3)
        }
    }

@router.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "..", "..", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Chưa tìm thấy file index.html</h1>"
