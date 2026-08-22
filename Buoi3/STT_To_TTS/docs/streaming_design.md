# Tài liệu Thiết kế Kiến trúc WebSocket Streaming Voice Translate (Latency < 4s)

## 1. Tóm tắt Yêu cầu & Mục tiêu (Understanding Summary)
* **Mục tiêu:** Giảm tổng thời gian phản hồi (Latency) luồng dịch giọng nói thời gian thực xuống **dưới 4 giây** (hướng tới Time-To-First-Audio < 1.5 giây).
* **Vấn đề cần giải quyết:** 
  * Chiều Việt ➔ Anh: Xử lý STT (Whisper) chậm khi dùng HTTP Block Request.
  * Chiều Anh ➔ Việt: Xử lý TTS (Edge-TTS) chậm khi tổng hợp toàn bộ câu văn bản lớn.
* **Môi trường phần cứng:** GPU NVIDIA GeForce RTX 3050 (4GB VRAM) + CUDA 12.4 + PyTorch cu124.

---

## 2. Các Giả định (Assumptions)
1. Trình duyệt client hỗ trợ Web Audio API (`AudioContext`, `MediaRecorder`) để stream âm thanh định dạng PCM/WebM qua WebSocket.
2. Mô hình Whisper giữ nguyên bản **`small`** chạy trên GPU với kiểu tính toán `float16`.
3. Gemini Flash API dùng chế độ `generate_content_stream` để trả về kết quả từng token.

---

## 3. Nhật ký Quyết định (Decision Log)

| STT | Quyết định | Phương án thay thế | Lý do chọn |
| :--- | :--- | :--- | :--- |
| **1** | Chuyển sang **Full Duplex WebSocket Pipeline** | HTTP POST Request tuần tự | Giảm bớt thời gian chờ thu toàn bộ audio, giảm latency từ 8-10s xuống còn **1.0-1.5s**. |
| **2** | Giữ nguyên **Whisper `small` GPU (float16)** | Hạ cấp xuống `tiny` / `base` | Đảm bảo độ chính xác dịch tiếng Việt mà vẫn đạt tốc độ xử lý trên GPU RTX 3050 dưới 400ms/câu. |
| **3** | **Streaming Pipelining** (Gemini Stream ➔ Edge-TTS) | Chờ Gemini dịch xong cả câu rồi mới gọi TTS | Cho phép client phát được âm thanh ngay ở token/cụm từ đầu tiên (Time-To-First-Audio cực thấp). |

---

## 4. Thiết kế Kiến trúc Chi tiết (Final Design)

### 4.1 Sơ đồ Luồng Dữ liệu (Data Flow Diagram)

```mermaid
flowgraph TD
    Client[Client Browser / Web Audio API] -->|WebSocket Binary Chunks| WS[FastAPI WebSocket Endpoint /ws/voice-stream]
    WS -->|Audio Queue| STT[GPU Faster-Whisper + Silero VAD]
    STT -->|Streamed STT Text| Gemini[Gemini Stream API]
    Gemini -->|Sentence Chunk Stream| TTS[Edge-TTS Async Stream Engine]
    TTS -->|Binary MP3 Chunks| Client
```

### 4.2 Chi tiết xử lý từng phần (Pipeline Details)

1. **Client Audio Stream (`index.html`):**
   * Thu âm bằng `AudioWorklet` / `MediaRecorder` và gửi audio chunk mỗi 200ms–300ms tới endpoint `/ws/voice-stream`.
2. **GPU STT Processing (`app/services/stt.py`):**
   * Sử dụng `faster-whisper` trên GPU CUDA (`float16`), phát hiện ngắt câu bằng VAD (`min_silence_duration_ms=250`).
3. **Gemini Streaming (`app/services/translation.py`):**
   * Sử dụng `client.models.generate_content_stream()`.
   * Bộ đệm câu (Sentence Buffer) đọc từng token và tự động ngắt vế/câu dựa trên dấu câu (`,`, `.`, `?`, `!`, `\n`).
4. **Parallel TTS & Audio Stream (`app/services/tts.py`):**
   * Gọi Edge-TTS tổng hợp song song từng vế câu và phát lại trực tiếp dưới dạng binary MP3 chunks qua kết nối WebSocket về phía Client.

---

## 5. Xử lý Lỗi & Trường hợp biên (Error Handling)
* **WebSocket Disconnect:** Server hủy các task `asyncio.Task` ngầm và dọn dẹp `asyncio.Queue` ngay khi client ngắt kết nối.
* **Gemini Timeout / Quota Limit:** Hạn chế timeout 5 giây, trả về thông báo lỗi JSON qua WebSocket nếu API quá tải.
* **Noise Filtering:** Tích hợp Silero VAD loại bỏ khoảng lặng/tiếng ồn môi trường trước khi đưa vào pipeline.
