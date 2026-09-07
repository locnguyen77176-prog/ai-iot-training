import time
from typing import List, Tuple, Dict, Optional


def ccw(A: Tuple[float, float], B: Tuple[float, float], C: Tuple[float, float]) -> bool:
    """Kiểm tra hướng quay của 3 điểm (Counter-Clockwise)"""
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])


def segments_intersect(A: Tuple[float, float], B: Tuple[float, float], 
                       C: Tuple[float, float], D: Tuple[float, float]) -> bool:
    """Kiểm tra xem 2 đoạn thẳng AB và CD có cắt nhau hay không"""
    return (ccw(A, C, D) != ccw(B, C, D)) and (ccw(A, B, C) != ccw(A, B, D))


class VirtualLineCounter:
    """
    Quản lý vạch ảo (Virtual Counting Line) và phát hiện sự kiện cắt vạch (Line Crossing).
    Sử dụng tích có hướng 2D (Cross-Product) để xác định chuẩn xác chiều di chuyển IN hoặc OUT.
    """
    def __init__(self, point_a: List[int], point_b: List[int], 
                 in_label: str = "IN", out_label: str = "OUT", 
                 cooldown_seconds: float = 2.5):
        self.point_a = tuple(point_a)
        self.point_b = tuple(point_b)
        self.in_label = in_label
        self.out_label = out_label
        self.cooldown_seconds = cooldown_seconds

        # Lưu vết quỹ đạo di chuyển của từng track_id: track_id -> [(x, y), ...]
        self.track_history: Dict[int, List[Tuple[int, int]]] = {}
        # Quản lý cooldown tránh đếm lặp: track_id -> {'time': timestamp, 'direction': dir}
        self.counted_tracks: Dict[int, dict] = {}

        # Thống kê tổng số lượt
        self.total_in = 0
        self.total_out = 0

    def set_line(self, point_a: Tuple[int, int], point_b: Tuple[int, int]):
        """Cập nhật tọa độ vạch mới (khi người dùng vẽ bằng chuột)"""
        self.point_a = tuple(point_a)
        self.point_b = tuple(point_b)

    @staticmethod
    def get_bottom_center(bbox: List[int]) -> Tuple[int, int]:
        """Lấy điểm đáy tâm (bước chân) của Bounding Box [x1, y1, x2, y2]"""
        cx = int((bbox[0] + bbox[2]) / 2)
        cy = int(bbox[3])
        return (cx, cy)

    def update(self, tracks: List[dict]) -> List[dict]:
        """
        Cập nhật quỹ đạo và kiểm tra sự kiện cắt vạch cho danh sách track trong frame hiện tại.
        Mỗi track là dict: {'track_id': int, 'bbox': [x1, y1, x2, y2], 'conf': float}
        
        Trả về danh sách các sự kiện cắt vạch xảy ra trong frame này:
        [{'track_id': int, 'direction': 'IN'/'OUT', 'bbox': list, 'point': (x, y)}]
        """
        now = time.time()
        crossing_events = []
        current_active_ids = set()

        for trk in tracks:
            track_id = trk['track_id']
            bbox = trk['bbox']
            current_active_ids.add(track_id)

            curr_point = self.get_bottom_center(bbox)

            if track_id not in self.track_history:
                self.track_history[track_id] = [curr_point]
                continue

            self.track_history[track_id].append(curr_point)
            # Giữ tối đa 30 điểm gần nhất trong quỹ đạo
            if len(self.track_history[track_id]) > 30:
                self.track_history[track_id].pop(0)

            # Cần tối thiểu 2 điểm để tạo thành vector di chuyển
            prev_point = self.track_history[track_id][-2]

            # Kiểm tra giao cắt giữa đoạn thẳng [prev_point, curr_point] và vạch [point_a, point_b]
            if segments_intersect(self.point_a, self.point_b, prev_point, curr_point):
                # Kiểm tra debounce / cooldown
                if track_id in self.counted_tracks:
                    last_event = self.counted_tracks[track_id]
                    if now - last_event['time'] < self.cooldown_seconds:
                        continue  # Đang trong thời gian cooldown, không đếm trùng

                # Tính tích có hướng 2D (Cross-Product) giữa vector vạch AB và vector di chuyển
                # V_ab = B - A
                # V_mov = curr - prev
                # z = (B.x - A.x) * (curr.y - prev.y) - (B.y - A.y) * (curr.x - prev.x)
                v_ab_x = self.point_b[0] - self.point_a[0]
                v_ab_y = self.point_b[1] - self.point_a[1]
                v_mov_x = curr_point[0] - prev_point[0]
                v_mov_y = curr_point[1] - prev_point[1]

                cross_z = (v_ab_x * v_mov_y) - (v_ab_y * v_mov_x)

                # Quy ước: cross_z > 0 là IN, cross_z < 0 là OUT
                if cross_z > 0:
                    direction = self.in_label
                    self.total_in += 1
                else:
                    direction = self.out_label
                    self.total_out += 1

                self.counted_tracks[track_id] = {
                    'time': now,
                    'direction': direction
                }

                crossing_events.append({
                    'track_id': track_id,
                    'direction': direction,
                    'bbox': bbox,
                    'point': curr_point
                })

        # Xóa triệt để lịch sử các track_id đã rời khỏi khung hình để giải phóng RAM tối đa
        stale_history = [tid for tid in self.track_history if tid not in current_active_ids]
        for tid in stale_history:
            self.track_history.pop(tid, None)

        # Dọn dẹp bộ nhớ đệm cooldown của các đối tượng đã rời đi
        stale_counted = [tid for tid in self.counted_tracks if tid not in current_active_ids and (now - self.counted_tracks[tid]['time'] > 10.0)]
        for tid in stale_counted:
            self.counted_tracks.pop(tid, None)

        return crossing_events

    def reset_counts(self):
        """Đặt lại số lượng đếm về 0"""
        self.total_in = 0
        self.total_out = 0
        self.counted_tracks.clear()
