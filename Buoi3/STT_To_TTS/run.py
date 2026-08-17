import os
import sys
import uvicorn

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    port = int(os.getenv("PORT", 8000))
    print(f"=== Starting Vi-En Fast Translator Server (Port {port})... ===")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)


