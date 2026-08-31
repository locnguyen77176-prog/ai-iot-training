# 🎙️ Real-time Vi-En Voice & Text Translator

Ứng dụng web dịch thuật **Giọng nói & Văn bản** hai chiều **Tiếng Việt ↔ Tiếng Anh** thời gian thực với độ trễ siêu thấp. Tích hợp công nghệ nhận diện giọng nói **Faster-Whisper (GPU)**, dịch thuật **Google Gemini API (`gemini-3.5-flash-lite`)** và tổng hợp giọng đọc **Piper TTS (Local CPU)**.

---

## ⚙️ Kiến trúc & Công nghệ (Tech Stack)

| Thành phần | Công nghệ | Mô tả / Vai trò |
|---|---|---|
| **Backend Framework** | FastAPI + Uvicorn | Async Python Web & WebSocket Server (chạy Local tại `127.0.0.1:8000`) |
| **STT (Speech-to-Text)** | `faster-whisper` (`large-v3-turbo`) | Nhận diện giọng nói 100% Local trên NVIDIA CUDA GPU (float16) hoặc CPU fallback |
| **Dịch thuật (NMT)** | Google Gemini API (`gemini-3.5-flash-lite`) | Dịch thuật hai chiều Việt ↔ Anh
| **VAD (Voice Activity)** | Silero VAD (PyTorch) | Tự động phát hiện khoảng lặng (>400ms) để cắt câu chính xác |
| **Streaming Engine** | FastAPI WebSocket (`/ws/stream`) | Xử lý âm thanh dạng stream song song theo thời gian thực |
| **TTS (Text-to-Speech)** | Piper TTS (ONNX Runtime) — **Offline** | Tổng hợp tiếng nói 100% Local trên CPU đa luồng (0 MB VRAM) |
| **Chuẩn hóa Âm thanh** | FFmpeg In-memory Stream | Chuyển đổi âm thanh WebM/OGG/PCM ➔ WAV 16kHz PCM 16-bit |
| **Public Tunnel** | Cloudflare Quick Tunnel (`cloudflared`) | Tự động mở đường dẫn Public HTTPS/WSS khi chạy cờ `--public` (Miễn phí 100%) |
| **Frontend UI** | HTML5 + CSS3 Glassmorphism + Vanilla JS | Single Page Web App tương tác nhanh, không phụ thuộc framework |

---

## 🔄 Luồng Hoạt Động của Dữ Liệu (Data Flow)

Ứng dụng hoạt động theo **3 luồng chính**:

### 1. Luồng Dịch Giọng nói Batch (REST API `/api/voice-translate`)

Dành cho chế độ thu âm 🎙️ **Nói** ➔ Bấm ⏹️ **Dừng và Dịch**.

```
[ Client Microphone ]
         │ (File âm thanh WebM / OGG)
         ▼ (HTTP POST /api/voice-translate)
[ FastAPI Endpoint ]
         │
         ▼ 1. In-memory Audio Conversion
[ FFmpeg Engine ] ────────► Chuyển đổi trực tiếp trong RAM thành WAV 16kHz Mono 16-bit
         │
         ▼ 2. Speech-to-Text (STT Local)
[ Faster-Whisper GPU ] ──► Model Whisper (Greedy Search beam_size=1) ──► Văn bản gốc (STT Text)
         │                    (Tiêm Context Prompt từ khóa chuyên ngành IoT/HaUI/CNTT)
         ▼ 3. Neural Machine Translation (Gemini API)
[ Google Gemini API ] ──► Model gemini-3.5-flash-lite (~0.2s) ──► Văn bản đã dịch (Target Text)
         │
         ▼ 4. Text-to-Speech (TTS Local)
[ Piper ONNX Engine ] ──► Tách câu & Tổng hợp song song (ThreadPool 6 worker) ──► Audio WAV Base64
         │
         ▼ (JSON Response)
[ Client Web UI ] ──────► Hiển thị STT, Bản dịch, Tự động phát âm thanh & Bảng Latency chi tiết
```

---

### 2. Luồng Dịch Giọng nói Real-time Streaming (WebSocket `/ws/stream`)

Dành cho chế độ stream liên tục, phản hồi âm thanh **tức thì (<0.1s perceived delay)** khi vừa nhả mic.

```
[ Client Microphone ] ──► Stream liên tục các chunk PCM 16kHz qua WebSocket /ws/stream
         │
         ▼
[ VADSegmenter (Silero VAD) ] ──► Phân tích tín hiệu & phát hiện ngắt câu (khoảng lặng >400ms)
         │
         ├──► Khi phát hiện DỨT 1 CÂU:
         │        │
         │        ▼ (Đẩy vào Background Worker Async)
         │    [ Background Worker Pipeline ]
         │        ├── 1. Whisper STT Local (Dùng câu trước làm Context Prompt)
         │        ├── 2. Gemini API Dịch câu vừa nhận diện (~0.2s)
         │        └── 3. Piper TTS Local tổng hợp chunk WAV của câu đó
         │        │
         │        ▼
         │    [ Session Store (RAM Buffer) ] ──► Lưu tích lũy văn bản & nối sẵn các chunk WAV
         │
         └──► Khi người dùng bấm ⏹️ Dừng (Gửi event "stop"):
                  │
                  ▼
              [ Session Store ] ──► Xuất đoạn âm thanh WAV đã được ghép sẵn trong RAM
                  │
                  ▼ (Phản hồi perceived delay)
              [ Client UI ] ──► Phát âm thanh dịch hoàn chỉnh ngay lập tức!
```

---

### 3. Luồng Dịch Văn bản (REST API `/api/text-translate`)

```
[ Client Text Input ] ──► [ Gemini API Dịch (~0.2s) ] ──► [ Piper TTS Local ] ──► [ Audio & Text Response ]
```

---

## 🚀 Điểm Nổi Bật & Tối Ưu Hiệu Năng

### 1. Khởi động Nóng Tự động (Automated Server Warmup)
- **Tự động Warmup CUDA GPU**: Chạy ngầm 1 sample âm thanh rỗng 0.5s khi bật server để ép PyTorch khởi tạo CUDA Context, VRAM allocator và cuDNN JIT Kernels.
- **Tự động Warmup Gemini TLS**: Mở sẵn kết nối HTTPS mã hóa TLS tới máy chủ Google AI Studio.
- **Kết quả**: Loại bỏ hoàn toàn độ trễ Cold Start, giúp lượt dịch đầu tiên đạt luôn tốc độ cao bằng lượt dịch thứ 2.

### 2. STT — Faster-Whisper GPU (Local)
- **Greedy Search (`beam_size=1`)**: Tăng tốc nhận diện ~2.5× so với mặc định.
- **VAD Filter**: Tự động lọc tạp âm và khoảng lặng.
- **Context Prompt Conditioning**: Tiêm sẵn từ khóa chuyên ngành (IoT, vi điều khiển, HaUI...) nâng cao độ chính xác.

### 3. Dịch thuật — Google Gemini (`gemini-3.5-flash-lite`)
- **Client Caching & Pre-built Config**: Tối ưu tài nguyên, không allocate lại object cho mỗi request.
- **Tốc độ siêu nhanh**: Phản hồi chỉ trong **~0.2s - 0.5s**.

### 4. TTS — Piper TTS ONNX (Local 100% Offline)
- **Parallel Sentence Synthesis**: Tách câu văn bản dài và tổng hợp **song song trong 6 worker threads**, giảm thời gian TTS cho văn bản dài từ 5s xuống ~1s.
- **In-memory RAM Cache**: Trả kết quả tức thì `< 0.003s` khi gặp lại câu trùng lặp.

---

## 📁 Cấu Trúc Thư Mục Dự Án

```
STT_To_TTS/
├── app/
│   ├── main.py                  # Khởi tạo ứng dụng FastAPI, lifespan setup & CORS
│   ├── api/
│   │   ├── routes.py            # REST Endpoints (/api/voice-translate, /api/text-translate, /api/health)
│   │   └── websocket_routes.py  # WebSocket Endpoint (/ws/stream) xử lý streaming real-time
│   ├── core/
│   │   ├── config.py            # Cấu hình biến môi trường và đường dẫn model
│   │   ├── cuda_setup.py        # Tự động nạp thư viện DLL CUDA trên Windows
│   │   └── session_store.py     # Bộ nhớ tạm RAM lưu giữ session stream audio & văn bản
│   ├── models/
│   │   └── schemas.py           # Pydantic Schemas định dạng dữ liệu đầu vào/đầu ra
│   └── services/
│       ├── stt.py               # Dịch vụ Faster-Whisper GPU STT (Local + GPU Warmup)
│       ├── tts.py               # Dịch vụ Piper TTS Offline (Local CPU, Multi-threaded)
│       ├── translation.py       # Dịch vụ dịch thuật Google Gemini API (gemini-3.5-flash-lite + TLS Warmup)
│       ├── audio.py             # Dịch vụ chuẩn hóa audio qua FFmpeg
│       └── vad_stream.py        # Dịch vụ cắt phân đoạn giọng nói VAD (Silero VAD)
├── bin/
│   └── cloudflared.exe          # Tự động tải binary Cloudflare Tunnel khi chạy public mode
├── models/
│   └── tts/                     # Thư mục chứa model Piper ONNX (auto-downloaded)
│       ├── vi_VN-vais1000-medium.onnx
│       └── en_US-lessac-medium.onnx
├── docs/
│   └── streaming_design.md      # Tài liệu thiết kế chi tiết luồng WebSocket Streaming
├── index.html                   # Giao diện người dùng Single Page (HTML/CSS/JS)
├── download_models.py           # Script tự động tải các model Whisper & Piper TTS về local
├── run.py                       # Entry point khởi chạy server (Local / Public Mode)
├── requirements.txt             # Các thư viện Python cần thiết
├── Dockerfile                   # Cấu hình đóng gói Container Docker
├── .env                         # Cấu hình biến môi trường
└── README.md                    # Tài liệu hướng dẫn dự án
```

---

## 🛠️ Cài Đặt & Khởi Chạy

### 1. Yêu cầu Hệ thống
- **Python**: 3.10 trở lên
- **FFmpeg**: Đã cài đặt và thêm vào biến môi trường `PATH`.
- **Google Gemini API Key**: Lấy API Key miễn phí tại [Google AI Studio](https://aistudio.google.com/apikey).

### 2. Cài đặt Thư viện Python
```bash
pip install -r requirements.txt
```

### 3. Tải các Model AI về Máy Cục bộ
Chạy script để tải trước Whisper STT (`large-v3-turbo`) & Piper TTS models:
```bash
python download_models.py
```

### 4. Cấu hình `.env`
Tạo file `.env` tại thư mục gốc dự án:
```env
HOST=127.0.0.1
PORT=8000
WHISPER_MODEL_SIZE=large-v3-turbo
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your_gemini_api_key_here
```

### 5. Khởi động Ứng dụng

#### 🔹 Chế độ Local (Mặc định cho máy của bạn)
```bash
python run.py
```
👉 Truy cập tại: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

#### 🌐 Chế độ Public (Chia sẻ đường dẫn HTTPS công khai qua Internet — 100% Miễn phí, Không đăng ký)
Chạy server với cờ `--public`:
```bash
python run.py --public
```
Server sẽ tự động khởi tạo Cloudflare Quick Tunnel và in đường dẫn **`https://xxxx.trycloudflare.com`** ra màn hình. Bạn chỉ cần copy link này gửi cho người khác truy cập từ bất kỳ đâu trên thế giới!
