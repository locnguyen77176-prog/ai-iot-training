import time
import json
import base64
import asyncio
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.vad_stream import VADSegmenter, init_silero_vad
from app.services.stt import run_whisper_stt
from app.services.translation import translate_text
from app.services.tts import tts_stream_chunks
from app.core.session_store import session_store

websocket_router = APIRouter()


@websocket_router.websocket("/ws/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = f"ws_sess_{int(time.time() * 1000)}"
    await session_store.init_session(session_id)

    vad = VADSegmenter(sample_rate=16000, silence_duration_ms=400)
    source_lang = "vi"
    target_lang = "en"
    t_session_start = time.perf_counter()

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                pcm_data = message["bytes"]
                # Process PCM audio frame through VAD
                completed_wav = vad.add_pcm_chunk(pcm_data)

                if completed_wav:
                    # Voice pause detected! Process sentence slice concurrently in background
                    asyncio.create_task(
                        _process_sentence_slice(
                            session_id=session_id,
                            wav_bytes=completed_wav,
                            source_lang=source_lang,
                            target_lang=target_lang,
                            websocket=websocket
                        )
                    )

            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    event_type = payload.get("event")

                    if event_type == "start":
                        source_lang = payload.get("source_lang", "vi")
                        target_lang = payload.get("target_lang", "en")
                        t_session_start = time.perf_counter()
                        await session_store.init_session(session_id)
                        vad = VADSegmenter(sample_rate=16000, silence_duration_ms=400)
                        await websocket.send_json({"event": "started", "session_id": session_id})

                    elif event_type == "stop":
                        # Flush remaining audio in VAD buffer
                        remaining_wav = vad.flush()
                        if remaining_wav:
                            await _process_sentence_slice(
                                session_id=session_id,
                                wav_bytes=remaining_wav,
                                source_lang=source_lang,
                                target_lang=target_lang,
                                websocket=websocket
                            )

                        # Deliver pre-buffered merged audio instantaneously (<0.1s perceived latency)
                        t_stop = time.perf_counter()
                        merged_wav = await session_store.get_merged_audio(session_id)
                        full_stt_text = await session_store.get_full_stt(session_id)
                        full_translation = await session_store.get_full_translation(session_id)

                        t_latency = round(time.perf_counter() - t_stop, 3)
                        t_total = round(time.perf_counter() - t_session_start, 3)

                        audio_b64 = f"data:audio/wav;base64,{base64.b64encode(merged_wav).decode('utf-8')}" if merged_wav else ""

                        await websocket.send_json({
                            "event": "final_audio",
                            "session_id": session_id,
                            "stt_text": full_stt_text,
                            "translation": full_translation,
                            "audio_b64": audio_b64,
                            "latency": {
                                "perceived_playback_delay": t_latency,
                                "total_session": t_total
                            }
                        })
                        await session_store.clear_session(session_id)

                    elif event_type == "ping":
                        await websocket.send_json({"event": "pong"})

                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        await session_store.clear_session(session_id)
    except Exception as e:
        await session_store.clear_session(session_id)


async def _process_sentence_slice(
    session_id: str,
    wav_bytes: bytes,
    source_lang: str,
    target_lang: str,
    websocket: WebSocket
):
    """Processes a dứt câu audio slice through STT -> NMT -> TTS concurrently with speech context continuity."""
    try:
        # Get accumulated previous spoken text for context continuity
        previous_stt = await session_store.get_full_stt(session_id)

        # 1. STT with Speech Context Conditioning
        stt_text = await asyncio.to_thread(run_whisper_stt, wav_bytes, source_lang, previous_stt)
        if not stt_text.strip():
            return

        await session_store.add_stt_text(session_id, stt_text)
        full_stt_text = await session_store.get_full_stt(session_id)

        # 2. NMT
        translation = await translate_text(stt_text, source_lang, target_lang)
        if not translation.strip():
            return

        # 3. TTS (Piper ONNX Parallel)
        tts_b64, _ = await tts_stream_chunks(translation, target_lang)

        if tts_b64:
            tts_wav_bytes = base64.b64decode(tts_b64)
            await session_store.add_wav_chunk(session_id, tts_wav_bytes, translation)

        full_translation = await session_store.get_full_translation(session_id)

        # Notify UI with full accumulated translation and full spoken text update
        await websocket.send_json({
            "event": "partial_text",
            "session_id": session_id,
            "stt_text": full_stt_text,
            "translation": full_translation
        })

    except Exception as e:
        print(f"[WebSocket Worker Error]: {e}")
