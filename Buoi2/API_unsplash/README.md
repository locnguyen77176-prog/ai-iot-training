# 🖼️ Unsplash Image Search — Streamlit App

Ứng dụng tìm kiếm và hiển thị hình ảnh từ Unsplash API, được xây dựng bằng Python + Streamlit.

## ✨ Tính năng

| Tính năng | Chi tiết |
|-----------|----------|
| 🔍 Tìm kiếm | Hỗ trợ Tiếng Việt và Tiếng Anh |
| 🌐 Dịch tự động | Tiếng Việt → Tiếng Anh via deep-translator |
| 💾 SQLite Cache | TTL 10 phút, tránh gọi API lặp lại |
| 📊 Benchmark | Response time, nguồn dữ liệu, số kết quả |
| 🔄 Retry | 3 lần với exponential backoff (1s → 2s → 4s) |
| 🖼️ Grid 4 cột | Thumbnail + tên tác giả + nút tải ảnh gốc |

## 🗂️ Cấu trúc thư mục

`
API_unsplash/
├── app.py                    # Ứng dụng Streamlit chính
├── requirements.txt          # Các thư viện cần cài
├── .env.example              # Mẫu file cấu hình
├── .env                      # ⚠️ KHÔNG commit file này!
├── unsplash_cache.db         # SQLite DB (tự tạo khi chạy)
├── .gitignore
└── .streamlit/
    ├── config.toml           # Theme dark mode
    └── secrets.toml.example  # Mẫu secrets cho Streamlit Cloud
`

## 🚀 Hướng dẫn chạy Local

### Bước 1 — Cài thư viện
`ash
pip install -r requirements.txt
`

### Bước 2 — Cấu hình API Key
Tạo file .env (copy từ .env.example):
`
UNSPLASH_ACCESS_KEY=your_key_here
`
> Đăng ký miễn phí tại: https://unsplash.com/developers

### Bước 3 — Chạy ứng dụng
`ash
streamlit run app.py
`
Trình duyệt sẽ tự mở tại http://localhost:8501

## ☁️ Deploy lên Streamlit Cloud

1. Push code lên GitHub (đừng commit .env và *.db)
2. Vào [share.streamlit.io](https://share.streamlit.io) → New app
3. Trong **Settings → Secrets**, thêm:
`	oml
UNSPLASH_ACCESS_KEY = "your_key_here"
`

## 🔄 Quy trình xử lý dữ liệu

`
Người dùng nhập từ khóa
        ↓
[1] Dịch sang Tiếng Anh (deep-translator)
        ↓
[2] Kiểm tra SQLite Cache
   ├─ HIT (< 10 phút) → Đọc JSON từ DB → Hiển thị (⚡ nhanh)
   └─ MISS → Gọi Unsplash API (requests)
                ↓
            Parse JSON (chắt lọc fields)
                ↓
            Lưu vào SQLite Cache
                ↓
           Hiển thị kết quả
        ↓
[3] Benchmark: Response Time + Nguồn dữ liệu
`

## 📦 Thư viện sử dụng

| Thư viện | Mục đích |
|----------|----------|
| streamlit | Web UI framework |
| 
equests | Gọi Unsplash REST API |
| python-dotenv | Đọc API key từ file .env |
| deep-translator | Dịch Tiếng Việt → Tiếng Anh |
| sqlite3 | Cache database (built-in Python) |


đường dẫn:
https://loc2207.streamlit.app/