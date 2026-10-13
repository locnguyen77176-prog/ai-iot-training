# Tối ưu FPS cho Raspberry Pi 4

## 1. Mục tiêu

Tối ưu hệ thống nhận diện và đếm người trên Raspberry Pi 4 để:

- Pipeline xử lý, tracking, đếm vùng và video đầu ra hướng tới mức ổn định `7–10 FPS`.
- Giữ nguyên YOLO26n NCNN INT8 tại kích thước đầu vào `640 × 640`.
- Giữ nguyên OSNet x0.25 NCNN FP32, không lượng tử OSNet xuống INT8.
- Không bổ sung module tăng tốc hoặc phần cứng bên ngoài.
- Giới hạn tải khi trong khung hình có nhiều người.

> Lưu ý: `7–10 FPS` là mục tiêu của toàn bộ pipeline theo kiến trúc đa nhịp. Với thời gian suy luận YOLO khoảng `417 ms`, detector 640 × 640 không thể tạo 7–10 kết quả YOLO mới mỗi giây trên Pi 4. Các frame giữa hai lần detection được cập nhật bằng motion prediction.

## 2. Nút thắt trước khi tối ưu

Pipeline cũ thực hiện tuần tự:

```text
Camera
  → YOLO NCNN
  → LiteByteTracker
  → OSNet ReID
  → FSM đếm vùng
  → Vẽ giao diện
  → JPEG
  → Trình duyệt
```

Mỗi vòng xử lý phải chờ YOLO hoàn thành. Kết quả đo trên Pi 4:

```text
YOLO NCNN: khoảng 417.2 ms/frame
OSNet NCNN FP32: khoảng 21.4 ms/người
Pipeline: khoảng 2.3 FPS
```

Vì YOLO chiếm hơn 400 ms, tối ưu JPEG hoặc OSNet riêng lẻ không thể đưa pipeline tuần tự lên 7–10 FPS.

## 3. Kiến trúc sau khi tối ưu

Pipeline được chuyển sang kiến trúc đa nhịp:

```text
                         ┌──────────────────────────────┐
Camera 10 FPS ──────────►│ Pipeline chính               │
                         │ - Motion prediction          │
                         │ - Persistent Identity        │
                         │ - Dual-Zone FSM              │
                         │ - Render và JPEG             │
                         └──────────────┬───────────────┘
                                        │ frame mới nhất
                                        ▼
                         ┌──────────────────────────────┐
                         │ Process YOLO NCNN riêng      │
                         │ - 3 CPU threads              │
                         │ - Tối đa một inference       │
                         │ - Không tạo backlog          │
                         └──────────────┬───────────────┘
                                        │ detection mới
                                        ▼
                         LiteByteTracker hiệu chỉnh lại
```

YOLO chạy trong một process riêng thay vì chạy đồng bộ trong vòng pipeline. Cách này tránh việc lời gọi NCNN Python giữ GIL làm đứng tracker và web server.

## 4. Những phần đã tối ưu

### 4.1. Tách YOLO sang process riêng

Các hàm worker process được thêm trong `src/ncnn_backend.py`:

- `initialize_detector_process()` tải duy nhất một model YOLO trong process con.
- `detector_process_ready()` kiểm tra model đã tải thành công.
- `detect_in_process()` chạy inference và trả về detection cùng thời gian suy luận.

`YOLOTracker` sử dụng `ProcessPoolExecutor` với đúng một worker. Hệ thống không chạy nhiều YOLO song song nên không làm tăng đột biến RAM và CPU.

### 4.2. Motion prediction giữa hai lần detection

`LiteByteTracker.predicted_tracks()` dự đoán bbox dựa trên vận tốc của track mà không thay đổi trạng thái tracker gốc.

Quy trình:

1. YOLO trả detection tại frame gốc.
2. LiteByteTracker hiệu chỉnh bbox và vận tốc.
3. Trong lúc chờ inference tiếp theo, bbox được ngoại suy cho các frame mới.
4. Khi detection mới đến, tracker được hiệu chỉnh lại.

Nhờ đó FSM đếm vùng và video không phải dừng lại chờ YOLO.

### 4.3. Không tạo hàng đợi frame cũ

Detector chỉ có tối đa một tác vụ inference đang chạy. Hệ thống không xếp nhiều frame vào queue, tránh tình trạng video vẫn xử lý những hình ảnh đã cũ vài giây.

### 4.4. ReID sử dụng frame detection gốc

Khi YOLO trả kết quả, hệ thống giữ frame tương ứng để OSNet cắt đúng vùng người tại thời điểm detection. Điều này hạn chế việc lấy nhầm crop từ bbox đã được ngoại suy sang frame hiện tại.

### 4.5. Giới hạn tải OSNet

OSNet vẫn là NCNN FP32. Cấu hình Pi được đặt:

```yaml
ncnn_reid_num_threads: 1
reid_max_per_frame: 1
reid_max_periodic_per_frame: 1
reid_sample_interval_frames: 60
reid_periodic_schedule_frames: 10
```

Tác dụng:

- Mỗi frame chỉ xử lý tối đa một crop OSNet.
- Khi có nhiều người, chi phí ReID không tăng đột biến trong một frame.
- ReID được phân bố theo thời gian thay vì xử lý toàn bộ đám đông cùng lúc.
- YOLO và OSNet không tranh toàn bộ bốn lõi CPU.

### 4.6. Giảm tính toán ngoại hình dư thừa

Histogram màu không còn được tính lại cho mọi người ở các frame chỉ dùng motion prediction.

Hồ sơ ngoại hình được cập nhật khi có detection thật hoặc khi một local ID cần được khởi tạo. Cách này:

- Giảm CPU khi có hàng chục người.
- Tránh cập nhật hồ sơ bằng crop bị lệch do ngoại suy.
- Không làm thay đổi FSM đếm vùng ở các frame trung gian.

### 4.7. Phân bổ CPU cho Pi 4

Cấu hình detector:

```yaml
ncnn_num_threads: 3
ncnn_reid_num_threads: 1
ncnn_async_detection: true
ncnn_detection_interval_frames: 1
```

Docker runtime:

```yaml
OMP_NUM_THREADS: "3"
OMP_WAIT_POLICY: "PASSIVE"
GOMP_SPINCOUNT: "0"
OPENBLAS_NUM_THREADS: "1"
```

OpenCV cũng được giới hạn một thread trong NCNN runtime. Mục tiêu là dành đủ tài nguyên cho web server, tracker, OSNet và JPEG thay vì để các thư viện cùng tạo nhiều thread vượt quá bốn lõi của Pi.

### 4.8. Giảm chi phí camera và JPEG

Cấu hình Pi hiện tại:

```yaml
source:
  target_fps: 10

ui:
  jpeg_quality: 60
```

Camera chỉ cung cấp đúng nhịp mục tiêu. JPEG quality 60 giảm thời gian encode và băng thông MJPEG nhưng vẫn đủ rõ cho dashboard giám sát.

### 4.9. Tách số đo PIPE và DET

Dashboard và API hiển thị riêng:

- `PIPE`: FPS của tracker, FSM, render và pipeline đầu ra.
- `DET`: số inference YOLO hoàn thành mỗi giây.
- `detector_latency_ms`: thời gian inference YOLO NCNN.
- `display_fps`: FPS JPEG thực tế được đưa ra trình duyệt.

Ví dụ:

```text
PIPE 9.8 | DET 2.1 FPS
```

Điều này có nghĩa pipeline đang xử lý gần 10 frame/giây, trong khi YOLO cung cấp khoảng 2.1 detection mới/giây. Các frame còn lại sử dụng tracking dự đoán.

## 5. Cấu hình Pi sau tối ưu

Các giá trị quan trọng trong `config.pi.yaml`:

```yaml
detector:
  backend: ncnn
  imgsz: 320
  ncnn_num_threads: 3
  ncnn_reid_num_threads: 1
  ncnn_async_detection: true
  ncnn_detection_interval_frames: 1

  reid_max_per_frame: 1
  reid_max_periodic_per_frame: 1
  reid_periodic_schedule_frames: 10
  reid_sample_interval_frames: 60

source:
  width: 1280
  height: 720
  target_fps: 10

ui:
  jpeg_quality: 60
```

Model triển khai hiện tại đã được export và lượng tử lại đúng input cố định `320 × 320`. Không đổi riêng `imgsz` sang giá trị khác nếu chưa tạo lại model NCNN cùng kích thước.

### Model detector 320 đang triển khai

- Thư mục: `models/yolo26n_320_ncnn_int8/`
- Input cố định: `320 × 320`
- Output: `84 × 2100` thay cho `84 × 8400` ở bản 640
- Lượng tử: NCNN INT8, ACIQ, 1.000 ảnh calibration đã letterbox
- `config.pi.yaml`, Dockerfile, entrypoint và script deploy đều đã trỏ sang model này

Không dùng bảng lượng tử KL cho bản 320 vì kiểm tra cho thấy confidence bị tụt mạnh.
Bảng ACIQ giữ được 94,7% detection của bản FP32 trên phép so sánh 100 ảnh tại
IoU 0,50. Đây là kiểm tra độ tương đồng với FP32, chưa thay thế đánh giá trên bộ
dữ liệu gán nhãn thực tế.

## 6. Các file đã thay đổi

| File | Nội dung |
|---|---|
| `src/ncnn_backend.py` | Worker process NCNN, validation metadata, motion prediction |
| `src/tracker.py` | Pipeline detector bất đồng bộ, tracking xen kẽ, giới hạn ReID |
| `web/server.py` | JPEG configurable, telemetry detector |
| `web/static/js/app.js` | Hiển thị riêng PIPE và DET |
| `config.pi.yaml` | Cấu hình Pi 4 tối ưu |
| `docker-compose.pi.yml` | Giới hạn OpenMP runtime |
| `Dockerfile.pi` | Biến môi trường CPU cho container |
| `main.py` | Truyền cấu hình mới và giải phóng detector process |
| `test_ncnn_backend.py` | Test metadata và motion prediction |
| `test_tracking.py` | Test scheduler ReID, async detector và descriptor cadence |

## 7. Kết quả kiểm tra trên máy phát triển

```text
40 tests passed
Python compile: passed
Docker Compose validation: passed
Multiprocessing pipeline test: 9.99 FPS
30-person identity tracking simulation: 1045 FPS
```

Các phép thử trên máy phát triển xác nhận pipeline không còn bị chặn bởi tác vụ detector và phần tracking/identity có đủ dư địa cho vài chục track.

Đây không phải kết quả benchmark cuối cùng trên Raspberry Pi. FPS thực tế còn phụ thuộc vào nhiệt độ, nguồn điện, camera, thẻ nhớ và tình trạng throttling.

## 8. Build và triển khai image mới

Code tối ưu nằm bên trong Docker image nên bắt buộc phải build và push image mới.

Trên máy tính Windows, bật Docker Desktop rồi chạy PowerShell:

```powershell
cd D:\ai-iot-training\Computer_Vision

docker login

docker buildx build `
  --platform linux/arm64 `
  -f Dockerfile.pi `
  -t locnguyen77176/visionflow-pi:latest `
  --push .
```

Commit và push source lên GitHub để Pi nhận `config.pi.yaml` mới.

Trên Raspberry Pi:

```bash
cd ~/ai-iot-training
git pull

cd ~/ai-iot-training/Computer_Vision
chmod +x scripts/deploy_docker_pi.sh

VISIONFLOW_IMAGE=locnguyen77176/visionflow-pi:latest \
PULL_IMAGE=1 \
./scripts/deploy_docker_pi.sh
```

## 9. Kiểm tra sau triển khai

Kiểm tra container:

```bash
docker compose -f docker-compose.pi.yml ps
docker compose -f docker-compose.pi.yml logs --tail=200 visionflow
docker stats --no-stream
```

Kiểm tra API:

```bash
curl http://127.0.0.1:8000/api/camera/status
```

Các trường cần quan sát:

```json
{
  "ai_fps": 9.5,
  "display_fps": 9.4,
  "detector_fps": 2.0,
  "detector_latency_ms": 450.0,
  "backend": "LiteByteTracker/NCNN"
}
```

Mục tiêu chấp nhận:

```text
PIPE/ai_fps: 7–10 FPS
display_fps: 7–10 FPS
DET/detector_fps: khoảng 1.8–2.5 FPS với model 640 hiện tại
Container: healthy
Không restart hoặc exit 139
```

## 10. Kiểm tra nhiệt độ và throttling

Trên Pi chạy:

```bash
vcgencmd measure_temp
vcgencmd get_throttled
```

Kết quả tốt:

```text
throttled=0x0
```

Nếu nhiệt độ cao hoặc Pi bị throttling, FPS sẽ giảm dù phần mềm đã được tối ưu. Cần dùng nguồn điện ổn định và tản nhiệt phù hợp cho Pi 4.

## 11. Giới hạn còn lại

- YOLO 640 × 640 vẫn là nút thắt chính.
- Motion prediction không thay thế được detection mới trong trường hợp người di chuyển quá nhanh, bị che khuất lâu hoặc đám đông giao nhau dày đặc.
- Mức ổn định với vài chục người phải được xác nhận bằng video/camera thực tế trên Pi.
- Độ chính xác đếm phải được đánh giá bằng tập video có nhãn, không chỉ quan sát độ mượt.

Nếu bắt buộc cả detector cũng phải đạt 7–10 FPS, bước tiếp theo là export và lượng tử YOLO26n INT8 ở `320 × 320` hoặc thử `416 × 416`, sau đó đo lại recall và độ chính xác đếm. OSNet vẫn có thể giữ FP32.
