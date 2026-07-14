# Tài Liệu Thiết Kế: Website Giới Thiệu Loa Smart Home (Local AI + IoT)

Tài liệu này ghi lại kết quả của quá trình thảo luận thiết kế (brainstorming) cho website giới thiệu sản phẩm Loa thông minh tích hợp AI xử lý ngôn ngữ tự nhiên Local và điều khiển nhà thông minh IoT.

---

## 1. Tóm Tắt Dự Án (Understanding Summary)
*   **Sản phẩm:** Một trang đơn Landing Page giới thiệu toàn diện sản phẩm Loa Smart Home.
*   **Mục đích:** Giới thiệu công nghệ độc đáo (AI Local xử lý offline & điều khiển IoT bảo mật), thu hút sự quan tâm của khách hàng cá nhân và hộ gia đình (B2C), hướng người dùng đến việc đăng ký nhận thông tin mở bán sớm.
*   **Đối tượng khách hàng:** Người tiêu dùng cá nhân, hộ gia đình muốn nâng cấp nhà thông minh bảo mật cao, không phụ thuộc vào internet hay lưu trữ đám mây.
*   **Ràng buộc cốt lõi:**
    *   Sử dụng **React + Vite + Vanilla CSS** để đảm bảo tốc độ tải trang tối ưu và quản lý dạng component hiện đại.
    *   Thiết kế giao diện **Dark Mode hiện đại**, kết hợp hiệu ứng kính mờ (glassmorphism) và dải đèn neon phát sáng (Ice Blue & Tím Neon) tượng trưng cho công nghệ AI.
    *   Cấu trúc trang đơn (Landing Page) cuộn mượt mà.
*   **Ngoài phạm vi (Non-goals):** Không tích hợp giỏ hàng thanh toán trực tuyến; không kết nối điều khiển thiết bị IoT vật lý thực tế.

---

## 2. Các Giả Định Hệ Thống (Assumptions & NFRs)
*   **Hiệu năng:** Thời gian tải trang ban đầu FCP (First Contentful Paint) < 1.5 giây. Thiết kế responsive tối ưu cho cả điện thoại di động, máy tính bảng và máy tính để bàn.
*   **Quy mô:** Hỗ trợ lượng truy cập lớn thông qua triển khai trang tĩnh (Static Site) trên các nền tảng CDN (Vercel, Netlify hoặc GitHub Pages).
*   **Bảo mật:** Không có backend lưu trữ cơ sở dữ liệu riêng; biểu mẫu đăng ký email sẽ hoạt động bằng cơ chế giả lập client-side hiển thị phản hồi trực quan và sẵn sàng tích hợp API bên thứ ba.

---

## 3. Rủi Ro & Giải Pháp Khắc Phục (Risks & Mitigations)
*   **Rủi ro 1: Hiệu năng kết xuất CSS neon/glassmorphism trên thiết bị cũ:** Hiệu ứng đổ bóng mờ (box-shadow) và làm mờ nền (backdrop-filter) có thể gây giật lag trên các dòng điện thoại đời cũ.
    *   *Khắc phục:* Sử dụng thuộc tính CSS tối ưu hóa phần cứng (`will-change`, `transform`), giảm độ phức tạp của đổ bóng trên thiết bị di động bằng Media Queries.
*   **Rủi ro 2: Thiết kế thiếu hình ảnh thực tế của sản phẩm:** Hiện chưa có hình ảnh sản phẩm thực tế từ phía người dùng.
    *   *Khắc phục:* Sử dụng mô hình AI tạo ảnh để thiết kế các mockup sản phẩm loa 3D và sơ đồ minh họa công nghệ đồng bộ với bảng màu neon của website.

---

## 4. Nhật Ký Quyết Định Thiết Kế (Decision Log)
1.  **Công nghệ:** Chọn **React + Vite + Vanilla CSS** để tối ưu hóa hiệu năng tải và đóng gói nhẹ nhàng.
2.  **Chủ đề giao diện:** Chọn **Tech-focused Dark Mode** phối màu nhấn neon để tạo sự lôi cuốn về mặt công nghệ AI đột phá.
3.  **Cấu trúc:** Chọn **Single Page** nhằm tập trung tối đa hành vi người dùng đi từ Hero giới thiệu xuống Form Đăng ký nhận tin ở chân trang thông qua liên kết cuộn mượt mà.
4.  **Tương tác chủ đạo:** Chọn xây dựng một **Sơ đồ luồng hoạt động tương tác (Data Flow)** bằng CSS animations để người dùng dễ hiểu cơ chế xử lý Offline của AI Local.

---

## 5. Cấu Trúc Các Component Giao Diện
*   **`Hero.jsx`:** Tiêu đề ấn tượng, nút kêu gọi hành động (CTA) cuộn xuống vùng đăng ký, và hình ảnh mockup loa 3D phát sáng.
*   **`DataFlow.jsx`:** Sơ đồ tương tác minh họa: Lệnh nói -> Loa xử lý Local (sóng âm neon) -> Thiết bị IoT phản hồi (Đèn sáng lên).
*   **`Features.jsx`:** Hệ thống lưới Bento Grid trưng bày 4 thế mạnh chính: Bảo mật offline, Mạng lưới IoT Matter/Zigbee, Chất âm Hi-Fi, và Tự động hóa thông minh.
*   **`Specs.jsx`:** Bảng thông số kỹ thuật chi tiết (NPU xử lý AI, kết nối không dây, cấu hình âm thanh, công tắc tắt micro vật lý).
*   **`FooterForm.jsx`:** Biểu mẫu điền email và tên đăng ký nhận ưu đãi đặt trước kèm hiệu ứng pháo hoa neon chúc mừng khi gửi thành công.
