# Benchmark giả lập camera Logitech C270 thời gian thực

## Mục tiêu và cấu hình mô phỏng

Hai video `vd1.mp4` và `vd2.mp4` được đưa qua đúng pipeline hiện tại gồm YOLO, FASTTracker, Kalman theo thời gian thực, OSNet tái nhận dạng Stable ID và bộ đếm vùng.

Cấu hình giả lập camera:

- Luồng camera: 1280 x 720, 15 FPS.
- Bộ đệm kiểu `latest-frame`: khi xử lý không kịp, hệ thống lấy frame mới nhất thay vì giữ một hàng đợi dài gây trễ.
- Nén JPEG chất lượng 90 để gần với một luồng camera thực tế.
- Dùng model, ngưỡng và các thiết lập đang có trong `config.yaml` tại thời điểm chạy.
- Bỏ 3 frame khởi động khỏi phép đo thời gian để tránh thời gian CUDA/model khởi tạo làm sai kết quả ổn định.

## Kết quả

| Chỉ số | vd1.mp4 | vd2.mp4 |
|---|---:|---:|
| Thời lượng nguồn | 300,04 giây | 100,00 giây |
| FPS nguồn | 25,003 | 15,000 |
| Frame camera công bố ở 15 FPS | 4.500 | 1.500 |
| Frame AI xử lý | 4.500 | 1.498 |
| Frame bị bỏ để giữ realtime | 0 (0,00%) | 2 (0,13%) |
| FPS AI realtime hiệu dụng | 14,998 | 14,980 |
| Năng lực lõi AI ước tính | 28,96 FPS | 25,01 FPS |
| Độ trễ AI trung bình | 34,53 ms | 39,98 ms |
| Độ trễ AI P95 | 48,86 ms | 53,74 ms |
| Số người trung bình mỗi frame | 19,05 | 40,94 |
| Số người nhiều nhất mỗi frame | 30 | 56 |
| Local ID sinh ra | 608 | 314 |
| Stable ID sau hợp nhất | 590 | 313 |
| Lần tái nhận dạng OSNet | 53 | 38 |
| Sửa Stable ID đến trễ | 35 | 37 |
| Đếm lặp bị chặn | 87 | 46 |

## Đánh giá

- Cả hai video đều đáp ứng mục tiêu camera 15 FPS theo mô phỏng. `vd1` không bỏ frame; `vd2` chỉ bỏ 0,13% dù mật độ trung bình khoảng 41 người/frame.
- `vd2` nặng hơn rõ rệt: độ trễ trung bình tăng từ 34,53 ms lên 39,98 ms. Tuy vậy P95 vẫn thấp hơn chu kỳ 66,67 ms của camera 15 FPS, nên phần lớn frame được xử lý kịp.
- Cơ chế OSNet sửa ID đến trễ đã hoạt động: 35 lần trên `vd1` và 37 lần trên `vd2`. Điều này xác nhận hệ thống có xét lại Stable ID sau khi embedding xuất hiện, thay vì khóa vĩnh viễn ID tạm.
- Với tải tương tự hai video này, đặt Logitech C270 ở 1280 x 720, 15 FPS là phù hợp hơn 30 FPS. 30 FPS sẽ tạo áp lực lớn hơn, đặc biệt khi cảnh có trên 40 người.

## Lưu ý về độ chính xác đếm

Các giá trị IN/OUT không được dùng để kết luận accuracy trong lần benchmark này. Hai video không có ground truth A/B tương ứng với ROI đang cấu hình. Phép thử sử dụng hai dải ngang chỉ dành cho benchmark và không sửa ROI trong `config.yaml`.

Muốn đo chính xác đếm người, cần lập một bảng ground truth gồm thời điểm từng người đi trọn hành trình A sang B hoặc B sang A, rồi so sánh với sự kiện hệ thống. Các chỉ số cần báo cáo khi đó là số đúng, đếm thiếu, đếm thừa và sai hướng.

## Phạm vi của phép giả lập

Phép thử phản ánh khả năng xử lý realtime của lõi AI và cơ chế bỏ frame mới nhất. Nó chưa tái tạo hoàn toàn phần cứng camera thật như nhòe chuyển động, rung, autofocus cố định, RightLight 2, USB/driver và thay đổi phơi sáng ngoài trời. Do đó vẫn cần một lượt kiểm thử C270 thực tế để xác nhận accuracy cuối cùng.
