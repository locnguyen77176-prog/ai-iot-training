# Tài liệu hệ thống nhận diện, bám vết, nhớ ID và đếm người

> Tài liệu này mô tả đúng phiên bản hiện tại của hệ thống: **YOLO26n + FastTrack + OSNet bên ngoài + bộ đếm hai vùng A/B**.
>
> Đối tượng đọc: người vận hành, quản lý và người không chuyên về AI.

## 1. Hệ thống dùng để làm gì?

Hệ thống nhận hình ảnh từ camera hoặc video, tìm người trong từng khung hình, bám theo đường đi của họ và ghi nhận lượt **vào** hoặc **ra** khi họ đi qua hai vùng đếm.

Hệ thống thực hiện năm công việc chính:

1. **Phát hiện người:** YOLO26n tìm vị trí người trong ảnh.
2. **Bám vết ngắn hạn:** FastTrack duy trì một mã `Local ID` qua các khung hình liên tiếp và che khuất ngắn.
3. **Nhớ ID dài hạn:** OSNet so sánh ngoại hình để nối `Local ID` mới về `Stable ID` cũ.
4. **Xác định hướng:** bộ đếm theo dõi hành trình qua vùng A và vùng B.
5. **Hiển thị và lưu kết quả:** giao diện vẽ ID, IN/OUT, FPS và ghi sự kiện vào SQLite.

Hệ thống **không nhận diện khuôn mặt**, không biết tên, căn cước hoặc danh tính thật. `ID #12` chỉ là mã kỹ thuật dùng trong phiên chạy hiện tại.

## 2. Kiến trúc tổng thể

```text
Camera USB / Camera IP / Video
              │
              ▼
 Chuẩn hóa 1280×720 + chống lóa tùy điều kiện
              │
              ▼
       YOLO26n phát hiện người
              │
              ▼
 FastTrack + Kalman tạo Local ID
      (bám vết trong ngắn hạn)
              │
              ▼
 OSNet bên ngoài + bộ nhớ danh tính
        tạo/khôi phục Stable ID
              │
              ▼
 Bộ đếm FSM hai vùng theo Stable ID
              │
              ▼
 SQLite + giao diện web + video kết quả
```

Mỗi thành phần có trách nhiệm riêng:

- YOLO chỉ trả lời: “Có người ở đâu trong frame này?”.
- FastTrack trả lời: “Phát hiện này có phải track vừa thấy ở các frame gần đây không?”.
- OSNet trả lời: “Ngoại hình này có giống một hồ sơ cũ không?”.
- Bộ đếm trả lời: “Stable ID này đã hoàn thành A → B hay B → A chưa?”.

## 3. Nguồn hình ảnh

### 3.1 Cấu hình nguồn hiện tại

| Thuộc tính | Giá trị hiện tại |
|---|---|
| Loại nguồn | Camera trực tiếp |
| Đường dẫn | `auto_usb` |
| Kích thước chuẩn hóa | `1280 × 720` |
| Lật ngang | Có |
| Thử kết nối lại | Mỗi 3 giây |
| Chống lóa phần mềm | Bật, chế độ tự động |

`auto_usb` ưu tiên camera USB vật lý và loại các tên camera tích hợp hoặc camera ảo đã nhận biết. Có thể thay nguồn bằng chỉ số camera, URL RTSP/HTTP hoặc file video.

### 3.2 Camera trực tiếp

Với camera USB/IP, luồng đọc chỉ giữ **frame mới nhất**. Nếu camera gửi 30 FPS nhưng AI chỉ xử lý được 9 FPS, các frame trung gian có thể bị bỏ qua để hình ảnh không trễ dần.

Do đó cần phân biệt:

- Camera FPS: tốc độ camera cung cấp ảnh.
- AI FPS: tốc độ YOLO, FastTrack, OSNet và bộ đếm xử lý ảnh.
- Display FPS: tốc độ ảnh đã vẽ và nén JPEG được gửi lên giao diện.

Camera 30 FPS không làm AI tự động chạy 30 FPS.

### 3.3 Video có sẵn

Với file video, hệ thống dùng hàng đợi tuần tự và chờ consumer lấy frame, nhờ vậy không chủ động bỏ frame như camera live.

Server hiện khởi tạo `loop_video=True`. Khi hết file, video tự tua về đầu và phát tiếp. Tracker và bộ đếm không nhận được một tín hiệu reset riêng tại điểm lặp. Vì vậy:

- Số IN/OUT tiếp tục cộng qua nhiều vòng.
- ID vòng trước có thể ảnh hưởng vòng sau.
- Khi benchmark chính xác phải chạy một lượt bằng `benchmark_mot.py`, không lấy số từ video web đã lặp nhiều lần.

### 3.4 Chống lóa

Khối chống lóa kiểm tra tỷ lệ vùng sáng. Khi ảnh đủ chói, hệ thống nén highlight và tăng tương phản cục bộ bằng CLAHE.

Đây là xử lý phần mềm, không thể khôi phục chi tiết đã cháy trắng hoàn toàn. Vị trí camera, hướng nắng, dải tương phản động và chất lượng cảm biến vẫn quyết định phần lớn chất lượng ảnh.

## 4. YOLO26n phát hiện người

YOLO26n nhận một frame và trả về các hộp chữ nhật quanh người. Runtime chỉ yêu cầu lớp `person` (`classes=[0]`).

| Thông số | Giá trị | Ý nghĩa |
|---|---:|---|
| Model | `models/yolo26n.pt` | Model phát hiện |
| `imgsz` | `640` | Kích thước suy luận YOLO |
| Confidence | `0.25` | Loại phát hiện quá thiếu chắc chắn |
| IoU | `0.60` | Giảm hộp phát hiện trùng |
| Device | `cuda:0` | GPU CUDA đầu tiên |

Nếu CUDA không khả dụng, tracker tự chuyển về CPU. Runtime hiện không ép `half=True` và không dùng TensorRT.

YOLO không nhớ người qua thời gian. Việc giữ ID thuộc về FastTrack và bộ nhớ danh tính.

## 5. FastTrack bám vết ngắn hạn

Backend thực tế đã được benchmark và xác nhận là `FASTTracker`. Cấu hình nằm trong `custom_fasttrack.yaml`.

FastTrack sử dụng:

- Vị trí và độ chồng lấp của bounding box.
- Điểm tin cậy phát hiện.
- Kalman Filter để dự đoán chuyển động.
- Logic riêng cho tình huống một người bị người khác che khuất.

FastTrack trong hệ thống này **không thực hiện Re-ID ngoại hình**. OSNet được chạy riêng bên ngoài.

### 5.1 Local ID

FastTrack gắn mã `Local ID`, ví dụ `Local ID 25`. Local ID hoạt động tốt khi người được nhìn thấy liên tục hoặc chỉ mất dấu ngắn.

Nếu track bị mất lâu hơn cửa sổ lưu giữ, người xuất hiện lại có thể nhận Local ID mới. Đây là hành vi bình thường của tracker ngắn hạn.

### 5.2 Kalman Filter

Kalman Filter ước lượng vị trí và vận tốc để đoán người có thể xuất hiện ở đâu ở lần cập nhật tiếp theo. Kalman không biết quần áo hay danh tính người.

Khi hai người cắt nhau, di chuyển bất thường hoặc mất dấu quá lâu, chỉ Kalman và IoU có thể không đủ để giữ ID.

### 5.3 Xử lý che khuất của FastTrack

FastTrack hiện có các cơ chế:

- Phát hiện track bị hộp khác che phủ.
- Lưu lịch sử trạng thái Kalman gần nhất.
- Khôi phục vị trí/vận tốc trước lúc bị che.
- Nới hộp tìm kiếm một lần.
- Giảm vận tốc dự đoán trong thời gian che.
- Cho track vừa bị che một cửa sổ tái xuất hiện dài hơn.
- Hạn chế tạo track mới trùng hộp đang hoạt động.

### 5.4 Cấu hình FastTrack hiện tại

| Thông số | Giá trị | Vai trò |
|---|---:|---|
| `track_high_thresh` | `0.30` | Ngưỡng ghép phát hiện chính |
| `track_low_thresh` | `0.08` | Phát hiện yếu có thể dùng để cứu track |
| `new_track_thresh` | `0.38` | Điều kiện tạo track mới |
| `track_buffer` | `45` | Số lần cập nhật giữ track mất dấu |
| `match_thresh` | `0.82` | Ngưỡng ghép chuyển động/hộp |
| `occ_cover_thresh` | `0.70` | Mức che phủ để coi là che khuất |
| `active_occ_to_lost_thresh` | `10` | Thời gian grace khi track đang bị che |
| `occ_reappear_window` | `45` | Cửa sổ cho track vừa bị che xuất hiện lại |
| `init_iou_suppress` | `0.70` | Hạn chế sinh track trùng |

`track_buffer=45` là 45 **lần FastTrack được cập nhật**, không phải luôn là 45 frame gốc của camera và không phải số giây cố định. Nếu AI chạy 9 FPS, 45 lần cập nhật tương đương khoảng 5 giây; nếu AI chạy 15 FPS thì khoảng 3 giây.

## 6. Local ID và Stable ID

Hệ thống có hai tầng ID:

| Loại ID | Nguồn tạo | Mục đích |
|---|---|---|
| Local ID | FastTrack | Theo dõi ngắn hạn |
| Stable ID | `PersistentIdentityManager` | Giữ mã dùng cho hiển thị và đếm |

Ví dụ:

```text
Trước khi mất dấu: Local ID 21 ─┐
                               ├─► Stable ID 8
Sau khi xuất hiện: Local ID 35 ─┘
```

Nếu OSNet kết luận Local ID 35 là người cũ, bộ đếm tiếp tục nhận Stable ID 8 thay vì tạo hành trình độc lập.

Stable ID chỉ có ý nghĩa trong phiên chạy. Khi đổi nguồn, tracker được reset và ID bắt đầu lại.

## 7. OSNet bên ngoài nhớ ID dài hạn

### 7.1 Model đang sử dụng

```text
models/osnet_x0_25_msmt17.pth
```

OSNet nhận crop người và tạo vector đặc trưng 512 chiều. Các vector gần nhau thường biểu thị ngoại hình tương tự.

OSNet không phải nhận diện khuôn mặt. Nó chủ yếu dựa vào quần áo, màu sắc, tỷ lệ hình thể và các mẫu thị giác tổng hợp.

### 7.2 Khi nào OSNet chạy?

OSNet không chạy cho mọi người ở mọi frame. Một track được yêu cầu trích embedding khi:

- Local ID mới chưa có Stable ID;
- Stable ID tạm chưa có embedding OSNet và cần được xét lại; hoặc
- Đã cách lần lấy mẫu gallery trước ít nhất `15` frame xử lý.

Crop chỉ được chấp nhận khi:

- Confidence tối thiểu `0.55`.
- Chiều cao bounding box tối thiểu `100` pixel.

Các yêu cầu mới/đang chờ được ưu tiên trước. Hệ thống chỉ gửi tối đa `4` crop tới OSNet trong một frame. Việc bổ sung gallery thông thường được gom tối đa `4` crop mỗi `3` frame để tận dụng batch GPU, thay vì gọi OSNet riêng lẻ ở mọi frame. Encoder hỗ trợ batch tối đa `16`, còn gallery của mỗi Stable ID giữ tối đa `5` embedding.

Nếu có hơn 4 ID mới trong cùng frame, các crop có confidence cao và kích thước lớn được xử lý trước; các ID còn lại tiếp tục được ưu tiên ở frame sau. Giới hạn này ngăn spike độ trễ khi cảnh đông.

### 7.3 Ghép Local ID mới về Stable ID cũ

Khi Local ID mới có embedding, bộ nhớ danh tính:

1. So sánh embedding với gallery của các Stable ID còn hiệu lực.
2. Kết hợp điểm OSNet với một phần nhỏ descriptor màu khi có.
3. Kiểm tra khoảng cách vị trí và thời gian vắng mặt.
4. Loại Stable ID đang được một Local ID khác sử dụng trong cùng frame.
5. Chọn ứng viên đạt điều kiện tốt nhất.

Trọng số hiện tại khi có cả hai loại đặc trưng:

```text
88% điểm OSNet + 12% điểm màu
```

Điều kiện chính:

- Điểm OSNet tối thiểu `0.78`.
- Điểm kết hợp tối thiểu `0.72`.
- Khoảng cách phải nằm trong cổng không gian được nới theo thời gian vắng mặt.

`reid_ambiguity_margin=0.0`, vì vậy hệ thống không từ chối chỉ vì hai ứng viên gần điểm nhau. Nó chọn ứng viên hợp lệ có điểm cao nhất. Cấu hình này ưu tiên giảm trường hợp không nối được ID, nhưng tăng nguy cơ gán nhầm người có ngoại hình giống nhau.

### 7.4 Thời gian nhớ ID

`identity_memory_seconds=40`: hồ sơ không xuất hiện quá 40 giây bị xóa khỏi bộ nhớ. Giá trị này không phải bộ nhớ vĩnh viễn và không tồn tại qua lần khởi động lại.

### 7.5 Xử lý embedding đến trễ

Nếu Local ID mới chưa đủ chất lượng ở frame đầu, hệ thống có thể tạo Stable ID tạm. Khi embedding đầu tiên đến ở frame sau, hệ thống chạy lại bước so khớp với các Stable ID cũ còn hiệu lực.

Nếu tìm thấy hồ sơ phù hợp, Local ID được chuyển khỏi Stable ID tạm về Stable ID cũ; hồ sơ tạm không còn được sử dụng sẽ bị xóa. Bộ đếm đồng thời nhập bằng chứng vùng và lịch sử ngắn của ID tạm vào ID cũ, nhưng vẫn giữ trạng thái hành trình ban đầu. Vì vậy tình huống `ID 6 ở A → mất dấu → ID tạm 9 ở B → embedding đến trễ` vẫn có thể hoàn tất hành trình A → B.

### 7.6 Khi OSNet không tải được

Khi `reid_model_path` được cấu hình, hệ thống yêu cầu deep Re-ID để nối ID dài hạn. Nếu checkpoint không tải được:

- YOLO và FastTrack vẫn hoạt động.
- Bám vết ngắn hạn vẫn có.
- Nối Stable ID dài hạn bị tắt.
- Hệ thống không âm thầm dùng màu quần áo thay thế OSNet để nối ID cũ.

Log đúng khi khởi động:

```text
[ReID] OSNet x0.25 enabled: ...osnet_x0_25_msmt17.pth
```

## 8. Loại bỏ track trùng

Trước khi cập nhật Stable ID, hệ thống kiểm tra các bounding box có IoU hoặc độ bao phủ quá lớn.

Nếu hai hộp rất có thể là cùng một người, hệ thống giữ một hộp và loại hộp còn lại nhằm tránh:

- Vẽ hai ID cho một người.
- Tạo hai hồ sơ OSNet cho cùng một người.
- Đếm một người hai lần.

Khi cả hai hộp có embedding OSNet, độ giống sâu cũng được dùng để hỗ trợ quyết định.

## 9. Bộ đếm hai vùng A/B

### 9.1 Điểm dùng để xác định vùng

Hệ thống dùng điểm **đáy giữa của bounding box**, gần vị trí bàn chân:

```text
x = (x1 + x2) / 2
y = y2
```

Điểm bàn chân phù hợp với vùng được vẽ trên mặt sàn hơn tâm bounding box.

Nếu điểm nằm đồng thời trong cả A và B, hoặc không nằm trong vùng nào, kết quả vùng là `NONE`. Vì vậy không nên để hai polygon chồng lên nhau.

### 9.2 Quy tắc đếm

```text
Stable ID đi A → B = tăng 1 IN
Stable ID đi B → A = tăng 1 OUT
```

Một vùng phải được nhìn thấy liên tiếp ít nhất `2` frame xử lý mới được công nhận. Điều này giảm nhiễu khi bounding box rung tại mép vùng.

### 9.3 Máy trạng thái

```text
NONE
  ├─ vào A ─► IN_A ── sang B ─► LOCKED_IN  ─► ghi 1 IN
  └─ vào B ─► IN_B ── sang A ─► LOCKED_OUT ─► ghi 1 OUT
```

Sau khi đếm, Stable ID bị khóa. Khi ID đã rời cả hai vùng và đủ `cooldown_seconds=3`, trạng thái trở về `NONE` để có thể ghi nhận một hành trình mới.

Trạng thái không hoạt động quá `120` giây sẽ bị xóa.

### 9.4 Không có bàn giao trạng thái mồ côi

Bộ đếm hiện tại không tìm một ID mất ở A để bàn giao trực tiếp cho một ID khác xuất hiện ở B. Nó chỉ hoàn thành hành trình khi đầu vào của bộ đếm có cùng Stable ID.

Điều này tránh kiểu đếm giả do ghép một người bất kỳ ở vùng đối diện, nhưng có thể đếm thiếu nếu:

- FastTrack tạo Local ID mới; và
- OSNet không nối Local ID mới về Stable ID cũ.

Nói cách khác, việc nối hành trình dài hạn hiện phụ thuộc vào `PersistentIdentityManager`, không có lớp cứu hành trình riêng trong `DualZoneCounter`.

### 9.5 Rủi ro Stable ID nhảy vùng

FSM kiểm tra thứ tự vùng nhưng chưa kiểm tra vận tốc, khoảng cách ngang hoặc tính liên tục của quỹ đạo khi Stable ID chuyển A ↔ B. Nếu Re-ID gán nhầm cùng Stable ID cho hai người ở hai vùng, bộ đếm vẫn có thể tạo sự kiện.

Đây là giới hạn cần biết khi dùng `reid_ambiguity_margin=0.0` trong cảnh nhiều người mặc giống nhau.

## 10. Giao diện và FPS

### 10.1 AI FPS

AI FPS được tính bằng số frame gần đây đã đi qua tracker và bộ đếm. Đây là chỉ số gần với năng lực xử lý AI thực tế.

### 10.2 Display FPS

Render, vẽ overlay và mã hóa JPEG chạy trên thread riêng. Display FPS phản ánh tốc độ frame đã chuẩn bị cho trình duyệt.

Hai con số có thể khác nhau:

- AI FPS thấp: nút thắt thường nằm ở YOLO, OSNet hoặc số người.
- Display FPS thấp nhưng AI FPS ổn: có thể do render, JPEG, mạng hoặc trình duyệt.

### 10.3 Nhãn `[IN]` và `[OUT]`

Sau khi một Stable ID được đếm, ID đó được lưu trong `counted_tracks` và giao diện tiếp tục hiển thị nhãn `[IN]` hoặc `[OUT]`. Nhãn hiện không tự hết sau vài giây; nó tồn tại cho đến khi trạng thái ID bị dọn hoặc bộ đếm được reset.

Vì vậy nhãn trên hộp chỉ cho biết ID đó **đã từng được đếm**, không có nghĩa tổng đang tăng ở mọi frame.

### 10.4 Occupancy

Giao diện ước tính:

```text
Occupancy = max(0, IN - OUT)
```

Đây là số ước tính. Nếu khởi động khi bên trong đã có người hoặc đã có lượt đếm sai, Occupancy không thể tự hiệu chỉnh về số thật.

## 11. Lưu dữ liệu

Mỗi sự kiện IN/OUT được ghi vào `database.db` bằng SQLite, gồm Stable ID, hướng và thời gian.

Web server hiện ghi tuổi và giới tính là `N/A`; hệ thống không chạy model tuổi/giới tính trong đường xử lý hiện tại.

Khi đổi nguồn, bộ đếm và tracker trong phiên được reset. Dữ liệu lịch sử đã ghi trong SQLite không tự bị xóa.

## 12. Cấu hình hiện tại

| Nhóm | Giá trị chính |
|---|---|
| Detector | YOLO26n, `imgsz=640`, conf `0.25`, IoU `0.60` |
| Tracker | `custom_fasttrack.yaml` |
| FastTrack buffer | `45` lần cập nhật |
| FastTrack occlusion window | `45` lần cập nhật |
| Re-ID | OSNet x0.25 MSMT17 |
| Ngưỡng OSNet | `0.78` |
| Ambiguity margin | `0.0` |
| Bộ nhớ Stable ID | `40` giây |
| Chu kỳ lấy mẫu | `15` frame xử lý |
| Chất lượng crop | confidence ≥ `0.55`, chiều cao ≥ `100 px` |
| Gallery | tối đa `5` embedding/Stable ID |
| Batch OSNet | tối đa `16` crop/lượt |
| Xác nhận vùng | `2` frame liên tiếp |
| Cooldown | `3` giây |
| TTL trạng thái đếm | `120` giây |

Các giá trị này là cấu hình hiện tại, không phải giá trị tối ưu cho mọi camera.

## 13. Ví dụ hoạt động

### Trường hợp 1: người đi rõ ràng từ A sang B

YOLO nhìn thấy người → FastTrack giữ Local ID → Stable ID không đổi → điểm chân được xác nhận ở A rồi B → ghi một IN và khóa ID.

### Trường hợp 2: bị che ngắn

FastTrack dùng Kalman và logic che khuất để chờ người xuất hiện lại. Nếu ghép thành công, Local ID và Stable ID không đổi; bộ đếm tiếp tục hành trình.

### Trường hợp 3: FastTrack tạo Local ID mới

Nếu crop mới đủ chất lượng, OSNet so với gallery cũ. Khi điểm và cổng không gian đạt điều kiện, Local ID mới được ánh xạ về Stable ID cũ.

### Trường hợp 4: Local ID mới không đủ chất lượng

Nếu người quá nhỏ hoặc confidence thấp, hệ thống dùng Stable ID tạm và tiếp tục ưu tiên lấy embedding ở các frame sau. Khi embedding đạt chất lượng và khớp hồ sơ cũ, ID tạm cùng trạng thái vùng được bàn giao về ID cũ. Nếu người biến mất trước khi có bất kỳ embedding hợp lệ nào, hành trình vẫn có thể bị đứt.

### Trường hợp 5: hai người mặc giống nhau

Vì ambiguity margin bằng 0, ứng viên hợp lệ có điểm cao nhất được chọn. Điều này có thể cứu thêm ID nhưng cũng có thể gán nhầm Stable ID, từ đó làm quỹ đạo hoặc số đếm sai.

### Trường hợp 6: người đứng ở mép vùng

Vùng phải ổn định 2 frame, nên một frame rung sang vùng khác chưa đủ để đếm. Sau khi đếm, trạng thái LOCKED ngăn cộng lặp khi người còn ở trong vùng.

## 14. Benchmark hiện tại trên MOT16-03.mp4

Benchmark được chạy đủ một lượt 1.500 frame, không thông qua vòng lặp web.

| Chỉ số | Kết quả |
|---|---:|
| Backend tracker | `FASTTracker` |
| External Re-ID | `OSNetReIDEncoder` |
| GPU | NVIDIA GeForce RTX 3050 Laptop GPU |
| Frame đã xử lý | 1.500 |
| FPS nguồn | 15 FPS |
| Pipeline FPS | **12,66 FPS** |
| Độ trễ tracker trung bình | 72,47 ms/frame |
| Độ trễ tracker p95 | 130,93 ms/frame |
| Người trung bình | 40,283 người/frame |
| Người tối đa | 54 người/frame |
| Local ID duy nhất | 314 |
| Stable ID duy nhất | 313 |
| Sự kiện Re-ID | 26 |
| Hộp trùng bị loại | 80 |
| IN / OUT theo ROI hiện tại | 33 / 15 |

Báo cáo nằm trong `benchmark_mot16_03_delayed_reid.json`.

Benchmark này xác nhận backend, tốc độ và một số dấu hiệu phân mảnh ID. Video không kèm ground truth nên kết quả **không phải** MOTA, IDF1, HOTA hoặc độ chính xác đếm. IN/OUT phụ thuộc trực tiếp vào ROI hiện tại.

Pipeline 12,66 FPS vẫn chậm hơn nguồn 15 FPS nhưng nhanh hơn benchmark trước đó 9,53 FPS. Khi chạy camera live, hệ thống bỏ frame trung gian để giữ độ trễ thấp; khi chạy file trong web, hàng đợi tuần tự và pacing nguồn có thể tạo trải nghiệm khác benchmark lõi.

## 15. Điểm mạnh

- FastTrack nhẹ và có xử lý che khuất riêng.
- Re-ID được tách khỏi tracker, tránh phụ thuộc model nội bộ của FastTrack.
- Stable ID tách khỏi Local ID.
- OSNet chỉ chạy cho ID mới hoặc theo chu kỳ, không chạy mọi người ở mọi frame.
- Gallery nhiều góc nhìn giúp so khớp bớt phụ thuộc một crop duy nhất.
- Bộ đếm hai vùng và trạng thái LOCKED giảm đếm lặp.
- Camera live ưu tiên frame mới nhất để tránh backlog.
- Luồng AI tách khỏi render/JPEG.

## 16. Hạn chế và rủi ro

- Cảnh đông, che khuất lâu hoặc nhiều người mặc giống nhau vẫn có thể đổi ID.
- Ambiguity margin bằng 0 tăng khả năng nối nhầm.
- Hơn 4 Local ID mới cùng lúc phải chờ phân bổ qua các frame kế tiếp.
- Crop nhỏ hơn 100 px không được dùng cho OSNet.
- Nếu không bao giờ có embedding hợp lệ thì Stable ID tạm không thể ánh xạ về hồ sơ cũ.
- Bộ đếm chỉ bàn giao trạng thái khi tracker xác nhận remap bằng OSNet; không tự ghép hai ID mồ côi chỉ dựa trên vùng.
- Bộ đếm chưa chặn Stable ID dịch chuyển phi vật lý giữa hai vùng.
- Nhãn `[IN]/[OUT]` tồn tại lâu, có thể gây hiểu nhầm.
- Video web tự lặp nhưng không reset phiên tại điểm lặp.
- 12,66 FPS thấp hơn video nguồn 15 FPS trong benchmark hiện tại.
- Không có ground truth nên chưa thể tuyên bố độ chính xác đếm hoặc tracking.

## 17. Bố trí camera và ROI

- Gắn camera cố định, tránh rung và tránh nhìn thẳng nguồn sáng.
- Đảm bảo người đủ lớn; với OSNet hiện tại chiều cao hộp phải đạt ít nhất 100 px.
- Hai vùng không nên chồng lên nhau.
- Vùng phải phủ hết chiều rộng lối đi thực tế.
- Giữa A và B nên có khoảng chuyển tiếp rõ ràng.
- Tránh đặt mép vùng tại nơi người thường đứng chờ.
- Dùng điểm chân trên màn hình để kiểm tra polygon, không chỉ nhìn tâm hộp.
- Kiểm thử vào giờ cao điểm và điều kiện ánh sáng xấu nhất.

## 18. Chẩn đoán nhanh

### Người bị che rồi nhận ID mới

Kiểm tra:

- Log OSNet đã enabled chưa.
- Bounding box có cao ít nhất 100 px không.
- Confidence có đạt 0.55 không.
- Thời gian vắng có vượt 40 giây không.
- Vị trí tái xuất hiện có quá xa cổng không gian không.
- Quần áo có giống nhiều người khác không.

### FPS tụt khi cảnh đông

Các nguyên nhân chính:

- YOLO chạy với `imgsz=640`.
- Có khoảng 40–50 người trong một frame.
- Nhiều ID mới khiến OSNet dùng hết ngân sách 4 crop/frame trong nhiều frame liên tiếp.
- Vẽ nhiều hộp/chữ và nén JPEG.
- GPU đang được ứng dụng khác sử dụng.

### Đếm thiếu

Kiểm tra:

- Điểm chân có thật sự được xác nhận ở cả A và B không.
- Stable ID có đổi giữa hai vùng không.
- Người có đi quá nhanh so với AI FPS không.
- ROI có khoảng trống mà người có thể bỏ qua không.

### Đếm nhầm

Kiểm tra:

- Stable ID có nhảy từ người này sang người khác không.
- Hai người có mặc giống nhau không.
- `reid_ambiguity_margin=0.0` có quá mạnh cho cảnh thực tế không.
- Hai polygon có chồng nhau hoặc đặt quá rộng không.
- Video có đang chạy vòng thứ hai trở đi không.

## 19. Các tệp chính

| Tệp | Trách nhiệm |
|---|---|
| `config.yaml` | Cấu hình camera, YOLO, OSNet, FastTrack và vùng |
| `custom_fasttrack.yaml` | Tham số FastTrack và che khuất ngắn |
| `src/video_stream.py` | Camera/video, reconnect, resize và chống lóa |
| `src/tracker.py` | YOLO, FastTrack, OSNet và Stable ID |
| `src/osnet_reid.py` | Tải checkpoint và trích embedding OSNet |
| `src/zone_counter.py` | FSM đếm hai vùng |
| `src/db_manager.py` | SQLite |
| `src/visualizer.py` | Vẽ ROI, ID, HUD và nhãn sự kiện |
| `web/server.py` | Worker AI, render, API và web stream |
| `benchmark_mot.py` | Benchmark một lượt và xác minh backend |
| `benchmark_mot16_03_fasttrack_osnet.json` | Báo cáo benchmark hiện tại |

Các file cấu hình BoT-SORT và ByteTrack tùy chỉnh đã bị xóa khỏi dự án. Mã dự án hiện chỉ cấu hình FastTrack cho tracker ngắn hạn và OSNet cho Re-ID bên ngoài.

## 20. Tóm tắt dễ nhớ

- **YOLO26n:** tìm người trong mỗi ảnh.
- **FastTrack + Kalman:** giữ Local ID trong thời gian ngắn và che khuất ngắn.
- **OSNet bên ngoài:** so ngoại hình để khôi phục Stable ID.
- **Stable ID:** mã được đưa vào bộ đếm.
- **FSM hai vùng:** chỉ ghi sự kiện khi cùng Stable ID hoàn thành A → B hoặc B → A.
- **SQLite:** lưu lịch sử sự kiện.
- **AI FPS:** tốc độ xử lý AI; không đồng nghĩa FPS camera hoặc Display FPS.

Kiến trúc hiện tại đã loại BoT-SORT/ByteTrack tùy chỉnh khỏi đường chạy dự án. Kết quả thực tế vẫn phụ thuộc góc camera, kích thước người, mật độ đám đông, ánh sáng, ROI và khả năng phần cứng.
