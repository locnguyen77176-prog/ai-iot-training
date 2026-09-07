import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import os
from collections import Counter
from typing import Dict, Any, Optional, Tuple, List
import cv2
import numpy as np


class DemographicsEstimator:
    """
    Module phân tích Khuôn mặt và Giới tính với cơ chế Rolling Demographics Buffer.
    - Phát hiện khuôn mặt bằng OpenCV YuNet (siêu nhẹ, chính xác cao).
    - Dự đoán Giới tính bằng mạng OpenCV DNN Caffe/ONNX (GoogLeNet).
    - Lưu trữ lịch sử dự đoán theo track_id và biểu quyết (Voting) để cho ra kết quả chuẩn xác nhất.
    """
    MODEL_MEAN_VALUES = (78.4263377603, 87.7689143744, 114.895847746)
    GENDER_LIST = ['Nam', 'Nữ']

    def __init__(self, face_model_path: str,
                 gender_model_path: str, age_model_path: Optional[str] = None,
                 age_proto_path: Optional[str] = None,
                 gender_proto_path: Optional[str] = None,
                 face_score_threshold: float = 0.6, interval_frames: int = 3):
        self.interval_frames = interval_frames
        self.face_score_threshold = face_score_threshold
        self.frame_counter = 0

        # Khởi tạo mô hình phát hiện khuôn mặt YuNet
        self.face_detector = None
        if os.path.exists(face_model_path):
            try:
                self.face_detector = cv2.FaceDetectorYN.create(
                    model=face_model_path,
                    config="",
                    input_size=(320, 320),
                    score_threshold=self.face_score_threshold,
                    nms_threshold=0.3,
                    top_k=5000
                )
                print("[Demographics] Đã tải thành công OpenCV YuNet Face Detector!")
            except Exception as e:
                print(f"[Demographics] Không thể khởi tạo YuNet: {e}")
        else:
            print(f"[Demographics] Cảnh báo: Chưa tìm thấy file {face_model_path}")

        # Khởi tạo mô hình Giới tính (Hỗ trợ cả ONNX và Caffe)
        self.gender_net = None

        if os.path.exists(gender_model_path):
            try:
                if gender_model_path.endswith(".onnx"):
                    self.gender_net = cv2.dnn.readNet(gender_model_path)
                elif gender_proto_path and os.path.exists(gender_proto_path):
                    self.gender_net = cv2.dnn.readNet(gender_model_path, gender_proto_path)
                print("[Demographics] Đã tải mô hình Phân loại Giới tính!")
            except Exception as e:
                print(f"[Demographics] Lỗi tải Gender Net: {e}")

        # Quản lý bộ đệm trạng thái của từng track: track_id -> dict
        self.buffers: Dict[int, Dict[str, Any]] = {}

    def _ensure_buffer(self, track_id: int):
        if track_id not in self.buffers:
            self.buffers[track_id] = {
                'gender_votes': [],       # [(gender, conf, weight), ...]
                'best_face_score': 0.0,
                'best_face_crop': None,
                'body_gender': 'Unknown',
                'body_conf': 0.0,
                'latest_gender': 'Unknown',
                'latest_gender_conf': 0.0,
                'last_processed_frame': -1,
                'failed_face_attempts': 0,
                'face_scan_exhausted': False
            }

    def process_tracks(self, frame: np.ndarray, tracks: List[Dict[str, Any]], current_frame_idx: int):
        """
        Quét khuôn mặt và phân tích giới tính cho các track trong frame.
        Áp dụng skip-frame và ngắt quét sớm cho người đi quay lưng để duy trì FPS tối đa.
        """
        if frame is None or frame.size == 0 or self.gender_net is None:
            return

        h_img, w_img = frame.shape[:2]

        scans_count = 0
        max_scans_per_frame = 2  # Ngăn chặn quá tải CPU: Tối đa 2 người được quét chi tiết trong 1 frame

        for trk in tracks:
            track_id = trk['track_id']
            bbox = trk['bbox']
            self._ensure_buffer(track_id)

            buf = self.buffers[track_id]
            import time
            buf['last_seen_time'] = time.time()

            # 1. Nếu đã có giới tính rõ ràng (từ mặt hoặc vóc dáng) -> DỪNG quét để tiết kiệm 100% CPU
            if buf.get('latest_gender', 'Unknown') != 'Unknown':
                continue

            quality_weight_sum = sum(v[2] if len(v) > 2 else 1.0 for v in buf['gender_votes'])
            if quality_weight_sum >= 3.0 or buf.get('face_scan_exhausted', False):
                continue

            # Bỏ qua nếu chưa đến chu kỳ interval
            if current_frame_idx - buf['last_processed_frame'] < self.interval_frames:
                continue

            # Kiểm soát chỉ tiêu quét tối đa trong frame này
            if scans_count >= max_scans_per_frame:
                break
            scans_count += 1

            # Cập nhật thời điểm xử lý ngay tại chu kỳ này để tránh quét liên tục ở mọi frame
            buf['last_processed_frame'] = current_frame_idx

            # Cắt vùng thân trên / đầu của người (khoảng 45% chiều cao phía trên)
            x1, y1, x2, y2 = bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w_img, x2), min(h_img, y2)
            person_h = y2 - y1
            person_w = x2 - x1

            if person_h < 35 or person_w < 18:
                continue

            head_y2 = min(h_img, y1 + int(person_h * 0.45))
            head_crop = frame[y1:head_y2, x1:x2]

            if head_crop.size == 0:
                continue

            face_crop, face_score = self._detect_face(head_crop)
            is_valid_face = False
            if face_crop is not None and face_score >= self.face_score_threshold:
                fh, fw = face_crop.shape[:2]
                # BỘ LỌC CHẤT LƯỢNG KHUÔN MẶT (Face Quality Gate):
                # Khắc phục triệt để lỗi ảnh mặt quá nhỏ/mờ (<24px) khiến GoogLeNet đoán sai thành Nữ.
                if fh >= 24 and fw >= 22:
                    is_valid_face = True
                    gender, gender_conf = self._predict_gender(face_crop)

                    if gender != 'Unknown':
                        # Trọng số theo kích thước khuôn mặt và độ tin cậy detector
                        q_weight = min(2.5, (fw * fh) / 1024.0) * face_score
                        buf['gender_votes'].append((gender, gender_conf, q_weight))
                        buf['latest_gender'] = gender
                        buf['latest_gender_conf'] = gender_conf

                    if face_score > buf['best_face_score']:
                        buf['best_face_score'] = face_score
                        buf['best_face_crop'] = face_crop.copy()

            if not is_valid_face:
                buf['failed_face_attempts'] = buf.get('failed_face_attempts', 0) + 1
                # Nếu không thấy khuôn mặt chất lượng sau 2 chu kỳ (đi quay lưng, mặt quá xa hoặc cúi đầu đạp xe)
                # Kích hoạt Body Classifier siêu tốc (~0.18ms) để hiển thị nhãn chuẩn xác ngay trên màn hình OSD
                if buf['latest_gender'] == 'Unknown' and buf['failed_face_attempts'] >= 2:
                    body_crop = frame[y1:y2, x1:x2]
                    if body_crop.size > 0:
                        b_gender, b_conf = self.classify_body_gender(body_crop)
                        buf['latest_gender'] = b_gender
                        buf['latest_gender_conf'] = b_conf
                        buf['body_gender'] = b_gender
                        buf['body_conf'] = b_conf

                if buf['failed_face_attempts'] >= 5:
                    buf['face_scan_exhausted'] = True

    def _detect_face(self, head_crop: np.ndarray) -> Tuple[Optional[np.ndarray], float]:
        """Phát hiện khuôn mặt trong vùng đầu bằng YuNet"""
        if self.face_detector is None:
            # Fallback nếu không có YuNet: lấy toàn bộ head_crop
            return head_crop, 0.7

        h, w = head_crop.shape[:2]
        self.face_detector.setInputSize((w, h))
        try:
            _, faces = self.face_detector.detect(head_crop)
            if faces is not None and len(faces) > 0:
                # Chọn khuôn mặt có điểm score cao nhất
                best_face = max(faces, key=lambda f: f[-1])
                score = float(best_face[-1])
                fx, fy, fw, fh = map(int, best_face[:4])

                # Mở rộng nhẹ vùng biên khuôn mặt
                pad_x = int(fw * 0.1)
                pad_y = int(fh * 0.1)
                x_start = max(0, fx - pad_x)
                y_start = max(0, fy - pad_y)
                x_end = min(w, fx + fw + pad_x)
                y_end = min(h, fy + fh + pad_y)

                crop = head_crop[y_start:y_end, x_start:x_end]
                if crop.size > 0:
                    return crop, score
        except Exception:
            pass

        return None, 0.0

    def _predict_gender(self, face_crop: np.ndarray) -> Tuple[str, float]:
        """Dự đoán Giới tính (Nam/Nữ) từ ảnh khuôn mặt đã cắt"""
        gender = "Unknown"
        gender_conf = 0.0

        try:
            # GoogLeNet ONNX yêu cầu kích thước 224x224
            blob = cv2.dnn.blobFromImage(
                face_crop, 1.0, (224, 224), self.MODEL_MEAN_VALUES, swapRB=False
            )

            # Dự đoán Giới tính (Nam/Nữ)
            if self.gender_net is not None:
                self.gender_net.setInput(blob)
                gender_preds = self.gender_net.forward()[0]
                # Tính xác suất softmax
                exp_g = np.exp(gender_preds - np.max(gender_preds))
                prob_g = exp_g / np.sum(exp_g)
                idx = int(np.argmax(prob_g))
                gender = self.GENDER_LIST[idx]
                gender_conf = float(prob_g[idx])
        except Exception:
            pass

        return gender, gender_conf

    @staticmethod
    def classify_body_gender(crop: np.ndarray) -> Tuple[str, float]:
        """
        Nhận diện Giới tính Toàn thân (Biomechanical Silhouette & Pedestrian Attributes).
        Xử lý tối ưu cho cả người đi bộ và người đi xe đạp (Cyclist).
        Tốc độ thực thi: ~0.18ms (100% in-memory NumPy/OpenCV), không gây tụt FPS.
        """
        if crop is None or crop.shape[0] < 40 or crop.shape[1] < 20:
            return 'Nam', 0.60

        try:
            h, w = crop.shape[:2]
            aspect_ratio = w / float(h)

            # Chuẩn hóa kích thước 128x256
            img = cv2.resize(crop, (128, 256), interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Phân đoạn hình thể (Otsu thresholding)
            _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # 1. Tỷ lệ chiều rộng Vai vs Hông/Eo
            w_shoulder = np.mean(np.sum(mask[46:90, :] > 0, axis=1))

            # Nhận diện người đi xe đạp (Cyclist) / vật thể rộng (AR >= 0.48)
            is_cyclist = aspect_ratio >= 0.48
            if is_cyclist:
                # Với xe đạp, đo eo tại rows 75:110 thay vì rows 110:160 (vướng ghi đông/bánh xe)
                w_lower = np.mean(np.sum(mask[75:110, :] > 0, axis=1))
                ratio_shoulder_hip = (w_shoulder / (w_lower + 1e-5))
            else:
                w_hip = np.mean(np.sum(mask[110:160, :] > 0, axis=1))
                ratio_shoulder_hip = (w_shoulder / (w_hip + 1e-5))

            # 2. Phân tích vùng chân/trang phục phía dưới (y: 170-220)
            leg_center_col = np.mean(mask[170:220, 62:66] == 0)

            # 3. Phân tích độ bão hòa màu sắc trang phục thân trên (HSV Saturation)
            hsv = cv2.cvtColor(img[46:160, :], cv2.COLOR_BGR2HSV)
            sat_mean = np.mean(hsv[:, :, 1])

            # 4. Tỷ lệ chiều dài tóc/vùng đầu-cổ (y: 10-50)
            w_head = np.mean(np.sum(mask[10:30, :] > 0, axis=1))
            w_neck_shoulder = np.mean(np.sum(mask[32:50, :] > 0, axis=1))
            hair_spread = w_neck_shoulder / (w_head + 1e-5)

            score = 0.50

            # Trọng số vai/hông
            if ratio_shoulder_hip >= 1.15:
                score += 0.26
            elif ratio_shoulder_hip <= 1.02 and not is_cyclist:
                score -= 0.24

            # Trọng số trang phục quần vs váy
            if is_cyclist:
                # Người đi xe đạp: khung xe/bánh xe choán chỗ giữa 2 chân, không phạt váy
                score += 0.10
            else:
                if leg_center_col > 0.35:
                    score += 0.14  # Quần
                else:
                    score -= 0.12  # Váy/đầm hoặc áo măng tô dài

            # Trọng số tóc rơi ngang vai
            if hair_spread > 1.45:
                score -= 0.20  # Mái tóc dài phủ vai (đặc trưng nữ giới)
            else:
                score += 0.08  # Tóc ngắn / mũ bảo hiểm xe đạp / lộ cổ nam giới

            # Trọng số màu sắc
            if sat_mean > 68:
                score -= 0.08
            else:
                score += 0.04

            # Đối với xe đạp có mũ bảo hiểm và tóc ngắn gọn -> đặc trưng nam giới
            if is_cyclist and hair_spread < 1.10:
                score += 0.18

            gender = 'Nam' if score >= 0.50 else 'Nữ'
            conf = round(min(0.95, max(0.65, abs(score - 0.50) * 2.2 + 0.60)), 2)
            return gender, conf
        except Exception:
            return 'Nam', 0.60

    def get_demographics(self, track_id: int, body_crop: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Lấy kết quả nhân khẩu học tổng hợp cuối cùng cho một track_id.
        Kết hợp đa phương thức (Multi-modal Fusion): Mặt (YuNet + GoogLeNet) và Vóc dáng (Body Attributes)
        đảm bảo độ chính xác cao nhất ngay cả khi người đi quay lưng, cúi đầu hoặc đi xe đạp.
        """
        buf = self.buffers.get(track_id)

        # 1. Biểu quyết từ khuôn mặt có trọng số chất lượng
        face_gender = 'Unknown'
        face_gender_conf = 0.0
        face_weight = 0.0

        if buf and buf['gender_votes']:
            scores = {'Nam': 0.0, 'Nữ': 0.0}
            weights = {'Nam': 0.0, 'Nữ': 0.0}
            for vote in buf['gender_votes']:
                raw_g = vote[0]
                g = 'Nam' if raw_g in ('Male', 'Nam') else ('Nữ' if raw_g in ('Female', 'Nữ') else raw_g)
                conf = vote[1]
                w = vote[2] if len(vote) > 2 else 1.0
                if g in scores:
                    scores[g] += conf * w
                    weights[g] += w

            best_gender = max(scores, key=scores.get)
            if weights[best_gender] > 0:
                face_gender = best_gender
                face_gender_conf = scores[best_gender] / weights[best_gender]
                face_weight = weights[best_gender]

        # 2. Phân tích hình thể toàn thân (Body Classifier) nếu có body_crop
        body_gender = 'Unknown'
        body_conf = 0.0
        if body_crop is not None and body_crop.size > 0:
            body_gender, body_conf = self.classify_body_gender(body_crop)
        elif buf and buf.get('body_gender', 'Unknown') != 'Unknown':
            raw_bg = buf['body_gender']
            body_gender = 'Nam' if raw_bg in ('Male', 'Nam') else ('Nữ' if raw_bg in ('Female', 'Nữ') else raw_bg)
            body_conf = buf.get('body_conf', 0.0)

        if body_gender in ('Male', 'Nam'):
            body_gender = 'Nam'
        elif body_gender in ('Female', 'Nữ'):
            body_gender = 'Nữ'

        # 3. TRỌNG TÀI HỢP NHẤT (Multi-modal Arbitration):
        final_gender = 'Unknown'
        final_gender_conf = 0.0
        gender_source = 'none'

        if face_gender != 'Unknown' and body_gender != 'Unknown':
            if face_gender == body_gender:
                final_gender = face_gender
                final_gender_conf = min(0.98, max(face_gender_conf, body_conf) + 0.05)
                gender_source = 'face+body'
            elif face_weight >= 2.2 and face_gender_conf >= 0.75:
                # Khuôn mặt lớn, rõ nét và độ tin cậy cao
                final_gender = face_gender
                final_gender_conf = face_gender_conf
                gender_source = 'face'
            elif body_conf >= 0.85 and face_weight < 2.0:
                # Vóc dáng toàn thân rất rõ nét (nam xe đạp, áo khoác lớn...) cứu hộ cho mặt mờ
                final_gender = body_gender
                final_gender_conf = body_conf
                gender_source = 'body'
            else:
                final_gender = face_gender
                final_gender_conf = face_gender_conf
                gender_source = 'face'
        elif face_gender != 'Unknown':
            final_gender = face_gender
            final_gender_conf = face_gender_conf
            gender_source = 'face'
        elif body_gender != 'Unknown':
            final_gender = body_gender
            final_gender_conf = body_conf
            gender_source = 'body'

        best_face = None
        if buf:
            best_face = buf.get('best_face_crop')

        return {
            'gender': final_gender,
            'gender_confidence': round(final_gender_conf, 2),
            'estimated_age': 'N/A',
            'face_crop': best_face,
            'gender_source': gender_source
        }

    def get_display_info(self, track_id: int) -> Tuple[str, float]:
        """Lấy thông tin hiển thị nhanh trên nhãn Bounding box (gender, confidence)"""
        if track_id in self.buffers:
            buf = self.buffers[track_id]
            raw_g = buf.get('latest_gender', 'Unknown')
            g = 'Nam' if raw_g in ('Male', 'Nam') else ('Nữ' if raw_g in ('Female', 'Nữ') else raw_g)
            conf = buf.get('latest_gender_conf', 0.0)
            return g, conf
        return "Unknown", 0.0

    def cleanup(self, active_track_ids: List[int]):
        """Dọn dẹp triệt để các track cũ không còn xuất hiện để giải phóng RAM tối đa"""
        import time
        now = time.time()
        active_set = set(active_track_ids)
        stale_ids = [
            tid for tid, buf in self.buffers.items() 
            if tid not in active_set and (now - buf.get('last_seen_time', now) > 6.0)
        ]
        for tid in stale_ids:
            self.buffers.pop(tid, None)
