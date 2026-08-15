# Webapp Dịch Giọng nói & Văn bản Tiếng Việt -> Tiếng Anh (Low Latency)

Ứng dụng web dịch thuật Giọng nói và Văn bản từ Tiếng Việt sang Tiếng Anh. Yêu cầu máy có GPU CUDA để nạp model Whisper trên GPU.

## 🚀 Điểm nổi bật & Công nghệ Kỹ thuật (Tech Stack)

1. **Speech-to-Text (STT)**:
   - Thư viện `faster-whisper` nạp sẵn Model `small` trực tiếp trên **GPU CUDA** (`float16`).
   - Thời gian xử lý phụ thuộc vào GPU và kích thước model; dự kiến thấp hơn khi chạy trên GPU hiện đại.
2. **Translation**:
   - Sử dụng `google-genai` SDK với model **gemini-3.5-flash-lite** (cấu hình qua biến môi trường `GEMINI_MODEL`).
   - System instruction tối ưu để trả về câu dịch ngắn gọn, giữ nguyên ý nghĩa nguồn.
3. **Text-to-Speech (TTS)**:
   - Thư viện `edge-tts` với giọng đọc mặc định `en-US-JennyNeural` (có thể cấu hình bằng biến môi trường `EDGE_TTS_VOICE`).
   - Streaming âm thanh trực tiếp trong bộ nhớ và trả về dưới dạng base64 (không lưu file tạm ra ổ đĩa), giảm độ trễ I/O.
4. **Chuẩn hóa Âm thanh**:
   - Tự động nén/chuyển đổi luồng audio từ trình duyệt (`WebM`/`WAV`/`OGG`) về chuẩn **WAV 16kHz 16-bit Mono PCM** bằng FFmpeg in-memory stream.
5. **Frontend**:
   - Giao diện Single File `index.html` hiện đại với waveform visualizer, đồng hồ đếm thời gian thu âm và bảng thống kê **Latency breakdown** (STT + Gemini + TTS = Total).

---

## 🛠️ Hướng dẫn Chạy Ứng dụng

### 1. Khởi động Server FastAPI
Mở terminal tại thư mục dự án và chạy câu lệnh:
```bash
python run.py
```
Server sẽ nạp Whisper Model `small` lên GPU CUDA (yêu cầu CUDA khả dụng) và lắng nghe tại: **`http://127.0.0.1:8000`**

Lưu ý:
- Nếu máy không có CUDA, ứng dụng sẽ báo lỗi khi khởi động vì thiết kế hiện tại yêu cầu chạy Whisper trên GPU để đạt độ trễ thấp.
- Cung cấp `GEMINI_API_KEY` bằng một trong các cách:
   - Đặt biến môi trường `GEMINI_API_KEY` trước khi chạy, ví dụ (Windows PowerShell):
      ```powershell
      $env:GEMINI_API_KEY = "your_api_key_here"
      python run.py
      ```
   - Hoặc nhập API key trên giao diện web (lưu vào `localStorage`).

### 2. Sử dụng Ứng dụng Web
- Mở trình duyệt web truy cập **`http://127.0.0.1:8000`**.
- Nhập **Gemini API Key** của bạn ở thanh cấu hình phía trên (API key sẽ được lưu an toàn trong trình duyệt `localStorage` để không phải nhập lại lần sau), hoặc đặt biến môi trường `GEMINI_API_KEY`.
- **Luồng Giọng nói (Voice Mode)**:
  - Bấm nút 🎙️ **Thu âm** -> Nói Tiếng Việt -> Bấm ⏹️ **Dừng & Dịch**.
  - Hệ thống sẽ hiển thị câu tiếng Việt nhận diện được, bản dịch tiếng Anh, tự động phát âm thanh giọng đọc tiếng Anh và hiển thị chính xác độ trễ (Latency).
- **Luồng Văn bản (Text Mode)**:
  - Nhập văn bản tiếng Việt vào ô nhập liệu (hoặc chọn các câu mẫu gợi ý) -> Bấm **🚀 Dịch sang Tiếng Anh** (hoặc gõ `Ctrl + Enter`).

---

## 📁 Cấu trúc Thư mục Dự án

```
STT_To_TTS/
├── app.py              # FastAPI Backend (GPU Whisper STT, gemini-3.5-flash-lite, Edge-TTS)
├── index.html          # Frontend giao diện người dùng (Single-page Web UI)
├── run.py              # Script khởi chạy ứng dụng uvicorn
├── requirements.txt    # Các thư viện Python cần thiết
└── README.md           # Hướng dẫn chi tiết
```
