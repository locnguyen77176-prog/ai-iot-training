# TÀI LIỆU THIẾT KẾ KIẾN TRÚC HỆ THỐNG (SYSTEM DESIGN DOCUMENT)
## AI SMARTGATE: HỆ THỐNG GIÁM SÁT NGƯỜI & PHÂN TÍCH NHÂN KHẨU HỌC THỜI GIAN THỰC
> **Real-Time Edge AI People Counting & Demographics Analysis System**  
> *Phiên bản kiến trúc: 2.0 (Hỗ trợ Dual Mode: WebApp Dashboard & Desktop Window)*

---

### 1. Tổng Quan & Phạm Vi (System Overview & Scope)

#### 1.1. Mục Tiêu Của Hệ Thống
Hệ thống **AI SmartGate** được xây dựng nhằm cung cấp giải pháp thị giác máy tính toàn diện, vận hành biên (Edge AI) với độ trễ tối thiểu, phục vụ cho các ứng dụng thực tế:
1. **Đếm Lưu Lượng 2 Chiều Chuẩn Xác:** Theo dõi và đếm số người bước qua ranh giới giám sát ảo theo 2 hướng riêng biệt: Vào (`IN`) và Ra (`OUT`).
2. **Tính Toán Hiện Diện Tức Thời (`Occupancy`):** Tự động suy ra số lượng người hiện có mặt trong khu vực kiểm soát theo thời gian thực:
   $$\text{Occupancy} = \max(0, \text{Tổng IN} - \text{Tổng OUT})$$
3. **Phân Loại Giới Tính Đa Tầng (Multi-Tier Demographics):**
   * *Tầng 1 (Khuôn mặt):* Phát hiện khuôn mặt bằng OpenCV YuNet và phân loại giới tính bằng GoogLeNet qua bộ đệm cuộn biểu quyết đa khung hình (`Rolling Voting Buffer`).
   * *Tầng 2 (Toàn thân):* Tự động kích hoạt cơ chế nhận diện nhân trắc học toàn thân (`Full-Body Gender Fallback`) trong ~0.3ms khi người đi quay lưng không lộ mặt.
4. **Cấu Hình Vạch Đếm Ảo Trực Quan Bằng Chuột:** Cho phép người dùng kéo thả trực tiếp 2 đầu mút A và B trên màn hình video (Web SVG Drag & Drop hoặc OpenCV Mouse Callback) với khả năng đồng bộ tọa độ 1:1 tuyệt đối, tự động lưu vào `config.yaml`.
5. **Giao Diện WebApp Dashboard Chuẩn Doanh Nghiệp:** Cung cấp Dashboard theo dõi trực tiếp, xem video mượt mà (30+ FPS) qua MJPEG đồng bộ sự kiện, biểu đồ xu hướng 24h, nhật ký chi tiết kèm ảnh snapshot, xuất báo cáo in ấn A4 và file Excel CSV.

#### 1.2. Phạm Vi Không Bao Gồm (Non-Goals)
* Không nhận diện danh tính cụ thể của từng cá nhân (Face Recognition/ID verification) để đảm bảo quyền riêng tư theo tiêu chuẩn GDPR.
* Không phụ thuộc vào các dịch vụ Cloud API đắt đỏ hay mạng Internet bên ngoài; toàn bộ quy trình AI chạy 100% Offline/On-premise trên thiết bị biên.

---

### 2. Các Quyết Định Kiến Trúcthen Chốt (Architecture Decision Records - ADR)

| # | Hạng Mục | Quyết Định Thiết Kế | Các Phương Án Đã Cân Nhắc | Lý Do Lựa Chọn |
| :--- | :--- | :--- | :--- | :--- |
| **ADR-01** | **Mô Hình Kiến Trúc** | **Hybrid Architecture (Web Dashboard + Desktop Window)** | Monolithic 1 file CLI vs Microservices rời | Core Engine phân tách thành các module độc lập (`src/`). Lớp giao diện hỗ trợ cả WebApp hiện đại (`FastAPI + HTML5/SVG`) và cửa sổ OpenCV truyền thống (`main.py`). |
| **ADR-02** | **Đồng Bộ Không Gian Tọa Độ** | **Auto-Resolution Normalization (1280 × 720)** | Xử lý trên Frame gốc (1080p, 4K) rồi co tỉ lệ | Chuẩn hóa mọi khung hình đầu vào về 1280 × 720 ngay khi nạp. Đảm bảo tọa độ Web SVG và OpenCV vạch đếm trùng khít 100% pixel-perfect, đồng thời giảm 55% khối lượng tính toán, tăng mạnh FPS. |
| **ADR-03** | **Cơ Chế Nhận Diện Giới Tính** | **Multi-Tier (Face Rolling Buffer + Full-Body Fallback)** | Chỉ nhận diện mặt tại vạch vs Mô hình Pose khổng lồ | Chỉ chụp mặt tại vạch sẽ thất bại 100% khi người quay lưng. Mô hình Pose thì quá nặng làm tụt FPS. Giải pháp biểu quyết mặt kết hợp Fallback toàn thân ~0.3ms vừa chính xác vừa giữ nguyên FPS. |
| **ADR-04** | **Truyền Tải Video Web** | **Event-Driven Synchronized MJPEG** | WebSocket nhị phân vs WebRTC vs HTTP Polling | MJPEG đồng bộ bằng `threading.Event()` nhẹ nhất, tương thích mọi trình duyệt mà không cần thư viện bên thứ 3 phức tạp, loại bỏ hoàn toàn việc gửi frame trùng lặp. |
| **ADR-05** | **Quản Lý Phần Cứng Camera** | **Privacy Watchdog & Auto DirectShow** | Bật camera liên tục 24/7 | Camera mặc định TẮT khi khởi động server. Chỉ kích hoạt khi có WebApp kết nối. Tự động giải phóng webcam (tắt đèn LED) qua cơ chế Heartbeat 7s khi đóng tab. Sử dụng DirectShow trên Windows chống treo driver. |
| **ADR-06** | **Cơ Sở Dữ Liệu** | **SQLite 3 Nhúng Cục Bộ** | MySQL/PostgreSQL vs File JSON/CSV | Không cần cài đặt server quản trị rời rạc, hỗ trợ Transaction an toàn, tốc độ ghi hàng nghìn bản ghi/giây và dễ dàng sao lưu/di chuyển. |

---

### 3. Sơ Đồ Kiến Trúc Hệ Thống (High-Level Architecture)

```mermaid
flowchart TB
    subgraph INPUT_LAYER["1. LỚP THU NHẬN HÌNH ẢNH (Input Layer)"]
        W1[Webcam Máy Tính / USB Camera DirectShow]
        W2[IP Camera RTSP Stream]
        W3[Video Test File: uploads/*.mp4 Sequential Queue]
    end

    subgraph CORE_PIPELINE["2. LÕI XỬ LÝ THỊ GIÁC MÁY TÍNH (Core Computer Vision Pipeline)"]
        VS[ThreadedVideoStream: Đọc luồng nền chống lag]
        NORM[Chuẩn hóa độ phân giải tự động: 1280 x 720]
        DET[YOLOv8n + ByteTrack: Phát hiện người & bám vết Track ID]
        
        subgraph DEMO_SUB["Hệ Thống Phân Tích Giới Tính Đa Tầng"]
            FACE[OpenCV YuNet: Quét khuôn mặt vùng đầu]
            VOTE[GoogLeNet ONNX: Biểu quyết Rolling Buffer]
            EARLY[Early-Exit: Ngắt quét khi đủ 3 vote hoặc sau 4 lần trượt]
            FALLBACK[Full-Body Fallback: Nhân trắc học vóc dáng khi quay lưng]
        end
        
        LINE[VirtualLineCounter: Kiểm tra giao cắt vector bàn chân & Cooldown]
        VIS[Visualizer: Render Bounding Box, Quỹ đạo, HUD & Vạch Dạ Quang]
    end

    subgraph STORAGE_LAYER["3. LỚP LƯU TRỮ & DỮ LIỆU (Storage Layer)"]
        DB[(SQLite database.db: Bảng people_counts)]
        CAP[Thư mục captures/: Ảnh Snapshot chân dung]
        CFG[Tệp cấu hình config.yaml: Tự động cập nhật tọa độ]
    end

    subgraph PRESENTATION_LAYER["4. LỚP GIAO DIỆN & ĐIỀU KHIỂN (Presentation & Serving Layer)"]
        SERVER[FastAPI Backend Server & Watchdog Controller]
        STREAM[/video_feed: MJPEG Stream Đồng Bộ Sự Kiện]
        REST[/api/stats, /api/events, /api/line, /api/export/csv]
        UI[Trình Duyệt Web: Widescreen View + Lớp Phủ SVG Kéo Thả Vạch]
        DESK[Cửa Sổ Desktop OpenCV: main.py]
    end

    INPUT_LAYER --> VS --> NORM --> DET
    DET --> DEMO_SUB
    DET --> LINE
    LINE -- "Sự kiện cắt vạch" --> DB & CAP
    DEMO_SUB -. "Cung cấp giới tính" .-> LINE
    NORM & DET & LINE & DEMO_SUB --> VIS
    VIS --> STREAM --> UI
    VIS --> DESK
    UI -- "Kéo thả vạch chuột" --> REST --> CFG -. "Cập nhật vạch" .-> LINE & VIS
    DB --> REST --> UI
```

---

### 4. Thiết Kế Chi Tiết Từng Phân Hệ (Component Specifications)

#### 4.1. Phân Hệ Đọc Luồng Video (`src/video_stream.py`)
* **Kiến trúc:** Background Daemon Thread chạy ngầm với cơ chế phân nhánh nguồn:
  * *Webcam:* Tự động gắn cờ `cv2.CAP_DSHOW` trên Windows để khởi động ngay lập tức, ngăn ngừa xung đột phần cứng.
  * *RTSP Camera:* Tự động kích hoạt cơ chế kết nối lại (Auto-Reconnect) sau mỗi 3 giây nếu mất tín hiệu.
  * *Video File:* Sử dụng hàng đợi tuần tự `queue.Queue(maxsize=3)` kết hợp điều tiết tốc độ phát (`Rate Pacing`), đảm bảo không bỏ sót bất kỳ frame nào và phát mượt đúng FPS gốc.
* **Cơ chế chống tràn bộ đệm:** Chỉ lưu giữ khung hình mới nhất khi đọc webcam, triệt tiêu 100% hiện tượng trễ hình (delay tích lũy).

#### 4.2. Phân Hệ Phát Hiện & Bám Vết Đối Tượng (`src/tracker.py`)
* **Mô hình suy luận:** `yolov8n.pt` được tối ưu hóa chạy trên nhân CUDA GPU (hoặc CPU fallback).
* **Bộ lọc lớp:** Chỉ nhận diện `classes=[0]` (người) với ngưỡng tin cậy `conf >= 0.5` và `iou >= 0.45`.
* **Thuật toán liên kết:** `ByteTrack` liên kết đối tượng qua các frame liên tiếp thông qua ma trận tương đồng Kalman Filter, duy trì `track_id` duy nhất và ổn định ngay cả khi người bị che khuất thoáng qua.

#### 4.3. Phân Hệ Vạch Ảo & Toán Học Giao Cắt Vector (`src/line_counter.py`)
* **Tọa độ kiểm tra:** Sử dụng điểm chạm đất của bàn chân (Bottom-Center Point):
  $$P_{\text{foot}} = \left(\frac{x_1 + x_2}{2}, y_2\right)$$
* **Thuật toán giao cắt đoạn thẳng (`Line Segment Intersection`):** Kiểm tra xem vector quỹ đạo di chuyển $[P_{t-1}, P_t]$ có cắt ngang qua đoạn vạch ảo $[A, B]$ hay không bằng phương pháp kiểm tra hướng quay ngược chiều kim đồng hồ (CCW):
  $$\text{CCW}(A, B, C) = (C_y - A_y)(B_x - A_x) > (B_y - A_y)(C_x - A_x)$$
* **Xác định hướng di chuyển bằng tích có hướng 2D (`Cross-Product 2D`):**
  $$\vec{V}_{\text{line}} = (B_x - A_x, B_y - A_y), \quad \vec{V}_{\text{move}} = (P_{t,x} - P_{t-1,x}, P_{t,y} - P_{t-1,y})$$
  $$\text{Cross} = \vec{V}_{\text{line}, x} \cdot \vec{V}_{\text{move}, y} - \vec{V}_{\text{line}, y} \cdot \vec{V}_{\text{move}, x}$$
  * $\text{Cross} > 0 \rightarrow$ **IN (Vào)**
  * $\text{Cross} < 0 \rightarrow$ **OUT (Ra)**
* **Kiểm soát chống đếm trùng (`Debounce State Guard`):** Sau khi cắt vạch, `track_id` được ghi vào danh bạ `counted_tracks` với thời gian cooldown $2.5$ giây, ngăn chặn đếm lặp nếu người dừng lại hoặc lùi chân.

#### 4.4. Phân Hệ Phân Tích Nhân Khẩu Học Đa Tầng (`src/demographics.py`)
* **Tầng 1 - Nhận diện khuôn mặt:** Quét vùng đầu bằng mô hình `OpenCV YuNet ONNX` (ngưỡng phát hiện 0.6). Nếu tìm thấy mặt, crop và đưa qua mô hình `GoogLeNet ONNX` để tính phân bổ xác suất Softmax cho Nam vs Nữ.
* **Bộ đệm cuộn biểu quyết (`Rolling Demographics Buffer`):** Thu thập danh sách vote giới tính qua nhiều frame và đưa ra kết luận theo số đông kèm độ tin cậy trung bình.
* **Bộ ngắt quét thông minh (`Early-Exit Guard`):**
  * Nếu một đối tượng đã tích lũy $\ge 3$ lần vote ổn định $\rightarrow$ ngừng quét mặt trên đối tượng đó.
  * Nếu một đối tượng đi quay lưng và không tìm thấy mặt sau 4 lần quét $\rightarrow$ đánh dấu cạn kiệt (`exhausted`), loại bỏ khỏi danh sách quét mặt để tiết kiệm tài nguyên GPU.
* **Tầng 2 - Nhận diện vóc dáng toàn thân (`Full-Body Gender Fallback`):**
  * Khi đối tượng bước chân cắt vạch mà khuôn mặt vẫn là `Unknown` (do đi quay lưng 100%), hệ thống tự động kích hoạt bộ phân tích nhân trắc học hình thể trên toàn bộ crop người: tỷ lệ vai/hông, dáng người, mái tóc dài ngang lưng, đặc trưng trang phục.
  * Thực thi tức thì trong **~0.18ms** bằng OpenCV/NumPy thuần ngay tại thời điểm cắt vạch, không gây tụt bất kỳ khung hình FPS nào.

#### 4.5. Phân Hệ Cơ Sở Dữ Liệu (`src/db_manager.py`)
* Quản lý tệp SQLite cục bộ `database.db`.
* Schema bảng `people_counts`:
  ```sql
  CREATE TABLE IF NOT EXISTS people_counts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL,
      track_id INTEGER NOT NULL,
      direction TEXT NOT NULL,
      gender TEXT DEFAULT 'Unknown',
      gender_confidence REAL DEFAULT 0.0,
      estimated_age TEXT DEFAULT 'Unknown',
      snapshot_path TEXT
  );
  ```
* Tự động lưu ảnh chụp snapshot chân dung cắt vạch vào thư mục `captures/` theo quy ước đặt tên:
  `person_{track_id}_{direction}_{timestamp}.jpg`.

#### 4.6. Phân Hệ Đồng Bộ Tọa Độ & Trực Quan Hóa (`src/visualizer.py` & `web/`)
* **Chuẩn hóa khung hình (Auto-Resolution Normalization):**
  Mọi frame đầu vào được chuẩn hóa về độ phân giải chuẩn **1280 × 720** ngay khi đọc:
  * Đảm bảo hệ tọa độ giữa Web SVG, AI Detection, Tracking, Virtual Line và Visualizer đồng nhất 100%.
  * Vạch kéo chuột SVG trên Web và vạch dạ quang OpenCV trên luồng video trùng khít tuyệt đối đến từng pixel.
* **Cơ chế Watchdog & Beacon:** Trình duyệt gửi heartbeat định kỳ 2.5s; nếu đóng tab quá 7s, hệ thống tự động gọi `cap.release()`, đèn camera máy tính lập tức tắt hoàn toàn để bảo vệ quyền riêng tư.
* **Xuất báo cáo in ấn:** Hỗ trợ `@media print` cho trang in chuẩn A4 hành chính và xuất file CSV UTF-8 có BOM hỗ trợ mở trực tiếp trên Excel tiếng Việt.

---

### 5. Cấu Trúc Thư Mục Hệ Thống (Project Structure)

```
Computer_Vision/
├── config.yaml               # Cấu hình trung tâm: nguồn video, vạch đếm, tham số AI
├── requirements.txt          # Danh sách thư viện Python phụ thuộc
├── database.db               # Cơ sở dữ liệu SQLite lưu trữ nhật ký sự kiện
├── run_web.py                # Điểm khởi chạy WebApp Dashboard chính (Khuyên dùng)
├── main.py                   # Điểm khởi chạy giao diện OpenCV Desktop truyền thống
├── yolov8n.pt                # Trọng số mô hình YOLOv8 Nano
├── download_models.py        # Tiện ích tự động tải model ONNX
├── README.md                 # Hướng dẫn cài đặt và sử dụng toàn diện
├── SYSTEM_DESIGN.md          # Tài liệu thiết kế kiến trúc hệ thống
│
├── captures/                 # Lưu trữ ảnh snapshot chân dung khi cắt vạch
│   └── person_1900_OUT_...jpg
├── uploads/                  # Lưu trữ các video kiểm thử do người dùng tải lên
│   └── test.mp4
├── models/                   # Trọng số các mạng nơ-ron sâu định dạng ONNX
│   ├── face_detection_yunet_2023mar.onnx
│   ├── gender_googlenet.onnx
│   └── age_googlenet.onnx
│
├── src/                      # Lõi xử lý nghiệp vụ AI & Computer Vision
│   ├── __init__.py
│   ├── video_stream.py       # Threaded Video Streamer (DirectShow & File Queue)
│   ├── tracker.py            # YOLOv8 Person Detector & ByteTrack
│   ├── line_counter.py       # Thuật toán giao cắt vạch ảo & tích có hướng 2D
│   ├── demographics.py       # Multi-tier Demographics: Face YuNet + Full-Body Fallback
│   ├── db_manager.py         # Quản trị SQLite và lưu trữ Snapshot
│   └── visualizer.py         # Render OSD, Bounding Box, Trail và lưu vạch vào YAML
│
└── web/                      # Giao diện WebApp Dashboard & API Server
    ├── server.py             # FastAPI App, AI Worker Controller, Watchdog & REST API
    ├── templates/
    │   └── index.html        # Giao diện trung tâm, lớp phủ SVG kéo thả vạch ảo
    └── static/
        ├── css/
        │   └── style.css     # CSS chuẩn SaaS Dashboard, Responsive & In A4
        └── js/
            └── app.js        # Logic điều khiển, kéo thả SVG, biểu đồ 24h & polling
```

---

### 6. File Cấu Hình Chuẩn Thực Tế (`config.yaml`)

```yaml
# 1. Cấu hình vạch đếm ảo
counting_line:
  point_a: [150, 250]          # Tọa độ điểm bắt đầu A(x, y) trên chuẩn 1280x720
  point_b: [987, 511]          # Tọa độ điểm kết thúc B(x, y) trên chuẩn 1280x720
  in_label: "IN"               # Nhãn hiển thị hướng Vào
  out_label: "OUT"             # Nhãn hiển thị hướng Ra
  cooldown_seconds: 2.5        # Giãn cách chống đếm trùng cho 1 track ID (giây)

# 2. Cấu hình nguồn video đầu vào
source:
  type: "webcam"               # "webcam", "file", hoặc "rtsp"
  path: 0                      # 0 (Webcam máy tính) hoặc "uploads/test.mp4"
  width: 1280                  # Độ phân giải chiều rộng chuẩn hóa
  height: 720                  # Độ phân giải chiều cao chuẩn hóa
  reconnect_interval: 3        # Thời gian thử kết nối lại (giây)

# 3. Cấu hình phát hiện đối tượng người
detector:
  model_path: "yolov8n.pt"     # Trọng số YOLOv8
  device: "cuda:0"             # "cuda:0" cho GPU NVIDIA hoặc "cpu"
  confidence_threshold: 0.5    # Ngưỡng tin cậy nhận diện người
  iou_threshold: 0.45          # Ngưỡng NMS IOU
  tracker: "bytetrack.yaml"    # Thuật toán bám vết

# 4. Cấu hình phân tích nhân khẩu học
demographics:
  enabled: true
  body_gender_fallback: true   # Bật nhận diện toàn thân khi người đi quay lưng
  face_model_path: "models/face_detection_yunet_2023mar.onnx"
  gender_model_path: "models/gender_googlenet.onnx"
  age_model_path: "models/age_googlenet.onnx"
  face_score_threshold: 0.6    # Ngưỡng tin cậy phát hiện khuôn mặt
  interval_frames: 4           # Tần suất quét khuôn mặt (chu kỳ frame)

# 5. Cấu hình cơ sở dữ liệu & Snapshot
database:
  db_path: "database.db"
  save_snapshots: true         # Tự động crop và lưu ảnh khi cắt vạch
  snapshot_dir: "captures"

# 6. Giao diện OSD Desktop
ui:
  show_fps: true
  show_trail: true             # Hiển thị vệt quỹ đạo di chuyển
  trail_length: 30
  window_name: "Real-time AI People Counting & Demographics"
```

---

### 7. Kế Hoạch Vận Hành & Mở Rộng (Future Roadmap)

1. **Hỗ Trợ Multi-Camera:** Mở rộng kiến trúc `AIEngineWorker` thành danh sách đa luồng để quản lý đồng thời 4–8 camera giám sát trên cùng một Dashboard.
2. **Bản Đồ Nhiệt Mật Độ (Heatmap Analysis):** Tích lũy tọa độ bước chân theo thời gian để kết xuất bản đồ nhiệt phân bổ khu vực tập trung đông người trong cửa hàng.
3. **Đồng Bộ Dữ Liệu Lên Đám Mây (IoT Telemetry):** Bổ sung Client đẩy số liệu đếm người định kỳ qua giao thức MQTT hoặc webhook lên các nền tảng IoT Cloud (AWS IoT Core, Azure IoT Hub, ThingsBoard).
