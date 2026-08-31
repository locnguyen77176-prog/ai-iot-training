"""
run.py — Entry point khởi chạy ứng dụng.

Chế độ LOCAL (mặc định cho máy của bạn):
    python run.py

Chế độ PUBLIC (Mở đường dẫn Cloudflare HTTPS/WSS công khai qua Internet — Miễn phí 100%, 0% đăng ký):
    python run.py --public
"""

import os
import re
import sys
import time
import subprocess
import threading
import urllib.request
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8000))
PUBLIC_MODE = "--public" in sys.argv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
CLOUDFLARED_PATH = os.path.join(BIN_DIR, "cloudflared.exe")
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

_tunnel_proc = None


def ensure_cloudflared() -> str:
    """Kiểm tra và tự động tải binary cloudflared.exe về thư mục bin/ nếu chưa có."""
    # 1. Kiểm tra trong hệ thống (PATH)
    try:
        res = subprocess.run(["cloudflared", "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            return "cloudflared"
    except Exception:
        pass

    # 2. Kiểm tra file cục bộ bin/cloudflared.exe
    if os.path.exists(CLOUDFLARED_PATH):
        return CLOUDFLARED_PATH

    # 3. Tải tự động nếu chưa có
    os.makedirs(BIN_DIR, exist_ok=True)
    print("\n=== Đang tải Cloudflare Tunnel binary (cloudflared.exe - 100% Miễn phí)... ===")
    try:
        urllib.request.urlretrieve(CLOUDFLARED_URL, CLOUDFLARED_PATH)
        print(f"=== [OK] Đã tải xong cloudflared.exe ({os.path.getsize(CLOUDFLARED_PATH)} bytes)! ===\n")
        return CLOUDFLARED_PATH
    except Exception as e:
        print(f"[Cloudflare Error] Không thể tải cloudflared.exe: {e}")
        return ""


def start_cloudflare_tunnel():
    """Khởi chạy Cloudflare Quick Tunnel ngầm trong thread riêng."""
    global _tunnel_proc

    # Đợi FastAPI server khởi động sẵn sàng
    print("[Cloudflare] Đang chờ server local khởi động...")
    for _ in range(30):
        time.sleep(1)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1)
            break
        except Exception:
            continue

    cloudflared_cmd = ensure_cloudflared()
    if not cloudflared_cmd:
        print("[Cloudflare Error] Không tìm thấy công cụ cloudflared.exe.")
        return

    try:
        print("[Cloudflare] Đang khởi tạo đường dẫn HTTPS/WSS công khai...")
        _tunnel_proc = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        # Đọc log stderr để tìm đường dẫn public trycloudflare.com
        for line in _tunnel_proc.stderr:
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                public_url = match.group(0)
                print("\n" + "=" * 70)
                print("🚀 ĐƯỜNG DẪN PUBLIC CLOUDFLARE HTTPS (CHIA SẺ CHO BẤT KỲ AI):")
                print(f"👉  {public_url}")
                print("=" * 70)
                print("  💡 Miễn phí 100% | Không cần đăng ký | Hỗ trợ Micro & Streaming WSS")
                print("  💡 Đường dẫn chỉ hoạt động khi bạn đang bật server này.\n")
                break

    except Exception as e:
        print(f"[Cloudflare Error] Lỗi khởi chạy Tunnel: {e}")


if __name__ == "__main__":
    mode = "PUBLIC (CLOUDFLARE HTTPS)" if PUBLIC_MODE else "LOCAL"
    print(f"=== Vi-En Translator Server [{mode} MODE] — http://{HOST}:{PORT} ===")

    if PUBLIC_MODE:
        # Chạy Cloudflare Tunnel trong thread ngầm
        t = threading.Thread(target=start_cloudflare_tunnel, daemon=True)
        t.start()

    bind_host = "0.0.0.0" if PUBLIC_MODE else HOST
    try:
        uvicorn.run("app.main:app", host=bind_host, port=PORT, reload=False)
    finally:
        if _tunnel_proc:
            _tunnel_proc.terminate()
