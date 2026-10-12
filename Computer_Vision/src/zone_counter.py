import time
from typing import List, Tuple, Dict, Optional, Any
import cv2
import numpy as np


class DualZoneCounter:
    """
    Hệ Thống Đếm Người Ra/Vào Bằng 2 Vùng Không Gian (Dual-Zone State Machine).
    - Vùng A (Zone A): Thường đặt ở phía Ngoài cửa.
    - Vùng B (Zone B): Thường đặt ở phía Trong cửa.
    - Máy trạng thái hữu hạn (FSM):
        * IN (Vào): Đi từ Vùng A -> Vùng B -> Khóa LOCKED_IN (không đếm lặp khi đứng lắc lư).
        * OUT (Ra): Đi từ Vùng B -> Vùng A -> Khóa LOCKED_OUT.
        * Reset trạng thái khi đối tượng rời khỏi hoàn toàn cả 2 vùng ROI.
    """
    def __init__(self, zone_a: List[List[int]], zone_b: List[List[int]],
                 in_label: str = "IN", out_label: str = "OUT",
                 cooldown_seconds: float = 3.0,
                 state_ttl_seconds: float = 120.0,
                 min_zone_hits: int = 2,
                 canvas_w: int = 1280, canvas_h: int = 720):
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h
        self.in_label = in_label
        self.out_label = out_label
        self.cooldown_seconds = cooldown_seconds
        self.state_ttl_seconds = max(8.0, float(state_ttl_seconds))
        self.min_zone_hits = max(1, int(min_zone_hits))

        # Thiết lập tọa độ 2 vùng (Polygon numpy array)
        self.zone_a_pts: List[List[int]] = []
        self.zone_b_pts: List[List[int]] = []
        self.zone_a_poly: Optional[np.ndarray] = None
        self.zone_b_poly: Optional[np.ndarray] = None
        self.set_zones(zone_a, zone_b)

        # Quản lý trạng thái từng track_id
        self.track_states: Dict[int, Dict[str, Any]] = {}
        self.counted_tracks: Dict[int, Dict[str, Any]] = {}
        self.track_history: Dict[int, List[Tuple[int, int]]] = {}

        # Thống kê tổng số
        self.total_in = 0
        self.total_out = 0

    def set_zones(self, zone_a: List[List[int]], zone_b: List[List[int]]):
        """Cập nhật tọa độ 2 vùng ROI từ giao diện"""
        self.zone_a_pts = [[int(pt[0]), int(pt[1])] for pt in zone_a]
        self.zone_b_pts = [[int(pt[0]), int(pt[1])] for pt in zone_b]
        self.zone_a_poly = np.array(self.zone_a_pts, dtype=np.int32)
        self.zone_b_poly = np.array(self.zone_b_pts, dtype=np.int32)

    def get_zones(self) -> Dict[str, List[List[int]]]:
        """Lấy tọa độ 2 vùng hiện tại"""
        return {
            "zone_a": self.zone_a_pts,
            "zone_b": self.zone_b_pts
        }

    def reset_counts(self):
        """Reset bộ đếm và lịch sử trạng thái"""
        self.total_in = 0
        self.total_out = 0
        self.track_states.clear()
        self.counted_tracks.clear()
        self.track_history.clear()

    @staticmethod
    def get_bottom_center(bbox: List[int]) -> Tuple[int, int]:
        """Lấy điểm đáy tâm (bước chân) của Bounding Box"""
        cx = int((bbox[0] + bbox[2]) / 2)
        cy = int(bbox[3])
        return (cx, cy)

    def _check_point_in_poly(self, point: Tuple[int, int], poly: Optional[np.ndarray]) -> bool:
        """Kiểm tra điểm có nằm trong đa giác hay không (Point in Polygon test)"""
        if poly is None or len(poly) < 3:
            return False
        return cv2.pointPolygonTest(poly, (float(point[0]), float(point[1])), False) >= 0

    def _determine_zone(self, bbox: List[int]) -> str:
        """
        Xác định đối tượng đang thuộc vùng nào (A, B hoặc NONE).
        Sử dụng DUY NHẤT vị trí tiếp xúc bước chân (Bottom Feet Anchor Point) để đảm bảo chuẩn xác tuyệt đối.
        """
        feet_point = self.get_bottom_center(bbox)

        in_a = self._check_point_in_poly(feet_point, self.zone_a_poly)
        in_b = self._check_point_in_poly(feet_point, self.zone_b_poly)

        if in_a and not in_b:
            return "A"
        if in_b and not in_a:
            return "B"

        return "NONE"

    def _merge_remapped_state(self, provisional_id: int, stable_id: int) -> None:
        """Merge FSM evidence after a provisional identity is corrected."""
        if provisional_id == stable_id:
            return

        provisional = self.track_states.pop(provisional_id, None)
        stable = self.track_states.get(stable_id)
        if provisional is not None:
            if stable is None:
                self.track_states[stable_id] = provisional
            else:
                # Preserve the old journey state (for example IN_A), while
                # carrying consecutive-zone evidence gathered under the temp ID.
                if provisional.get('candidate_zone') in ('A', 'B'):
                    stable['candidate_zone'] = provisional['candidate_zone']
                    stable['zone_hits'] = max(
                        stable.get('zone_hits', 0), provisional.get('zone_hits', 0)
                    )
                stable['last_seen_time'] = max(
                    stable.get('last_seen_time', 0), provisional.get('last_seen_time', 0)
                )

        provisional_history = self.track_history.pop(provisional_id, [])
        if provisional_history:
            merged = self.track_history.get(stable_id, []) + provisional_history
            self.track_history[stable_id] = merged[-40:]

        provisional_count = self.counted_tracks.pop(provisional_id, None)
        if provisional_count is not None and stable_id not in self.counted_tracks:
            provisional_count['track_id'] = stable_id
            self.counted_tracks[stable_id] = provisional_count

    def update(self, tracks: List[dict]) -> List[dict]:
        """
        Cập nhật máy trạng thái FSM cho từng track trong frame hiện tại.
        Trả về danh sách sự kiện đếm vừa hoàn thành trong frame.
        """
        now = time.time()
        events = []
        current_active_ids = set()

        for trk in tracks:
            track_id = trk['track_id']
            remapped_from = trk.get('identity_remapped_from')
            if remapped_from is not None:
                self._merge_remapped_state(int(remapped_from), int(track_id))
            bbox = trk['bbox']
            current_active_ids.add(track_id)

            curr_pos = self.get_bottom_center(bbox)
            if track_id not in self.track_history:
                self.track_history[track_id] = []
            self.track_history[track_id].append(curr_pos)
            if len(self.track_history[track_id]) > 40:
                self.track_history[track_id].pop(0)

            curr_zone = self._determine_zone(bbox)

            # Khởi tạo đối tượng mới nếu chưa có trong bộ nhớ FSM
            if track_id not in self.track_states:
                self.track_states[track_id] = {
                    'state': 'NONE',
                    'first_zone': curr_zone if curr_zone in ("A", "B") else None,
                    'first_seen_time': now,
                    'last_seen_time': now,
                    'last_zone': "NONE",
                    'candidate_zone': curr_zone,
                    'zone_hits': 1,
                    'counted_time': None,
                    'direction': None
                }
                if self.min_zone_hits == 1:
                    if curr_zone == "A":
                        self.track_states[track_id]['state'] = 'IN_A'
                    elif curr_zone == "B":
                        self.track_states[track_id]['state'] = 'IN_B'
                    self.track_states[track_id]['last_zone'] = curr_zone
                continue

            t_data = self.track_states[track_id]
            t_data['last_seen_time'] = now
            state = t_data['state']

            # Chỉ công nhận vùng sau N frame liên tiếp, chống bbox rung/nhảy vùng.
            if curr_zone == t_data.get('candidate_zone'):
                t_data['zone_hits'] = t_data.get('zone_hits', 0) + 1
            else:
                t_data['candidate_zone'] = curr_zone
                t_data['zone_hits'] = 1
            stable_zone = curr_zone if t_data['zone_hits'] >= self.min_zone_hits else t_data.get('last_zone', "NONE")

            # ==========================================================
            # FSM TRANSITION LOGIC (Xử lý chuyển trạng thái)
            # ==========================================================
            if state == 'NONE':
                if stable_zone == "A":
                    t_data['state'] = 'IN_A'
                    if t_data['first_zone'] is None:
                        t_data['first_zone'] = 'A'
                elif stable_zone == "B":
                    t_data['state'] = 'IN_B'
                    if t_data['first_zone'] is None:
                        t_data['first_zone'] = 'B'

            elif state == 'IN_A':
                # Đang xuất phát từ Vùng A, nếu bước sang Vùng B -> KÍCH HOẠT LƯỢT VÀO (IN)
                if stable_zone == "B":
                    self.total_in += 1
                    t_data['state'] = 'LOCKED_IN'
                    t_data['counted_time'] = now
                    t_data['direction'] = 'IN'

                    self.counted_tracks[track_id] = {
                        'direction': 'IN',
                        'time': now,
                        'track_id': track_id
                    }

                    events.append({
                        'track_id': track_id,
                        'direction': 'IN',
                        'bbox': bbox,
                        'timestamp': now
                    })
                    print(f"[DualZone] Track #{track_id} Chuyen Vung A -> B => DEM VAO (IN). Tong IN: {self.total_in}")

            elif state == 'IN_B':
                # Đang xuất phát từ Vùng B, nếu bước sang Vùng A -> KÍCH HOẠT LƯỢT RA (OUT)
                if stable_zone == "A":
                    self.total_out += 1
                    t_data['state'] = 'LOCKED_OUT'
                    t_data['counted_time'] = now
                    t_data['direction'] = 'OUT'

                    self.counted_tracks[track_id] = {
                        'direction': 'OUT',
                        'time': now,
                        'track_id': track_id
                    }

                    events.append({
                        'track_id': track_id,
                        'direction': 'OUT',
                        'bbox': bbox,
                        'timestamp': now
                    })
                    print(f"[DualZone] Track #{track_id} Chuyen Vung B -> A => DEM RA (OUT). Tong OUT: {self.total_out}")

            elif state in ('LOCKED_IN', 'LOCKED_OUT'):
                # Đối tượng đã được đếm xong!
                # 1. Nếu vẫn còn ở trong Vùng A/B hoặc chưa hết thời gian cooldown -> Giữ nguyên khóa LOCKED chống đếm lặp
                # 2. Khi ĐÃ RỜI KHỎI CẢ 2 VÙNG (curr_zone == "NONE") VÀ đã hết cooldown -> Reset về NONE để sẵn sàng cho chu trình mới
                counted_time = t_data.get('counted_time') or 0
                if stable_zone == "NONE" and (now - counted_time) >= self.cooldown_seconds:
                    t_data['state'] = 'NONE'
                    t_data['first_zone'] = None

            t_data['last_zone'] = stable_zone

        # Giữ FSM bằng thời gian nhớ ID để vẫn hoàn tất A -> B sau một lần che khuất dài.
        stale_ids = [
            tid for tid, data in self.track_states.items()
            if (now - data['last_seen_time']) > self.state_ttl_seconds and tid not in current_active_ids
        ]
        for tid in stale_ids:
            del self.track_states[tid]
            if tid in self.track_history:
                del self.track_history[tid]
            self.counted_tracks.pop(tid, None)

        return events
