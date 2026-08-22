"""
run.py — Entry point khởi chạy ứng dụng.

Chế độ LOCAL (mặc định):
    python run.py

Chế độ PUBLIC (mở Ngrok tunnel HTTPS, URL cố định):
    python run.py --public

Yêu cầu trong .env cho chế độ PUBLIC:
    NGROK_AUTHTOKEN=...
    NGROK_DOMAIN=your-domain.ngrok-free.app
"""

import os
import sys
import time
import threading
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PORT = int(os.getenv("PORT", 8000))
PUBLIC_MODE = "--public" in sys.argv


def start_ngrok():
    """Khởi động Ngrok tunnel với Static Domain sau khi server sẵn sàng."""
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    domain    = os.getenv("NGROK_DOMAIN")

    if not authtoken:
        print("[Ngrok] ERROR: Thiếu NGROK_AUTHTOKEN trong file .env")
        return
    if not domain:
        print("[Ngrok] ERROR: Thiếu NGROK_DOMAIN trong file .env")
        return

    try:
        from pyngrok import ngrok, conf
    except ImportError:
        print("[Ngrok] ERROR: pyngrok chưa được cài. Chạy: pip install pyngrok")
        return

    conf.get_default().auth_token = authtoken

    # Đợi FastAPI server sẵn sàng (tối đa 30s)
    print("[Ngrok] Dang doi server khoi dong...")
    for _ in range(30):
        time.sleep(1)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1)
            break
        except Exception:
            continue

    # Mở tunnel với Static Domain cố định
    tunnel = ngrok.connect(PORT, domain=domain, bind_tls=True)
    url = tunnel.public_url

    print("\n" + "=" * 60)
    print(f"  LINK CONG KHAI (chia se link nay cho nguoi dung):")
    print(f"  >>  {url}")
    print("=" * 60)
    print("  Nhan Ctrl+C de dong server va tat tunnel.\n")


if __name__ == "__main__":
    mode = "PUBLIC" if PUBLIC_MODE else "LOCAL"
    print(f"=== Vi-En Translator Server [{mode} MODE] — Port {PORT} ===")

    if PUBLIC_MODE:
        # Chạy Ngrok trong thread riêng, không chặn server
        t = threading.Thread(target=start_ngrok, daemon=True)
        t.start()

    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=False)
