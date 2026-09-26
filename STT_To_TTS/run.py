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

    # Đợi FastAPI server nạp xong toàn bộ Model và sẵn sàng phản hồi
    print("[Cloudflare] Đang chờ server nạp xong AI Model và sẵn sàng...", flush=True)
    server_ready = False
    for _ in range(60):
        time.sleep(1)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/health", headers={"User-Agent": "CFT"})
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            continue

    if not server_ready:
        print("[Cloudflare Error] Server chưa sẵn sàng sau 60 giây.", flush=True)
        return

    cloudflared_cmd = ensure_cloudflared()
    if not cloudflared_cmd:
        print("[Cloudflare Error] Không tìm thấy công cụ cloudflared.exe.", flush=True)
        return

    try:
        print("[Cloudflare] Server đã sẵn sàng! Đang khởi tạo đường dẫn HTTPS công khai...", flush=True)
        cmd = [
            cloudflared_cmd,
            "tunnel",
            "--no-autoupdate",
            "--url", f"http://127.0.0.1:{PORT}"
        ]
        
        _tunnel_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        def _log_and_find_url():
            found = False
            for line in _tunnel_proc.stderr:
                if not found:
                    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                    if match:
                        found = True
                        public_url = match.group(0)
                        print("\n" + "=" * 70, flush=True)
                        print("🚀 ĐƯỜNG DẪN PUBLIC CLOUDFLARE HTTPS MỚI:", flush=True)
                        print(f"👉  {public_url}", flush=True)
                        print("=" * 70, flush=True)
                        print("  💡 Lưu ý quan trọng:", flush=True)
                        print("     1. Mỗi lần khởi động lại server sẽ tạo 1 link MỚI. Link cũ sẽ bị Error 1033.", flush=True)
                        print("     2. Luôn giữ cửa sổ Terminal này chạy để duy trì kết nối.", flush=True)
                        print("     3. Đợi khoảng 5-10 giây sau khi có link để Cloudflare cập nhật DNS.\n", flush=True)

        reader_thread = threading.Thread(target=_log_and_find_url, daemon=True)
        reader_thread.start()

    except Exception as e:
        print(f"[Cloudflare Error] Lỗi khởi chạy Tunnel: {e}", flush=True)


if __name__ == "__main__":
    mode = "PUBLIC (CLOUDFLARE HTTPS)" if PUBLIC_MODE else "LOCAL"
    print(f"=== Vi-En Translator Server [{mode} MODE] — http://{HOST}:{PORT} ===", flush=True)

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
