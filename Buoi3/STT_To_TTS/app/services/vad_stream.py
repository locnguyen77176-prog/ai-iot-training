import io
import wave
import struct
import math
from typing import List, Optional

import torch

_SILERO_MODEL = None
_SILERO_UTILS = None


def init_silero_vad():
    global _SILERO_MODEL, _SILERO_UTILS
    if _SILERO_MODEL is not None:
        return

    try:
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False
        )
        _SILERO_MODEL = model
        _SILERO_UTILS = utils
        print("[Silero-VAD] Loaded Silero VAD PyTorch Model successfully!")
    except Exception as e:
        print(f"[Silero-VAD] Warning: Internet/Hub download fallback to Adaptive Energy VAD ({e})")


class VADSegmenter:
    """
    Slices continuous 16kHz Mono 16-bit PCM audio stream into sentence audio slices.
    Trigger silence threshold: 600ms.
    """
    def __init__(self, sample_rate: int = 16000, silence_duration_ms: int = 600):
        self.sample_rate = sample_rate
        self.silence_duration_ms = silence_duration_ms
        self.silence_frames_threshold = int((silence_duration_ms / 1000.0) * sample_rate)
        
        self.pcm_buffer = bytearray()
        self.speech_buffer = bytearray()
        self.in_speech = False
        self.silent_sample_count = 0

    def add_pcm_chunk(self, pcm_bytes: bytes) -> Optional[bytes]:
        """
        Appends raw PCM samples (16-bit Mono, 16kHz).
        Returns a complete WAV byte chunk when a sentence boundary (silence pause) is detected.
        """
        if not pcm_bytes:
            return None

        self.pcm_buffer.extend(pcm_bytes)
        
        # Analyze in 32ms frames (512 samples at 16kHz)
        frame_size = 512
        frame_bytes = frame_size * 2 # 16-bit PCM = 2 bytes per sample

        completed_chunk = None

        while len(self.pcm_buffer) >= frame_bytes:
            chunk = bytes(self.pcm_buffer[:frame_bytes])
            del self.pcm_buffer[:frame_bytes]

            is_speech = self._is_speech_frame(chunk)

            if is_speech:
                self.speech_buffer.extend(chunk)
                self.in_speech = True
                self.silent_sample_count = 0
            else:
                if self.in_speech:
                    self.speech_buffer.extend(chunk)
                    self.silent_sample_count += frame_size

                    if self.silent_sample_count >= self.silence_frames_threshold:
                        # Sentence pause detected! Must have at least 1s of speech audio
                        if len(self.speech_buffer) >= 16000:
                            completed_chunk = self._convert_pcm_to_wav(bytes(self.speech_buffer))
                        
                        self.speech_buffer.clear()
                        self.in_speech = False
                        self.silent_sample_count = 0

        return completed_chunk

    def flush(self) -> Optional[bytes]:
        """Flushes remaining audio buffer on stream end."""
        if len(self.speech_buffer) >= 8000: # 0.5s min
            wav_bytes = self._convert_pcm_to_wav(bytes(self.speech_buffer))
            self.speech_buffer.clear()
            self.in_speech = False
            return wav_bytes
        self.speech_buffer.clear()
        return None

    def _is_speech_frame(self, pcm_frame: bytes) -> bool:
        """Determines if a 32ms PCM frame contains human speech."""
        samples = struct.unpack(f"<{len(pcm_frame)//2}h", pcm_frame)
        if not samples:
            return False

        # Calculate RMS energy
        energy = math.sqrt(sum(s * s for s in samples) / len(samples))
        
        if _SILERO_MODEL is not None:
            try:
                audio_tensor = torch.tensor([s / 32768.0 for s in samples], dtype=torch.float32)
                speech_prob = _SILERO_MODEL(audio_tensor, self.sample_rate).item()
                return speech_prob > 0.4
            except Exception:
                pass

        # Energy VAD fallback threshold
        return energy > 350.0

    def _convert_pcm_to_wav(self, pcm_data: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)
        return buf.getvalue()
