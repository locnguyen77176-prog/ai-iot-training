import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import torch
from ultralytics import YOLO
from typing import List, Dict, Any


class YOLOTracker:
    """
    Wrapper phát hiện và theo dõi người (Person Tracking) sử dụng YOLOv8 và ByteTrack.
    Chỉ lọc đối tượng Người (COCO class 0) và gán track_id duy nhất.
    """
    def __init__(self, model_path: str = "yolov8n.pt", 
                 device: str = "cuda:0", 
                 confidence_threshold: float = 0.5, 
                 iou_threshold: float = 0.45,
                 tracker: str = "bytetrack.yaml"):
        self.model_path = model_path
        self.conf = confidence_threshold
        self.iou = iou_threshold
        self.tracker = tracker

        # Tự động chuyển về CPU nếu GPU không khả dụng
        if "cuda" in device and not torch.cuda.is_available():
            print(f"[Tracker] CUDA không khả dụng, tự động chuyển về CPU.")
            self.device = "cpu"
        else:
            self.device = device
            if "cuda" in self.device:
                try:
                    torch.backends.cudnn.benchmark = True
                except Exception:
                    pass

        print(f"[Tracker] Đang tải mô hình {self.model_path} trên thiết bị: {self.device}...")
        self.model = YOLO(self.model_path)
        print(f"[Tracker] Khởi tạo mô hình thành công!")

    def track(self, frame) -> List[Dict[str, Any]]:
        """
        Thực hiện inference và tracking trên frame.
        Trả về danh sách các đối tượng người có track_id:
        [{'track_id': int, 'bbox': [x1, y1, x2, y2], 'conf': float}]
        """
        if frame is None or frame.size == 0:
            return []

        # Chạy YOLOv8 tracking (classes=[0] đại diện cho class 'person')
        with torch.inference_mode():
            results = self.model.track(
                source=frame,
                persist=True,
                tracker=self.tracker,
                classes=[0],
                conf=self.conf,
                iou=self.iou,
                device=self.device,
                verbose=False,
                imgsz=480
            )

        tracked_objects = []
        if not results or len(results) == 0:
            return tracked_objects

        boxes = results[0].boxes
        if boxes is None or boxes.id is None:
            return tracked_objects

        ids = boxes.id.int().cpu().tolist()
        xyxys = boxes.xyxy.int().cpu().tolist()
        confs = boxes.conf.cpu().tolist()

        for track_id, bbox, conf in zip(ids, xyxys, confs):
            tracked_objects.append({
                'track_id': track_id,
                'bbox': bbox,
                'conf': round(conf, 2)
            })

        return tracked_objects
