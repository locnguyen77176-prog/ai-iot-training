# AI Camera đếm người — SmartGate AI

Hệ thống thị giác máy tính đếm người ra/vào theo thời gian thực bằng **YOLO26n + FASTTracker/Kalman + OSNet + Dual-Zone FSM**. Hệ thống nhận camera hoặc video, theo dõi người bằng ID ẩn danh, chỉ tạo sự kiện khi một người hoàn thành hành trình qua hai vùng và hiển thị kết quả trên Web Dashboard.

> Trạng thái hiện tại: prototype end-to-end cho một camera tại một lối ra/vào. Hệ thống đã có kiểm thử chức năng, benchmark hiệu suất và một bộ ground truth thủ công 96 hành trình; chưa được xác nhận cho vận hành thương mại 24/7.

## Mục lục

1. [Bài toán và phạm vi](#bài-toán-và-phạm-vi)
2. [Tính năng hiện tại](#tính-năng-hiện-tại)
3. [Kiến trúc và luồng dữ liệu](#kiến-trúc-và-luồng-dữ-liệu)
4. [Cơ chế đếm Dual-Zone](#cơ-chế-đếm-dual-zone)
5. [Thiết kế xử lý thời gian thực](#thiết-kế-xử-lý-thời-gian-thực)
6. [Cài đặt và vận hành](#cài-đặt-và-vận-hành)
7. [Cấu hình](#cấu-hình)
8. [Dữ liệu và quyền riêng tư](#dữ-liệu-và-quyền-riêng-tư)
9. [REST API](#rest-api)
10. [Kiểm thử và kết quả hiện tại](#kiểm-thử-và-kết-quả-hiện-tại)
11. [Giới hạn đã biết](#giới-hạn-đã-biết)
12. [Cấu trúc dự án](#cấu-trúc-dự-án)
13. [Khắc phục sự cố](#khắc-phục-sự-cố)

## Bài toán và phạm vi

SmartGate AI hướng đến việc tự động thống kê lưu lượng tại cửa ra/vào, nơi phương pháp dùng một vạch ảo đơn có thể đếm lặp khi người đứng gần cửa, quay đầu hoặc bounding box dao động quanh ranh giới.

Phạm vi phiên bản hiện tại:

- Một camera cố định giám sát một lối ra/vào.
- Chỉ xử lý lớp `person`.
- Đếm hai chiều bằng thứ tự đi qua hai vùng ROI: `A → B = IN`, `B → A = OUT`.
- Stable ID là mã ẩn danh phục vụ tracking, không phải danh tính thật.
- Không nhận diện khuôn mặt, tên, giới tính hoặc độ tuổi.
- Không tự động ghi hoặc lưu video camera trực tiếp.
- Chưa hỗ trợ tracking xuyên nhiều camera.

## Tính năng hiện tại

- Phát hiện người bằng trọng số pretrained `models/yolo26n.pt`.
- FASTTracker và Kalman duy trì Local ID trong khoảng mất dấu ngắn.
- OSNet x0.25 trích xuất embedding 512 chiều và hỗ trợ nối Local ID mới về Stable ID cũ.
- Identity Manager có gallery nhiều mẫu, loại track trùng và có cơ chế sửa Stable ID đến trễ.
- Dual-Zone FSM xác định IN/OUT và khóa đối tượng sau khi đếm.
- Xác nhận vùng qua nhiều frame để giảm nhiễu tại biên ROI.
- Hỗ trợ webcam USB, camera index, nguồn mạng RTSP/HTTP(S) và video kiểm thử.
- Chuẩn hóa frame về `1280×720`.
- Camera live dùng chiến lược latest-frame để hạn chế tích lũy độ trễ.
- Video file được đọc tuần tự và tự lặp khi kết thúc.
- Web Dashboard hiển thị MJPEG, KPI trong ngày, biểu đồ 24 giờ và lịch sử sự kiện.
- Kéo thả hai vùng ROI trên Dashboard và lưu vào `config.yaml`.
- Bật/tắt camera, đổi nguồn, tải video kiểm thử và xóa lịch sử.
- Xuất báo cáo Excel gồm tổng quan, thống kê 24 giờ và biểu đồ.
- Ưu tiên CUDA; tự chuyển sang CPU nếu CUDA không khả dụng.

## Kiến trúc và luồng dữ liệu

```mermaid
flowchart TD
    A[Camera USB / RTSP / HTTP / Video] --> B[ThreadedVideoStream]
    B --> C[Frame 1280x720]
    C --> D[YOLO26n: bbox + confidence]
    D --> E[FASTTracker + Kalman: Local ID]
    E --> F[OSNet + Identity Manager: Stable ID]
    F --> G[Dual-Zone FSM: trạng thái A/B]
    G -->|A → B hoặc B → A| H[Sự kiện IN/OUT]
    H --> I[(SQLite database.db)]
    I --> J[REST API / Excel]
    C --> K[Visualizer]
    F --> K
    G --> K
    K --> L[JPEG encoder]
    L --> M[MJPEG /video_feed]
    J --> N[Web Dashboard]
    M --> N
```

Dữ liệu được biến đổi theo chuỗi:

```text
Frame → Bounding box → Local ID → Stable ID → Trạng thái vùng → Sự kiện IN/OUT
```

Hai nhánh đầu ra độc lập:

- **Nhánh nghiệp vụ:** sự kiện IN/OUT được ghi vào SQLite và dùng cho thống kê/báo cáo.
- **Nhánh hiển thị:** frame được vẽ overlay, nén JPEG và giữ tạm trong RAM để stream lên trình duyệt.

## Cơ chế đếm Dual-Zone

### Điểm neo bước chân

Vị trí người được biểu diễn bởi điểm giữa cạnh dưới bounding box:

```text
P_feet = ((x1 + x2) / 2, y2)
```

`cv2.pointPolygonTest()` xác định điểm này thuộc vùng A, vùng B hay ngoài cả hai vùng.

### Máy trạng thái thực tế

```text
NONE → IN_A → LOCKED_IN
NONE → IN_B → LOCKED_OUT
```

- `A → B`: tạo một sự kiện `IN`.
- `B → A`: tạo một sự kiện `OUT`.
- Vùng chỉ được công nhận sau `min_zone_hits` frame liên tiếp; cấu hình hiện tại là 2.
- Sau khi tạo sự kiện, track chuyển sang trạng thái khóa.
- Track chỉ trở lại `NONE` khi đã ra ngoài cả hai vùng và hết `cooldown_seconds`; hiện tại là 3 giây.
- Trạng thái FSM được giữ tối đa theo `state_ttl_seconds`; hiện tại là 120 giây để hỗ trợ hoàn thành hành trình sau mất dấu tạm thời.
- Khi Identity Manager sửa một Stable ID tạm, trạng thái FSM và lịch sử quỹ đạo được hợp nhất sang ID đúng.

`Occupancy` trên Dashboard được ước tính theo:

```text
max(0, tổng IN trong ngày - tổng OUT trong ngày)
```

Đây là giá trị ước tính. Nếu hệ thống khởi động khi bên trong đã có người hoặc trước đó có sự kiện sai, occupancy không tự biết số người ban đầu.

## Thiết kế xử lý thời gian thực

Hệ thống tách ba công việc chính:

1. **Capture thread:** đọc camera/video và chuẩn hóa frame.
2. **AI worker:** detection, tracking, Re-ID và counting.
3. **Render thread:** vẽ overlay và nén JPEG cho Dashboard.

Với camera live, nếu AI không theo kịp tốc độ nguồn, hệ thống lấy frame mới nhất thay vì giữ một hàng đợi dài. FASTTracker được tiến Kalman thêm theo số frame hoặc thời gian bị bỏ qua. Thiết kế này ưu tiên độ trễ thấp, chấp nhận bỏ một số frame trung gian.

Với video file, `ThreadedVideoStream` dùng hàng đợi và AI worker giữ nhịp theo timeline của file để phục vụ kiểm thử có thể lặp lại.

## Cài đặt và vận hành

### Yêu cầu

- Python 3.10 trở lên.
- Windows, Linux hoặc macOS có OpenCV hỗ trợ nguồn video tương ứng.
- GPU NVIDIA là tùy chọn; CPU vẫn chạy được nhưng chậm hơn.
- Hai file trọng số:
  - `models/yolo26n.pt`
  - `models/osnet_x0_25_msmt17.pth`
- Trên Windows, chế độ `source.path: auto_usb` cần FFmpeg trong `PATH` để liệt kê và chọn camera USB vật lý, đồng thời bỏ qua camera tích hợp/ảo. Nếu không dùng FFmpeg, đặt camera index cụ thể như `0` hoặc `1`.

### Cài thư viện

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu dùng CUDA, cài bản PyTorch tương thích với driver/CUDA của máy trước khi chạy.

### Chạy Web Dashboard — khuyến nghị

```powershell
python run_web.py
```

Mở:

```text
http://localhost:8000
```

Camera và AI worker tự khởi động cùng server. Nhấn `Ctrl+C` trong terminal để dừng toàn bộ hệ thống.

Quy trình vận hành:

1. Kết nối camera hoặc chuẩn bị video kiểm thử.
2. Chạy `python run_web.py`.
3. Mở `http://localhost:8000`.
4. Chọn nguồn camera/video.
5. Hiệu chỉnh vùng A/B và kiểm tra hướng IN/OUT.
6. Theo dõi KPI, sự kiện và biểu đồ.
7. Xuất Excel hoặc xóa lịch sử khi bắt đầu chu kỳ mới.

### Chạy cửa sổ OpenCV độc lập

```powershell
python main.py
```

Ghi đè nguồn video:

```powershell
python main.py --source 0
python main.py --source uploads\video.mp4
python main.py --source rtsp://user:password@host/stream
```

Phím tắt:

- `q` hoặc `Esc`: thoát.
- `r`: reset bộ đếm FSM trong bộ nhớ; không xóa lịch sử SQLite.

## Cấu hình

Nguồn cấu hình chuẩn là [`config.yaml`](config.yaml). Các giá trị đáng chú ý hiện tại:

| Nhóm | Tham số | Giá trị hiện tại | Ý nghĩa |
|---|---|---:|---|
| Detector | `model_path` | `models/yolo26n.pt` | Trọng số phát hiện người |
| Detector | `device` | `cuda:0` | Tự fallback CPU nếu CUDA không có |
| Detector | `confidence_threshold` | `0.25` | Ngưỡng confidence YOLO |
| Detector | `iou_threshold` | `0.60` | Ngưỡng IoU của detector |
| Detector | `imgsz` | `640` | Kích thước suy luận YOLO |
| Tracker | `tracker` | `custom_fasttrack.yaml` | Cấu hình FASTTracker |
| Identity | `identity_memory_seconds` | `40` | Thời gian giữ hồ sơ ID không hoạt động |
| Re-ID | `reid_similarity_threshold` | `0.78` | Ngưỡng embedding OSNet |
| Re-ID | `reid_ambiguity_margin` | `0.0` | Không yêu cầu khoảng cách giữa hai ứng viên; giảm đếm thiếu nhưng tăng rủi ro nối nhầm |
| Re-ID | `reid_min_confidence` | `0.55` | Confidence tối thiểu để lấy crop |
| Re-ID | `reid_min_bbox_height` | `100` | Chiều cao bbox tối thiểu để lấy crop |
| Re-ID | `reid_max_per_frame` | `4` | Giới hạn crop OSNet mỗi frame |
| Source | `path` | `auto_usb` | Tự chọn camera USB vật lý trên Windows |
| Source | `width`, `height` | `1280`, `720` | Độ phân giải chuẩn hóa |
| Source | `target_fps` | `15` | FPS yêu cầu từ camera; driver có thể không chấp nhận đúng giá trị này |
| Source | `reconnect_interval` | `3` | Chu kỳ thử kết nối lại, tính bằng giây |
| Source | `anti_glare.enabled` | `false` | Tiền xử lý chống chói hiện đang tắt |
| Zones | `min_zone_hits` | `2` | Số frame liên tiếp để xác nhận vùng |
| Zones | `cooldown_seconds` | `3.0` | Thời gian khóa tối thiểu sau khi đếm |
| Zones | `state_ttl_seconds` | `120.0` | Thời gian giữ trạng thái FSM khi mất dấu |

Tọa độ ROI trong `config.yaml` dùng canvas `1280×720`. Dashboard có thể thay đổi chúng bằng `POST /api/zones`.

## Dữ liệu và quyền riêng tư

### Dữ liệu được lưu lâu dài

Bảng SQLite `people_counts`:

```sql
CREATE TABLE IF NOT EXISTS people_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    gender TEXT DEFAULT 'Unknown',
    gender_confidence REAL DEFAULT 0.0,
    estimated_age TEXT DEFAULT 'Unknown'
);
```

Pipeline hiện chỉ dùng các trường:

- `timestamp`
- `track_id` — Stable ID ẩn danh trong phiên/bộ nhớ
- `direction` — `IN` hoặc `OUT`

Các cột giới tính và tuổi là cột tương thích schema cũ; pipeline hiện ghi `N/A` và không có mô hình suy luận giới tính/tuổi.

### Dữ liệu không tự động lưu

- Frame camera trực tiếp.
- Ảnh khuôn mặt hoặc crop từng người.
- Embedding OSNet.
- Quỹ đạo và trạng thái tracking sau khi tiến trình kết thúc.

Frame JPEG mới nhất và embedding chỉ tồn tại tạm thời trong RAM. Video do người dùng chủ động tải lên để kiểm thử được lưu trong `uploads/`.

## REST API

| Method | Endpoint | Chức năng |
|---|---|---|
| `GET` | `/` | Trang Dashboard |
| `GET` | `/video_feed` | Stream MJPEG; trả frame chờ khi AI chưa hoạt động |
| `GET` | `/api/camera/status` | Trạng thái camera, nguồn, AI FPS, display FPS và CUDA |
| `POST` | `/api/camera/start` | Bật camera/AI worker |
| `POST` | `/api/camera/stop` | Dừng worker và giải phóng camera |
| `POST` | `/api/camera/heartbeat` | Trả trạng thái capture cho tab Web đang mở |
| `POST` | `/api/upload_video` | Tải video kiểm thử và chuyển ngay sang video đó |
| `GET` | `/api/videos` | Danh sách video trong `uploads/` |
| `POST` | `/api/set_source` | Chuyển giữa webcam và video đã tải lên |
| `GET` | `/api/stats` | KPI trong ngày, thống kê 24 giờ và trạng thái hệ thống |
| `GET` | `/api/events` | Sự kiện mới nhất; hỗ trợ `limit` và lọc `direction=IN|OUT` |
| `GET` | `/api/zones` | Lấy tọa độ hai ROI |
| `POST` | `/api/zones` | Cập nhật ROI và lưu vào `config.yaml` |
| `POST` | `/api/reset_counts` | Reset trạng thái/bộ đếm trong RAM, không xóa SQLite |
| `POST` | `/api/clear_history` | Xóa toàn bộ `people_counts` và reset trạng thái đếm |
| `GET` | `/api/export/excel` | Xuất báo cáo `.xlsx` từ toàn bộ lịch sử SQLite |
| `GET` | `/api/export/csv` | Alias tương thích; hiện cũng trả file Excel `.xlsx` |

Lưu ý: `in_percentage`, `out_percentage` và `occupancy_trend` trong phản hồi `/api/stats` hiện là giá trị giao diện mẫu, chưa được tính từ dữ liệu lịch sử. Không dùng ba trường này làm số liệu đánh giá.

## Kiểm thử và kết quả hiện tại

### Unit/regression tests

```powershell
python -m pytest -q
```

Kết quả kiểm tra gần nhất: **28/28 test đạt**. Test hiện tập trung vào:

- Chọn camera USB và fallback backend trên Windows.
- Latest-frame, stale frame, RTSP timeout và flip camera.
- Tiền xử lý chống chói.
- Kalman khi bỏ frame.
- Loại track trùng.
- Persistent Stable ID và OSNet Re-ID.
- Gallery, ambiguous match và sửa ID đến trễ.
- Bảo toàn FSM sau mất dấu/remap.
- Chống nhiễu vùng một frame.

Đây không phải là bằng chứng vận hành 24/7 hoặc accuracy trên mọi điều kiện.

### Ground truth đếm người

Bảng đánh giá thủ công hiện tại:

| Chỉ số | IN | OUT | Tổng |
|---|---:|---:|---:|
| Hành trình thực tế | 41 | 55 | 96 |
| Đếm đúng | 40 | 51 | 91 |
| Đếm thiếu | 1 | 4 | 5 |
| Đếm thừa | 0 | 0 | 0 |
| Sai hướng | 0 | 0 | 0 |
| Tỷ lệ hành trình đếm đúng | 97,56% | 92,73% | 94,79% |

Với `TP=91`, `FP=0`, `FN=5`:

- Precision: `100%`
- Recall: `94,79%`
- F1-score: `97,33%`

Các chỉ số trên đánh giá **sự kiện đếm cuối pipeline**, không phải mAP của YOLO hay metric MOT của tracker. Để kết quả có thể kiểm tra lại, cần lưu kèm video gốc, bảng timestamp/hướng ground truth, bảng sự kiện AI và quy tắc ghép thời gian đã dùng.

### Benchmark mô phỏng camera 720p/15 FPS

| Chỉ số | Kịch bản 1 | Kịch bản 2 |
|---|---:|---:|
| Người trung bình/tối đa mỗi frame | 19,05 / 30 | 40,94 / 56 |
| AI FPS hiệu dụng | 14,998 | 14,980 |
| Độ trễ AI trung bình | 34,53 ms | 39,98 ms |
| Độ trễ AI P95 | 48,86 ms | 53,74 ms |
| Frame bị bỏ | 0% | 0,13% |

Chi tiết: [`benchmark_results/C270_REALTIME_BENCHMARK.md`](benchmark_results/C270_REALTIME_BENCHMARK.md).

### Quan sát camera thực tế

- AI FPS trên HUD khoảng `9,7–10,2 FPS`, thấp hơn mục tiêu cấu hình 15 FPS.
- Không thấy crash trong hai bản ghi quan sát dài 100,5 giây và 401,7 giây.
- Cảnh đông có các đoạn khựng ngắn 0,20–0,43 giây và sau đó tự tiếp tục.
- Chưa đo chính xác latency camera-to-browser, RAM hoặc VRAM từ các bản ghi này.

Chi tiết: [`benchmark_results/REALTIME_REVIEW_TEST1_TEST2.md`](benchmark_results/REALTIME_REVIEW_TEST1_TEST2.md).

## Giới hạn đã biết

- Ground truth hiện có 96 hành trình, chưa bao phủ đầy đủ mọi điều kiện triển khai.
- Người mặc giống nhau có thể khiến OSNet nối nhầm Stable ID.
- `reid_ambiguity_margin: 0.0` ưu tiên giảm đếm thiếu nhưng tăng rủi ro nối nhầm.
- Crop thấp hơn 100 px hoặc confidence dưới 0.55 không được dùng cho OSNet.
- Tối đa bốn crop OSNet mỗi frame; cảnh có nhiều ID mới có thể làm Re-ID bị trì hoãn.
- Ánh sáng mạnh, bóng sâu, motion blur, mép ảnh và che khuất dài vẫn có thể gây mất detection hoặc phân mảnh ID.
- ROI đặt sai, chồng nhau hoặc không phủ hết lối đi có thể làm sai hướng/thiếu sự kiện.
- FSM chưa kiểm tra đầy đủ tính liên tục vật lý khi Stable ID bị nối nhầm giữa hai vùng.
- Camera thật hiện quan sát khoảng 10 FPS, chưa đạt mục tiêu 15 FPS.
- Chưa có thử nghiệm 24/7, telemetry RAM/VRAM dài hạn hoặc bài thử rút/cắm lại camera.
- Occupancy cần được hiệu chỉnh đầu ca và không tự biết số người đã ở bên trong trước khi hệ thống chạy.
- FastAPI hiện cho phép CORS `*` và chưa có xác thực; chỉ phù hợp mạng tin cậy trong giai đoạn prototype.

## Cấu trúc dự án

```text
Computer_Vision/
├── src/
│   ├── db_manager.py          # Ghi sự kiện vào SQLite
│   ├── osnet_reid.py          # OSNet x0.25, embedding 512-D
│   ├── tracker.py             # YOLO + FASTTracker + Persistent Identity
│   ├── video_stream.py        # Capture thread, nguồn live/file, reconnect
│   ├── visualizer.py          # ROI, bbox, trail và HUD
│   └── zone_counter.py        # Dual-Zone FSM
├── web/
│   ├── server.py              # FastAPI, AI worker, API, MJPEG, Excel
│   ├── static/css/style.css
│   ├── static/js/app.js
│   └── templates/index.html
├── models/
│   ├── osnet_x0_25_msmt17.pth
│   ├── yolo26n.pt
│   ├── osnet_x0_25_ncnn_model/   # OSNet NCNN FP32, input 256x128
│   ├── yolo26n_ncnn_model/       # YOLO26n NCNN FP32 baseline, input 640x640
│   ├── yolo26n_ncnn_int8/        # YOLO26n NCNN INT8 baseline, input 640x640
│   ├── yolo26n_320_ncnn_int8/    # YOLO26n NCNN INT8 cho Pi, input 320x320
│   └── NCNN_EXPORT.md             # Manifest và SHA-256 các artifact NCNN
├── uploads/                   # Video kiểm thử do người dùng tải lên
├── benchmark_results/         # Báo cáo benchmark/đánh giá
├── config.yaml                # Cấu hình runtime và ROI
├── custom_fasttrack.yaml      # Cấu hình tracker
├── database.db                # SQLite runtime
├── main.py                    # Chế độ OpenCV độc lập
├── run_web.py                 # Khởi chạy Dashboard
├── benchmark_mot.py
├── benchmark_realtime_camera.py
├── seed_demo_data.py
├── test_tracking.py
├── test_video_stream.py
└── requirements.txt
```

## Khắc phục sự cố

### `auto_usb` không tìm thấy camera

- Cài FFmpeg và bảo đảm lệnh `ffmpeg` có trong `PATH`.
- Đóng Zoom, Teams, OBS hoặc ứng dụng đang giữ camera.
- Hoặc đặt trực tiếp `source.path: 0`/`1` trong `config.yaml`.
- `auto_usb` chủ ý bỏ qua camera tích hợp và camera ảo trên Windows.

### CUDA không hoạt động

- Kiểm tra `python -c "import torch; print(torch.cuda.is_available())"`.
- Cài PyTorch phù hợp driver/CUDA.
- Nếu không có CUDA, hệ thống tự dùng CPU; FPS sẽ thấp hơn.

### OSNet bị vô hiệu hóa

- Kiểm tra `models/osnet_x0_25_msmt17.pth` tồn tại.
- Kiểm tra `torchreid` đã được cài.
- Xem log khởi động để biết checkpoint có tương thích không.
- Khi OSNet không khả dụng, hệ thống vẫn tracking ngắn hạn nhưng không khôi phục Stable ID dài hạn bằng deep Re-ID.

### Đếm sai hướng hoặc không đếm

- Kiểm tra A/B có đúng phía ngoài/trong hay không.
- Bảo đảm hai polygon không chồng nhau tại vùng người đi qua.
- Đặt ROI tại mặt sàn nơi điểm chân đi qua rõ ràng.
- Không di chuyển camera sau khi hiệu chỉnh ROI.
- Dùng Dashboard để đảo chiều hoặc kéo lại các đỉnh ROI.

### Dashboard có số liệu cũ

- `/api/stats` đọc sự kiện trong ngày từ SQLite, không chỉ bộ đếm RAM.
- Dùng “Làm sạch dữ liệu” hoặc `POST /api/clear_history` nếu muốn bắt đầu chu kỳ mới.
- `POST /api/reset_counts` chỉ reset trạng thái trong RAM.

## Triển khai NCNN trên Raspberry Pi 4 4GB

Backend Pi không cần PyTorch, Ultralytics hoặc Torchreid. Nó sử dụng YOLO26n
INT8 NCNN, OSNet x0.25 FP32 NCNN và tracker nhẹ tích hợp trong dự án.

### Cài trực tiếp trên Raspberry Pi OS 64-bit

```bash
chmod +x scripts/install_ncnn_pi.sh
./scripts/install_ncnn_pi.sh
.venv/bin/python scripts/smoke_ncnn.py --image scratch_benchmark/vd1_60.jpg
.venv/bin/python run_web.py --config config.pi.yaml
```

Mở `http://<IP-của-Pi>:8000`. Nếu camera không nằm ở `/dev/video0`, sửa
`source.path` trong `config.pi.yaml` thành index đúng.

### Chạy bằng Docker trên Pi

Build image trực tiếp trên Pi để nhận đúng kiến trúc ARM64:

```bash
docker build -f Dockerfile.pi -t visionflow-pi:latest .
docker run -d --name visionflow --restart unless-stopped \
  --device=/dev/video0:/dev/video0 \
  -p 8000:8000 \
  -v "$(pwd)/database.db:/app/database.db" \
  visionflow-pi:latest
```

Kiểm tra log bằng `docker logs -f visionflow`. File `yolo26n.table` chỉ phục
vụ hiệu chuẩn, không được nạp khi suy luận.

Trước khi nghiệm thu phải chạy lại video ground truth trên chính Pi và so sánh
số sự kiện IN/OUT với backend PyTorch. Unit test chỉ chứng minh logic phần mềm,
không chứng minh độ chính xác của model INT8 hay FPS trên thiết bị thật.

## Tài liệu liên quan

- [`TAI_LIEU_NHAN_DIEN_DEM_NGUOI.md`](TAI_LIEU_NHAN_DIEN_DEM_NGUOI.md) — giải thích detection, tracking, Re-ID và counting.
- [`KICH_BAN_BAO_VE_SMARTGATE_AI.md`](KICH_BAN_BAO_VE_SMARTGATE_AI.md) — kịch bản thuyết trình và Q&A.
- [`benchmark_results/C270_REALTIME_BENCHMARK.md`](benchmark_results/C270_REALTIME_BENCHMARK.md) — benchmark mô phỏng camera.
- [`benchmark_results/REALTIME_REVIEW_TEST1_TEST2.md`](benchmark_results/REALTIME_REVIEW_TEST1_TEST2.md) — đánh giá bản ghi camera thực tế.
