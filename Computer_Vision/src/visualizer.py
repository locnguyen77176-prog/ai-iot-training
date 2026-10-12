import cv2
import numpy as np
import yaml
from typing import List, Tuple, Dict, Any, Optional


class Visualizer:
    """
    Module phụ trách hiển thị trực quan (On-Screen Display - OSD):
    - Vẽ 2 Vùng Không Gian ROI bán trong suốt kèm nhãn định danh và hướng di chuyển.
    - Vẽ Bounding Box toàn thân với 4 góc chữ L phong cách camera AI thương mại.
    - Vẽ Điểm neo tiếp đất bàn chân (Ground Footstep Anchor) phát sáng tại chân người.
    - Hiển thị bảng điều khiển HUD (FPS, IN, OUT, Occupancy, Backend GPU/CPU).
    """
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.show_trail = False
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                self.show_trail = cfg.get("ui", {}).get("show_trail", False)
        except Exception:
            self.show_trail = False

    def draw_hud(self, frame: np.ndarray, total_in: int, total_out: int, 
                 fps: float, is_cuda: bool = True) -> np.ndarray:
        """Vẽ bảng điều khiển OSD bán trong suốt (Semi-transparent HUD) góc trên bên trái"""
        overlay = frame.copy()
        h, w = frame.shape[:2]

        pad = 15
        panel_w = 340
        panel_h = 160
        cv2.rectangle(overlay, (pad, pad), (pad + panel_w, pad + panel_h), (20, 20, 25), -1)
        cv2.rectangle(overlay, (pad, pad), (pad + panel_w, pad + panel_h), (100, 100, 120), 1)

        alpha = 0.82
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Tiêu đề
        cv2.putText(frame, "AI SMART PEOPLE COUNTER", (pad + 15, pad + 30), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, (240, 240, 240), 1, cv2.LINE_AA)

        # Thống kê IN / OUT
        cv2.putText(frame, f"IN:  {total_in}", (pad + 15, pad + 70), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 255, 120), 2, cv2.LINE_AA)
        cv2.putText(frame, f"OUT: {total_out}", (pad + 170, pad + 70), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 70, 255), 2, cv2.LINE_AA)

        # Hiện diện bên trong (Occupancy)
        net_count = max(0, total_in - total_out)
        cv2.putText(frame, f"Occupancy: {net_count}", (pad + 15, pad + 105), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)

        # Trạng thái GPU & FPS
        gpu_text = "CUDA GPU" if is_cuda else "CPU"
        cv2.putText(frame, f"FPS: {fps:.1f} | Backend: {gpu_text}", (pad + 15, pad + 135), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        return frame

    def draw_zones(self, frame: np.ndarray, zone_a: List[List[int]], zone_b: List[List[int]],
                   in_label: str = "IN (VÀO)", out_label: str = "OUT (RA)") -> np.ndarray:
        """
        Vẽ 2 Vùng Không Gian (Zone A: Ngoài & Zone B: Trong) với hiệu ứng bán trong suốt,
        viền phát sáng neon, tên nhãn và mũi tên chỉ hướng chuyển tiếp.
        """
        overlay = frame.copy()
        pts_a = np.array(zone_a, dtype=np.int32)
        pts_b = np.array(zone_b, dtype=np.int32)

        # 1. Vẽ mảng màu bán trong suốt cho 2 vùng
        cv2.fillPoly(overlay, [pts_a], (30, 180, 80))   # Zone A (Ngoài): Xanh lá
        cv2.fillPoly(overlay, [pts_b], (220, 100, 30))  # Zone B (Trong): Cam / Xanh dương

        alpha = 0.22
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # 2. Vẽ đường viền đa giác
        cv2.polylines(frame, [pts_a], isClosed=True, color=(0, 255, 120), thickness=2, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [pts_b], isClosed=True, color=(255, 160, 40), thickness=2, lineType=cv2.LINE_AA)

        # 3. Đánh dấu các đỉnh của đa giác
        for pt in zone_a:
            cv2.circle(frame, (int(pt[0]), int(pt[1])), 5, (0, 255, 120), -1)
        for pt in zone_b:
            cv2.circle(frame, (int(pt[0]), int(pt[1])), 5, (255, 160, 40), -1)

        # 4. Vẽ nhãn trung tâm của từng vùng
        mA = cv2.moments(pts_a)
        cxA = int(mA["m10"] / mA["m00"]) if mA["m00"] != 0 else int(np.mean(pts_a[:, 0]))
        cyA = int(mA["m01"] / mA["m00"]) if mA["m00"] != 0 else int(np.mean(pts_a[:, 1]))

        mB = cv2.moments(pts_b)
        cxB = int(mB["m10"] / mB["m00"]) if mB["m00"] != 0 else int(np.mean(pts_b[:, 0]))
        cyB = int(mB["m01"] / mB["m00"]) if mB["m00"] != 0 else int(np.mean(pts_b[:, 1]))

        # Box nhãn Vùng A
        label_a = "VUNG A (NGOAI)"
        (twA, thA), _ = cv2.getTextSize(label_a, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame, (cxA - int(twA/2) - 8, cyA - int(thA/2) - 6),
                      (cxA + int(twA/2) + 8, cyA + int(thA/2) + 6), (20, 20, 20), -1)
        cv2.rectangle(frame, (cxA - int(twA/2) - 8, cyA - int(thA/2) - 6),
                      (cxA + int(twA/2) + 8, cyA + int(thA/2) + 6), (0, 255, 120), 1)
        cv2.putText(frame, label_a, (cxA - int(twA/2), cyA + int(thA/2) - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 2, cv2.LINE_AA)

        # Box nhãn Vùng B
        label_b = "VUNG B (TRONG)"
        (twB, thB), _ = cv2.getTextSize(label_b, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame, (cxB - int(twB/2) - 8, cyB - int(thB/2) - 6),
                      (cxB + int(twB/2) + 8, cyB + int(thB/2) + 6), (20, 20, 20), -1)
        cv2.rectangle(frame, (cxB - int(twB/2) - 8, cyB - int(thB/2) - 6),
                      (cxB + int(twB/2) + 8, cyB + int(thB/2) + 6), (255, 160, 40), 1)
        cv2.putText(frame, label_b, (cxB - int(twB/2), cyB + int(thB/2) - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 160, 40), 2, cv2.LINE_AA)

        # 5. Mũi tên chỉ hướng di chuyển giữa 2 vùng
        mid_x = int((cxA + cxB) / 2)
        mid_y = int((cyA + cyB) / 2)
        cv2.arrowedLine(frame, (cxA, cyA), (cxB, cyB), (255, 255, 255), 2, tipLength=0.15)
        cv2.putText(frame, "A -> B = IN", (mid_x + 10, mid_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        return frame

    def draw_tracks(self, frame: np.ndarray, tracks: List[Dict[str, Any]], 
                    track_history: Optional[Dict[int, List[Tuple[int, int]]]] = None,
                    counted_tracks: Optional[Dict[int, dict]] = None) -> np.ndarray:
        """
        Vẽ Bounding Box toàn thân chuẩn thương mại (Hikvision/Dahua Style):
        - Khung bao toàn thân với 4 góc chữ L (Corner Brackets).
        - Điểm neo tiếp đất (Ground Footstep Anchor) phát sáng tại chân tiếp xúc mặt sàn.
        - Thẻ nhãn định danh ID trên đỉnh đầu với nền tối bán trong suốt.
        """
        if track_history is None:
            track_history = {}
        if counted_tracks is None:
            counted_tracks = {}

        for trk in tracks:
            track_id = trk['track_id']
            bbox = trk['bbox']
            x1, y1, x2, y2 = [int(v) for v in bbox]

            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            cx = int((x1 + x2) / 2)
            feet_y = y2

            # Màu sắc theo trạng thái
            if track_id in counted_tracks:
                direction = counted_tracks[track_id]['direction']
                color = (0, 255, 120) if direction == "IN" else (0, 70, 255)
                status_label = f"ID #{track_id} [{direction}]"
            else:
                color = (0, 215, 255)
                status_label = f"ID #{track_id}"

            # 1. Vẽ khung chữ nhật mảnh toàn thân
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)

            # 2. Vẽ 4 góc chữ L nổi bật (Corner Brackets)
            corner_len = max(8, min(22, int(min(w, h) * 0.20)))
            cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, 3, cv2.LINE_AA)
            cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, 3, cv2.LINE_AA)

            # 3. Vẽ ĐIỂM NEO TIẾP ĐẤT BƯỚC CHÂN (Ground Footstep Anchor)
            cv2.circle(frame, (cx, feet_y), 7, color, 2, cv2.LINE_AA)
            cv2.circle(frame, (cx, feet_y), 3, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.line(frame, (cx - 10, feet_y), (cx + 10, feet_y), color, 1, cv2.LINE_AA)

            # 4. Thẻ nhãn định danh ID trên đỉnh đầu (HUD Header Pill)
            (text_w, text_h), baseline = cv2.getTextSize(status_label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            tag_x1 = max(0, x1)
            tag_y1 = max(0, y1 - text_h - 8)
            tag_x2 = tag_x1 + text_w + 10
            tag_y2 = max(text_h + 8, y1)

            cv2.rectangle(frame, (tag_x1, tag_y1), (tag_x2, tag_y2), (20, 24, 30), -1)
            cv2.rectangle(frame, (tag_x1, tag_y1), (tag_x2, tag_y2), color, 1, cv2.LINE_AA)
            cv2.putText(frame, status_label, (tag_x1 + 5, tag_y2 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

        return frame

    def _save_zones_to_config(self, zone_a: List[List[int]], zone_b: List[List[int]]):
        """Ghi tọa độ 2 vùng mới vào file config.yaml"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            if "zones" not in cfg:
                cfg["zones"] = {}

            cfg["zones"]["zone_a"] = [[int(p[0]), int(p[1])] for p in zone_a]
            cfg["zones"]["zone_b"] = [[int(p[0]), int(p[1])] for p in zone_b]

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False, allow_unicode=True)
            print("[Visualizer] Đã lưu tọa độ 2 vùng vào config.yaml")
        except Exception as e:
            print(f"[Visualizer] Lỗi ghi config.yaml: {e}")
