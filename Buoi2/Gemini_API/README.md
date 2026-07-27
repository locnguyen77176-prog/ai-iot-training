# Enterprise Gemini Chatbot CLI (`gemini_chatbot.py`)

Chatbot tương tác CLI chuẩn doanh nghiệp bằng Python, kết nối với Gemini API thông qua SDK chính thức `google-genai` (model `gemini-2.5-flash`).

## 🌟 Tính năng nổi bật
1. **Google GenAI SDK**: Sử dụng gói thư viện chính thức mới nhất `google-genai`.
2. **Quản lý API Key an toàn**: Nạp biến môi trường từ file `.env` qua `python-dotenv`.
3. **Robust Retry Logic**: Tích hợp `tenacity` với chiến lược Exponential Backoff (4 lần thử: 2s -> 4s -> 8s -> 10s) cho các lỗi transient (API 429/5xx, lỗi kết nối mạng).
4. **Latency Benchmarking**: Đo lường thời gian phản hồi theo miligiây (`ms`) chính xác bằng `time.perf_counter()`.
5. **System Instruction**: Persona **AIOT Assistant** trả lời ngắn gọn, cô đọng (tối đa 300 từ) và hỗ trợ định dạng Markdown.
6. **Xử lý lỗi chặt chẽ**: Phân loại ngoại lệ (`APIError`, `ConnectionError`, `ValueError`) và in log warning trực quan.

---

## 🛠️ Hướng dẫn cài đặt & Thao tác

### Bước 1: Cài đặt thư viện phụ thuộc
Mở Terminal hoặc Command Prompt và chạy lệnh:
```bash
pip install google-genai tenacity python-dotenv
```

### Bước 2: Tạo file cấu hình môi trường `.env`
Tạo file tên `.env` tại cùng thư mục với `gemini_chatbot.py` (hoặc copy từ `.env.example`):

```env
GEMINI_API_KEY=your_gemini_api_key_here
```
> *(Thay `your_gemini_api_key_here` bằng Gemini API Key thực tế của bạn từ Google AI Studio)*

### Bước 3: Khởi chạy Chatbot
Chạy chương trình bằng lệnh Python:
```bash
python gemini_chatbot.py
```

- Nhập câu hỏi và nhấn `Enter`.
- Gõ `exit` hoặc `quit` để thoát chương trình.
