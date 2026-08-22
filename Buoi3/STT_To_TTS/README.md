# 🎙️ Real-time Vi-En Voice & Text Translator

Ứng dụng web dịch thuật **Giọng nói và Văn bản** hai chiều **Tiếng Việt ↔ Tiếng Anh** thời gian thực với độ trễ thấp, hoạt động **100% trên máy cục bộ** (không phụ thuộc Cloud cho STT và TTS).

---

## ⚙️ Kiến trúc & Công nghệ (Tech Stack)

| Thành phần | Công nghệ | Ghi chú |
|---|---|---|
| **Backend** | FastAPI + Uvicorn | Async Python server |
| **STT** (Speech-to-Text) | `faster-whisper` `large-v3-turbo` (GPU) | Chạy trên CUDA GPU, tự động fallback CPU |
| **Dịch thuật** | Google Gemini API (`gemini-3.5-flash-lite`) | Cấu hình qua `.env` |
| **TTS** (Text-to-Speech) | Piper TTS (ONNX Runtime) — **Offline Local** | 0 MB VRAM, chạy trên CPU đa luồng |
| **Chuẩn hóa Âm thanh** | FFmpeg in-memory stream | Chuyển đổi WebM/OGG → WAV 16kHz |
| **Frontend** | HTML + CSS + Vanilla JS | Single-file, không framework |

---

## 🚀 Điểm Nổi bật

### 1. STT — Faster-Whisper GPU (Offline)
- Model `large-v3-turbo` được nạp sẵn lên **GPU CUDA** (float16) và tự động fallback sang CPU nếu không có GPU.
- Sử dụng **Greedy Search** (`beam_size=1`) để tăng tốc ~2.5× so với beam search mặc định.
- **VAD Filter** tích hợp tự động cắt bỏ khoảng lặng, tối ưu cho âm thanh thu từ microphone laptop.
- **Context Prompt** tiêm sẵn từ khóa chuyên ngành (IoT, vi điều khiển, HaUI...) để tăng độ chính xác nhận diện thuật ngữ.

### 2. Dịch thuật — Google Gemini (`gemini-3.5-flash-lite`)
- Client được cache theo API key, không khởi tạo lại mỗi request.
- Pre-built `GenerateContentConfig` cho cả 2 chiều dịch, giảm overhead mỗi lần gọi API.
- Timeout 15 giây, tự động trả lỗi thay vì treo mãi.

### 3. TTS — Piper TTS ONNX (Hoàn toàn Offline)
- **0 phụ thuộc Internet** sau khi tải model lần đầu — không dùng Google TTS hay Edge-TTS.
- **Parallel Sentence Synthesis**: Văn bản dài được tách thành câu và xử lý **song song** trong `ThreadPoolExecutor` (6 luồng), giảm độ trễ từ ~5s xuống còn **~1s** cho đoạn văn dài.
- **In-memory Cache** (RAM): Các câu đã tổng hợp được lưu cache, phản hồi tức thì `< 0.003s` khi lặp lại.
- **Warmup lúc khởi động**: Cả 2 model giọng đọc được load và làm ấm sẵn, không bị trễ ở lượt dịch đầu tiên.
- Giọng đọc Local: `vi_VN-vais1000-medium` (Tiếng Việt) & `en_US-lessac-medium` (Tiếng Anh).

---

## 🛠️ Cài đặt & Chạy Ứng dụng

### 1. Yêu cầu Hệ thống
- Python **3.10+**
- FFmpeg (cài trong PATH hệ thống)
- GPU NVIDIA với CUDA (khuyến nghị, ít nhất 2GB VRAM) — hoặc chạy bằng CPU

### 2. Cài đặt Thư viện
```bash
pip install -r requirements.txt
```

### 3. Cấu hình API Key
Tạo file `.env` ở thư mục gốc dự án:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
> Lấy API Key miễn phí tại: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### 4. Khởi động Server
```bash
python run.py
```
Server sẽ thực hiện theo thứ tự:
1. Nạp Faster-Whisper `large-v3-turbo` lên GPU
2. Nạp & Warmup 2 model Piper TTS (Tiếng Việt + Tiếng Anh)
3. Lắng nghe tại **`http://127.0.0.1:8000`**

---

## 📋 Hướng dẫn Sử dụng

### 🎤 Chế độ Giọng nói (Voice Mode)
1. Chọn chiều dịch (🇻🇳 → 🇺🇸 hoặc 🇺🇸 → 🇻🇳) bằng nút **⇄** ở giữa.
2. Bấm nút 🎙️ → Nói → Bấm ⏹️ để dừng và dịch.
3. Kết quả hiển thị: văn bản nhận diện, bản dịch, âm thanh tự phát và bảng **Latency** chi tiết.

### ⌨️ Chế độ Văn bản (Text Mode)
1. Nhập văn bản vào ô nhập liệu (hoặc chọn câu mẫu gợi ý).
2. Bấm **🚀 Dịch** hoặc nhấn `Ctrl + Enter`.

---

## 📁 Cấu trúc Thư mục

```
STT_To_TTS/
├── app/
│   ├── main.py              # Khởi tạo FastAPI + Lifespan (load model)
│   ├── core/
│   │   ├── config.py        # Cấu hình (model, đường dẫn, API keys)
│   │   └── cuda_setup.py    # Khởi tạo CUDA DLL paths
│   ├── models/
│   │   └── schemas.py       # Pydantic request/response schemas
│   ├── services/
│   │   ├── stt.py           # Faster-Whisper STT (GPU)
│   │   ├── tts.py           # Piper TTS Offline (CPU, Parallel)
│   │   ├── translation.py   # Gemini Translation API
│   │   └── audio.py         # FFmpeg audio preprocessing
│   └── api/
│       └── routes.py        # FastAPI API endpoints
├── models/
│   └── tts/                 # Piper ONNX model files (auto-downloaded)
│       ├── vi_VN-vais1000-medium.onnx
│       └── en_US-lessac-medium.onnx
├── index.html               # Frontend (Single-page Web UI)
├── run.py                   # Entry point — khởi chạy uvicorn
├── requirements.txt         # Python dependencies
├── .env                     # API Keys (không commit lên Git)
└── README.md
```

---

## 🔑 Biến Môi trường (`.env`)

| Biến | Mặc định | Mô tả |
|---|---|---|
| `GEMINI_API_KEY` | *(bắt buộc)* | Google Gemini API Key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Tên model Gemini |
| `WHISPER_MODEL_SIZE` | `large-v3-turbo` | Kích thước model Faster-Whisper |
| `PIPER_VOICE_VI` | `vi_VN-vais1000-medium.onnx` | Model giọng đọc Tiếng Việt |
| `PIPER_VOICE_EN` | `en_US-lessac-medium.onnx` | Model giọng đọc Tiếng Anh |
