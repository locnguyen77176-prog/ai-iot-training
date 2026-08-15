import sys
import uvicorn

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("=== Starting Vi-En Fast Translator Server (Port 8000)... ===")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)

I