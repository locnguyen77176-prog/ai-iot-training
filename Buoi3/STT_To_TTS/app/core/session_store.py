import io
import wave
import asyncio
from typing import Dict, List, Optional


class SessionAudioStore:
    """
    In-memory pre-buffered RAM session store.
    Stores pre-synthesized WAV chunks and accumulated STT/NMT text per active WebSocket session.
    """
    def __init__(self):
        self._store: Dict[str, List[bytes]] = {}
        self._stt_store: Dict[str, List[str]] = {}
        self._text_store: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()

    async def init_session(self, session_id: str):
        async with self._lock:
            self._store[session_id] = []
            self._stt_store[session_id] = []
            self._text_store[session_id] = []

    async def add_stt_text(self, session_id: str, stt_text: str):
        if not stt_text:
            return
        async with self._lock:
            if session_id not in self._stt_store:
                self._stt_store[session_id] = []
            self._stt_store[session_id].append(stt_text.strip())

    async def add_wav_chunk(self, session_id: str, wav_bytes: bytes, translation_text: str):
        if not wav_bytes:
            return
        async with self._lock:
            if session_id not in self._store:
                self._store[session_id] = []
                self._text_store[session_id] = []
            self._store[session_id].append(wav_bytes)
            if translation_text:
                self._text_store[session_id].append(translation_text.strip())

    async def get_full_stt(self, session_id: str) -> str:
        async with self._lock:
            texts = self._stt_store.get(session_id, [])
            return " ".join(texts).strip()

    async def get_merged_audio(self, session_id: str) -> Optional[bytes]:
        async with self._lock:
            chunks = self._store.get(session_id, [])
            if not chunks:
                return None
            return self._merge_wav_list(chunks)

    async def get_full_translation(self, session_id: str) -> str:
        async with self._lock:
            texts = self._text_store.get(session_id, [])
            return " ".join(texts).strip()

    async def clear_session(self, session_id: str):
        async with self._lock:
            self._store.pop(session_id, None)
            self._stt_store.pop(session_id, None)
            self._text_store.pop(session_id, None)

    def _merge_wav_list(self, wav_chunks: List[bytes]) -> bytes:
        if not wav_chunks:
            return b""
        if len(wav_chunks) == 1:
            return wav_chunks[0]

        first = wave.open(io.BytesIO(wav_chunks[0]))
        nchannels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()
        first.close()

        all_frames = bytearray()
        for chunk in wav_chunks:
            try:
                wf = wave.open(io.BytesIO(chunk))
                all_frames.extend(wf.readframes(wf.getnframes()))
                wf.close()
            except Exception:
                continue

        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as out_wf:
            out_wf.setnchannels(nchannels)
            out_wf.setsampwidth(sampwidth)
            out_wf.setframerate(framerate)
            out_wf.writeframes(bytes(all_frames))
        return out_buf.getvalue()


# Global Singleton Session Store
session_store = SessionAudioStore()
