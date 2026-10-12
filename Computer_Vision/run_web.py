import argparse
import os
import sys
import uvicorn

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description="VisionFlow web server")
    parser.add_argument(
        "--config",
        default=os.environ.get("VISIONFLOW_CONFIG", "config.yaml"),
        help="Path to the YAML runtime configuration",
    )
    args = parser.parse_args()
    os.environ["VISIONFLOW_CONFIG"] = args.config

    print("=" * 65)
    print("  VISIONFLOW AI - SMART GATE DASHBOARD & PEOPLE MONITORING")
    print("=" * 65)
    print("[Server] Web Server đang khởi động tại: http://localhost:8000")
    print("[Camera] Camera và AI sẽ tự khởi động cùng máy chủ.")
    print("[Camera] Nếu chưa có tín hiệu, hệ thống sẽ liên tục tự kết nối lại.")
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
