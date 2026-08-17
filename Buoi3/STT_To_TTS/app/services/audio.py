import subprocess

def convert_audio_to_wav(input_bytes: bytes) -> bytes:
    """
    Chuyển đổi dữ liệu âm thanh từ WebM/WAV/OGG sang chuẩn WAV 16kHz 16-bit Mono PCM bằng FFmpeg
    hoàn toàn trong bộ nhớ (Memory Stream).

    [OPT-1] Bỏ dependency ffmpeg-python và dùng trực tiếp subprocess.
    Nguyên nhân cũ: try/except bắt mọi Exception, kể cả RuntimeError do returncode != 0,
    khiến FFmpeg được spawn 2 lần cho cùng 1 request (100-150ms overhead mỗi lần lỗi).
    """
    cmd = [
        'ffmpeg', '-y',
        '-hide_banner', '-loglevel', 'error',  # [OPT-1b] Bỏ verbose log, giảm I/O overhead
        '-i', 'pipe:0',
        '-f', 'wav', '-ac', '1', '-ar', '16000', '-acodec', 'pcm_s16le',
        'pipe:1'
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    out, err = proc.communicate(input=input_bytes)
    if proc.returncode != 0:
        raise RuntimeError(f"Lỗi FFmpeg: {err.decode('utf-8', errors='ignore')}")
    return out
