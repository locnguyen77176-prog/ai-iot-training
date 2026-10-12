# Đánh giá bản ghi kiểm thử realtime `test1.mp4` và `test2.mp4`

## Phạm vi đo

Đây là phân tích từ bản ghi màn hình 30 FPS, không phải log profiler của tiến trình. Các chỉ số FPS, bộ đếm và trạng thái CUDA được đọc từ HUD. Hiện tượng khựng được đo trên vùng video camera bằng ngưỡng đứng hình liên tục từ 0,20 giây. RAM, VRAM và độ trễ camera-to-browser không xuất hiện trong bản ghi nên không thể xác định chính xác.

## Kết quả định lượng

| Chỉ số | test1.mp4 | test2.mp4 |
|---|---:|---:|
| Thời lượng quan sát | 100,5 giây | 401,7 giây |
| FPS của bản ghi màn hình | 30 FPS | 30 FPS |
| FPS AI trên HUD | khoảng 10,0 FPS | khoảng 9,7–10,2 FPS |
| Sự cố dừng/crash nhìn thấy | 0 | 0 |
| Đoạn đứng hình từ 0,20 giây | 1 | 72 |
| Tổng thời gian đứng hình đo được | 0,20 giây | 15,33 giây |
| Đoạn đứng hình dài nhất | 0,20 giây | 0,43 giây |
| Thay đổi bộ đếm trong bản ghi | +3 IN, +6 OUT | +72 IN, +91 OUT |

Các đoạn đứng hình là chỉ báo từ hình ảnh, không đồng nghĩa hoàn toàn với lỗi server: cảnh thật sự đứng yên cũng có thể bị bộ dò đứng hình ghi nhận.

## Hiệu suất

### FPS

FPS ổn định quanh 10 FPS trong cả hai bản ghi và không có xu hướng giảm dần theo thời gian. Điều này cho thấy không có dấu hiệu rõ ràng của suy giảm hiệu suất tích lũy trong khoảng 6 phút 42 giây dài nhất. Tuy nhiên, 10 FPS thấp hơn mục tiêu cấu hình hiện tại là 15 FPS, nên bài kiểm thử chưa đạt mục tiêu realtime mong muốn.

### Thời gian phản hồi và độ trễ

Với 10 FPS, AI chỉ tạo một kết quả mới khoảng mỗi 100 ms. Bản ghi không chứa đồng hồ gắn tại thời điểm camera chụp nên không thể đo độ trễ đầu-cuối chính xác. `test2` có các khựng ngắn, dài nhất khoảng 433 ms; sau đó luồng tự tiếp tục.

### Bộ nhớ

Không có Task Manager, `nvidia-smi`, RAM tiến trình hoặc VRAM trong video. Vì vậy chưa thể báo mức dùng bộ nhớ, đỉnh bộ nhớ hay rò rỉ bộ nhớ. FPS không giảm dần chỉ cho phép kết luận rằng chưa thấy biểu hiện gián tiếp rõ ràng của rò rỉ trong thời gian quan sát, không phải bằng chứng loại trừ rò rỉ.

## Độ tin cậy

### Thời gian hoạt động

Cả hai phiên chạy xuyên suốt bản ghi, không thấy server dừng, camera báo mất kết nối hoặc trang web mất luồng. Thời gian hoạt động quan sát được lần lượt là 100,5 giây và 401,7 giây. Khoảng này chưa đủ để suy ra độ ổn định nhiều giờ hoặc nhiều ngày.

### Tỷ lệ lỗi và khôi phục

Không thấy lỗi ứng dụng hiện trên giao diện. Các khựng ngắn ở `test2` đều tự hồi phục, không cần tải lại trang. Chưa có tình huống rút USB, mất camera, lỗi CUDA hoặc khởi động lại server nên khả năng khôi phục sự cố cứng chưa được kiểm chứng.

### Độ chính xác

Không có ground truth ghi số người thực tế đi trọn A → B và B → A, do đó không thể tính precision, recall, tỷ lệ đếm thiếu hoặc đếm thừa bằng phần trăm.

Quan sát định tính:

- Phần lớn người nhìn rõ được phát hiện và có box liên tục.
- Các cửa sổ được xem chi tiết cho thấy bộ đếm tăng khi có người hoàn thành chuyển vùng, không thấy bộ đếm tự giảm hoặc reset giữa phiên.
- Cảnh có bóng cây mạnh, vùng sáng cháy và người chồng lấp. Box kém ổn định hơn ở mép ảnh, vùng B quá sáng và lúc nhiều người đi sát nhau; đây là các vị trí có nguy cơ mất ID và đếm thiếu.
- Số Local/Stable ID hiển thị tăng nhanh hơn số hành trình hoàn tất, cho thấy vẫn có phân mảnh ID hoặc nhiều người chỉ đi qua một phần ROI. Chỉ từ video không thể tách chính xác hai nguyên nhân.
- Camera bị di chuyển ở đầu/cuối phiên. Những khoảng này không nên đưa vào phép đo accuracy chính thức.

## Kết luận

- Độ ổn định ngắn hạn: đạt; không crash và tự tiếp tục sau các khựng ngắn.
- FPS mục tiêu 15: chưa đạt; thực tế quan sát khoảng 10 FPS.
- Độ mượt: `test1` tốt, `test2` trung bình do nhiều khựng 0,20–0,43 giây khi cảnh đông.
- Bộ nhớ: chưa có dữ liệu để đánh giá.
- Accuracy định lượng: chưa thể kết luận khi chưa có ground truth; chất lượng phát hiện nhìn chung khá nhưng còn rủi ro tại vùng cháy sáng, bóng mạnh, mép ảnh và đám đông.

## Phép thử cần bổ sung

1. Ghi log theo giây gồm capture FPS, AI FPS, display FPS, latency trung bình/P95, RAM và VRAM.
2. Chạy liên tục tối thiểu 2 giờ để phát hiện rò rỉ và suy giảm hiệu suất.
3. Thử rút/cắm lại USB và che camera để kiểm tra tự kết nối lại.
4. Lập ground truth cho ít nhất 100 hành trình, ghi rõ thời điểm và hướng, rồi tính đúng, thiếu, thừa và sai hướng.
