import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.cuda_setup import setup_cuda_dlls
setup_cuda_dlls()

from app.services.stt import init_whisper_model
from app.services.translation import init_gemini_translation
from app.services.tts import init_piper_tts
from app.api.routes import router
from app.api.websocket_routes import websocket_router

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== [1/3] Nạp Faster-Whisper Model trên GPU & GPU Warmup... ===")
    init_whisper_model()
    print("=== [2/3] Mở kết nối & Warmup Gemini API... ===")
    init_gemini_translation()
    print("=== [3/3] Nạp Piper Local TTS Engine & Warmup... ===")
    init_piper_tts()
    print("=== Hệ thống đã sẵn sàng xử lý yêu cầu! ===")
    yield
    print("=== Đóng ứng dụng ===")

app = FastAPI(
    title="Real-time Vi-En Voice & Text Translation",
    description="FastAPI + GPU Whisper STT + Gemini 3.5 Flash Lite + Piper Local TTS",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(websocket_router)

