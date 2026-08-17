import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# This needs to run before importing other things that might load torch, but we can do it here.
from app.core.cuda_setup import setup_cuda_dlls
setup_cuda_dlls()

from app.services.stt import init_whisper_model
from app.api.routes import router

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== Khởi tạo ứng dụng & nạp Whisper Model... ===")
    init_whisper_model()
    yield
    print("=== Đóng ứng dụng ===")

app = FastAPI(
    title="Real-time Vi-En Voice & Text Translation",
    description="FastAPI + GPU Whisper STT + Gemini 1.5 Flash + Edge-TTS",
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
