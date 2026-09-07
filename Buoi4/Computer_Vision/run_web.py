import os
import sys
import webbrowser
import uvicorn

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    print("=" * 65)
    print("  VISIONFLOW AI - SMART GATE DASHBOARD & PEOPLE MONITORING")
    print("=" * 65)
    print("[Server] Web Server đang khởi động tại: http://localhost:8000")
    print("[Camera] Camera ĐANG TẮT (Chế độ chờ an toàn - Đèn Webcam tắt).")
    print("[Camera] Camera chỉ mở khi bạn truy cập WebApp trên trình duyệt.")
    print("[Hệ Thống] Nhấn Ctrl+C để dừng máy chủ.")
    print("-" * 65)

    uvicorn.run(
        "web.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
