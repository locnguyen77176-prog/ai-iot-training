import cv2
import numpy as np
import yaml
from typing import List, Tuple, Dict, Any, Optional


class Visualizer:
    """
    Module phụ trách hiển thị trực quan (On-Screen Display - OSD), vẽ Bounding Box,
    quỹ đạo di chuyển, vạch đếm ảo và giao diện chuột tương tác kéo/đặt vạch đếm.
    """
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.setup_mode = False
        self.temp_points = []
        self.status_message = "Nhấn 's' để chỉnh vạch đếm | 'q' để thoát"
        self.status_timer = 0

    def draw_hud(self, frame: np.ndarray, total_in: int, total_out: int, 
                 fps: float, is_cuda: bool = True, custom_stats: Optional[dict] = None) -> np.ndarray:
        """Vẽ bảng điều khiển OSD bán trong suốt (Semi-transparent HUD) góc trên bên trái"""
        overlay = frame.copy()
        h, w = frame.shape[:2]

        # Khung panel HUD
        pad = 15
        panel_w = 340
        panel_h = 160
        cv2.rectangle(overlay, (pad, pad), (pad + panel_w, pad + panel_h), (20, 20, 25), -1)
        # Đường viền panel neon
        cv2.rectangle(overlay, (pad, pad), (pad + panel_w, pad + panel_h), (100, 100, 120), 1)

        alpha = 0.8
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Tiêu đề
        cv2.putText(frame, "AI SMART PEOPLE COUNTER", (pad + 15, pad + 30), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, (240, 240, 240), 1, cv2.LINE_AA)

        # Thống kê IN / OUT
        # IN: Màu xanh lá dạ quang (0, 255, 120)
        cv2.putText(frame, f"IN:  {total_in}", (pad + 15, pad + 70), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 255, 120), 2, cv2.LINE_AA)
        
        # OUT: Màu đỏ tươi (0, 70, 255)
        cv2.putText(frame, f"OUT: {total_out}", (pad + 170, pad + 70), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 70, 255), 2, cv2.LINE_AA)

        # Hiện diện bên trong (Net count)
        net_count = max(0, total_in - total_out)
        cv2.putText(frame, f"Occupancy: {net_count}", (pad + 15, pad + 105), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)

        # Trạng thái GPU & FPS
        gpu_text = "CUDA GPU" if is_cuda else "CPU"
        cv2.putText(frame, f"FPS: {fps:.1f} | Backend: {gpu_text}", (pad + 15, pad + 135), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        # Nếu đang ở chế độ Setup Mode hoặc có thông báo trạng thái
        if self.setup_mode:
            banner_text = ">>> CHE DO CHINH VACH: Click 2 diem tren man hinh de dat vach moi <<<"
            cv2.rectangle(frame, (0, h - 45), (w, h), (0, 140, 255), -1)
            cv2.putText(frame, banner_text, (20, h - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        else:
            # Gợi ý phím tắt nhỏ ở đáy
            cv2.putText(frame, self.status_message, (15, h - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

        return frame

    def draw_counting_line(self, frame: np.ndarray, point_a: Tuple[int, int], 
                           point_b: Tuple[int, int], in_label: str = "IN", out_label: str = "OUT") -> np.ndarray:
        """Vẽ vạch đếm ảo với hiệu ứng dạ quang và nhãn chỉ dẫn hướng"""
        # Đường viền phát sáng mỏng
        cv2.line(frame, point_a, point_b, (255, 255, 0), 4, cv2.LINE_AA)
        cv2.line(frame, point_a, point_b, (0, 200, 255), 2, cv2.LINE_AA)

        # Đánh dấu 2 đầu mút
        cv2.circle(frame, point_a, 6, (0, 0, 255), -1)
        cv2.circle(frame, point_b, 6, (0, 0, 255), -1)

        # Tính điểm giữa của vạch để đặt nhãn
        mid_x = int((point_a[0] + point_b[0]) / 2)
        mid_y = int((point_a[1] + point_b[1]) / 2)

        # Tính vector pháp tuyến để vẽ mũi tên chỉ hướng IN/OUT
        vx = point_b[0] - point_a[0]
        vy = point_b[1] - point_a[1]
        length = np.hypot(vx, vy)
        if length > 0:
            nx = int(-vy / length * 30)
            ny = int(vx / length * 30)

            # Mũi tên chỉ hướng IN
            cv2.arrowedLine(frame, (mid_x, mid_y), (mid_x + nx, mid_y + ny), (0, 255, 120), 2, tipLength=0.3)
            cv2.putText(frame, in_label, (mid_x + nx - 10, mid_y + ny - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 120), 2, cv2.LINE_AA)

            # Mũi tên chỉ hướng OUT
            cv2.arrowedLine(frame, (mid_x, mid_y), (mid_x - nx, mid_y - ny), (0, 70, 255), 2, tipLength=0.3)
            cv2.putText(frame, out_label, (mid_x - nx - 10, mid_y - ny + 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 70, 255), 2, cv2.LINE_AA)

        return frame

    def draw_tracks(self, frame: np.ndarray, tracks: List[Dict[str, Any]], 
                    demographics_estimator, track_history: Dict[int, List[Tuple[int, int]]],
                    counted_tracks: Dict[int, dict]) -> np.ndarray:
        """Vẽ Bounding Box, quỹ đạo và nhãn định danh, giới tính, tuổi tác cho từng người"""
        for trk in tracks:
            track_id = trk['track_id']
            bbox = trk['bbox']
            x1, y1, x2, y2 = bbox

            # Màu sắc theo trạng thái:
            # - Đã đếm IN: Xanh lá
            # - Đã đếm OUT: Đỏ
            # - Đang theo dõi: Vàng cam
            if track_id in counted_tracks:
                direction = counted_tracks[track_id]['direction']
                color = (0, 255, 120) if direction == "IN" else (0, 70, 255)
            else:
                color = (0, 215, 255)

            # Vẽ bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

            # Vẽ điểm đáy (vị trí bước chân)
            cx = int((x1 + x2) / 2)
            cv2.circle(frame, (cx, y2), 5, color, -1)

            # Vẽ vệt quỹ đạo di chuyển (Trail) - dùng LINE_8 tối ưu phần cứng siêu tốc
            if track_id in track_history and len(track_history[track_id]) > 1:
                points = np.array(track_history[track_id], np.int32)
                cv2.polylines(frame, [points], False, color, 2, cv2.LINE_8)

            # Nhãn thông tin: ID + Giới tính (Nam/Nữ) + Tỷ lệ %
            info = demographics_estimator.get_display_info(track_id)
            if len(info) == 3:
                gender, _, conf = info
            else:
                gender, _ = info
                conf = 0.0

            if gender != "Unknown":
                osd_gender = "Nam" if gender in ("Nam", "Male") else "Nu"
                pct = int(round(conf * 100))
                if pct > 0:
                    label = f"ID:{track_id} | {osd_gender} {pct}%"
                else:
                    label = f"ID:{track_id} | {osd_gender}"
            else:
                label = f"ID:{track_id}"

            (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w + 10, y1), color, -1)
            cv2.putText(frame, label, (x1 + 5, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

        return frame

    def mouse_callback(self, event, x, y, flags, param):
        """Xử lý sự kiện click chuột để đặt lại vạch đếm trực quan"""
        if not self.setup_mode:
            return

        line_counter = param.get("line_counter")

        if event == cv2.EVENT_LBUTTONDOWN:
            self.temp_points.append((x, y))
            print(f"[Visualizer] Đã chọn điểm {len(self.temp_points)}: ({x}, {y})")

            if len(self.temp_points) == 2:
                p_a, p_b = self.temp_points[0], self.temp_points[1]
                if line_counter is not None:
                    line_counter.set_line(p_a, p_b)

                # Lưu cập nhật vào config.yaml
                self._save_line_to_config(p_a, p_b)
                self.setup_mode = False
                self.temp_points.clear()
                self.status_message = "Vach dem da duoc cap nhat thanh cong vao config.yaml!"
                print(f"[Visualizer] Cập nhật vạch mới thành công: A={p_a}, B={p_b}")

    def _save_line_to_config(self, point_a: Tuple[int, int], point_b: Tuple[int, int]):
        """Ghi tọa độ vạch mới ngược lại file config.yaml"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            if "counting_line" not in cfg:
                cfg["counting_line"] = {}

            cfg["counting_line"]["point_a"] = list(point_a)
            cfg["counting_line"]["point_b"] = list(point_b)

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False, allow_unicode=True)
            print("[Visualizer] Đã lưu vạch mới vào config.yaml")
        except Exception as e:
            print(f"[Visualizer] Lỗi ghi config.yaml: {e}")
