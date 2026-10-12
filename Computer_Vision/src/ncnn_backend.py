"""NCNN inference and lightweight tracking for Raspberry Pi deployments.

This module deliberately depends only on numpy, OpenCV and the NCNN Python
binding.  PyTorch and Ultralytics are not imported on the NCNN path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


def _load_ncnn():
    try:
        import ncnn  # type: ignore

        return ncnn
    except ImportError as exc:
        raise RuntimeError(
            "NCNN backend was selected, but the 'ncnn' Python module is not installed. "
            "On Raspberry Pi, run scripts/install_ncnn_pi.sh first."
        ) from exc


def _check_model_file(path: str) -> str:
    resolved = os.path.abspath(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(resolved)
    return resolved


def _configure_net(net, num_threads: int, use_vulkan: bool) -> None:
    net.opt.use_vulkan_compute = bool(use_vulkan)
    # These options exist in current official NCNN builds.  hasattr keeps the
    # code compatible with older Python bindings packaged by some Pi images.
    for name, value in (
        ("num_threads", max(1, int(num_threads))),
        ("use_fp16_packed", False),
        ("use_fp16_storage", False),
        ("use_fp16_arithmetic", False),
    ):
        if hasattr(net.opt, name):
            setattr(net.opt, name, value)


def _load_net(param_path: str, bin_path: str, num_threads: int, use_vulkan: bool):
    ncnn = _load_ncnn()
    net = ncnn.Net()
    _configure_net(net, num_threads, use_vulkan)
    param_path = _check_model_file(param_path)
    bin_path = _check_model_file(bin_path)
    param_ret = net.load_param(param_path)
    model_ret = net.load_model(bin_path)
    if param_ret not in (None, 0) or model_ret not in (None, 0):
        raise RuntimeError(
            f"NCNN could not load model (param={param_ret}, bin={model_ret}): "
            f"{param_path}, {bin_path}"
        )
    return ncnn, net


def _extract(extractor, output_blob: str) -> np.ndarray:
    result = extractor.extract(output_blob)
    if isinstance(result, tuple):
        if len(result) != 2:
            raise RuntimeError(f"Unexpected NCNN extract result: {len(result)} values")
        ret, mat = result
        if ret not in (None, 0):
            raise RuntimeError(f"NCNN extract('{output_blob}') failed with code {ret}")
    else:
        mat = result
    return np.asarray(mat, dtype=np.float32)


def _make_extractor(net, num_threads: int):
    extractor = net.create_extractor()
    if hasattr(extractor, "set_light_mode"):
        extractor.set_light_mode(True)
    if hasattr(extractor, "set_num_threads"):
        extractor.set_num_threads(max(1, int(num_threads)))
    return extractor


def _nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> List[int]:
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: List[int] = []
    while order.size:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[current], x1[rest])
        yy1 = np.maximum(y1[current], y1[rest])
        xx2 = np.minimum(x2[current], x2[rest])
        yy2 = np.minimum(y2[current], y2[rest])
        intersection = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[current] + areas[rest] - intersection
        iou = intersection / np.maximum(union, 1e-7)
        order = rest[iou <= float(iou_threshold)]
    return keep


class NcnnYoloDetector:
    """YOLO26n NCNN detector producing person boxes in original-image pixels."""

    def __init__(self, param_path: str, bin_path: str, imgsz: int = 640,
                 confidence_threshold: float = 0.25, iou_threshold: float = 0.60,
                 input_blob: str = "in0", output_blob: str = "out0",
                 num_threads: int = 4, use_vulkan: bool = False):
        self.imgsz = int(imgsz)
        self.conf = float(confidence_threshold)
        self.iou = float(iou_threshold)
        self.input_blob = input_blob
        self.output_blob = output_blob
        self.num_threads = max(1, int(num_threads))
        self.ncnn, self.net = _load_net(param_path, bin_path, self.num_threads, use_vulkan)

    def _letterbox(self, frame: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        height, width = frame.shape[:2]
        ratio = min(self.imgsz / width, self.imgsz / height)
        resized_w = max(1, int(round(width * ratio)))
        resized_h = max(1, int(round(height * ratio)))
        resized = cv2.resize(frame, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
        pad_x = (self.imgsz - resized_w) // 2
        pad_y = (self.imgsz - resized_h) // 2
        canvas = np.full((self.imgsz, self.imgsz, 3), 114, dtype=np.uint8)
        canvas[pad_y:pad_y + resized_h, pad_x:pad_x + resized_w] = resized
        return canvas, ratio, pad_x, pad_y

    @staticmethod
    def _as_predictions(output: np.ndarray) -> np.ndarray:
        array = np.asarray(output, dtype=np.float32).squeeze()
        if array.ndim == 1:
            if array.size % 84 != 0:
                raise RuntimeError(f"Unexpected YOLO output size: {array.size}")
            array = array.reshape(84, -1)
        elif array.ndim != 2:
            raise RuntimeError(f"Unexpected YOLO output shape: {array.shape}")
        if array.shape[0] == 84:
            return array
        if array.shape[1] == 84:
            return array.T
        raise RuntimeError(f"Expected one YOLO output dimension to be 84, got {array.shape}")

    def detect(self, frame: np.ndarray) -> List[Dict[str, object]]:
        if frame is None or frame.size == 0:
            return []
        image, ratio, pad_x, pad_y = self._letterbox(frame)
        mat = self.ncnn.Mat.from_pixels(
            image,
            self.ncnn.Mat.PixelType.PIXEL_BGR2RGB,
            self.imgsz,
            self.imgsz,
        )
        mat.substract_mean_normalize([0.0, 0.0, 0.0], [1.0 / 255.0] * 3)
        extractor = _make_extractor(self.net, self.num_threads)
        input_ret = extractor.input(self.input_blob, mat)
        if input_ret not in (None, 0):
            raise RuntimeError(f"NCNN input('{self.input_blob}') failed with code {input_ret}")
        predictions = self._as_predictions(_extract(extractor, self.output_blob))

        # Exported YOLO26 output is [cx, cy, w, h, 80 class probabilities].
        scores = predictions[4]
        selected = scores >= self.conf
        if not np.any(selected):
            return []
        xywh = predictions[:4, selected].T
        scores = scores[selected]
        boxes = np.empty_like(xywh)
        boxes[:, 0] = xywh[:, 0] - xywh[:, 2] * 0.5
        boxes[:, 1] = xywh[:, 1] - xywh[:, 3] * 0.5
        boxes[:, 2] = xywh[:, 0] + xywh[:, 2] * 0.5
        boxes[:, 3] = xywh[:, 1] + xywh[:, 3] * 0.5
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / ratio
        height, width = frame.shape[:2]
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, width - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, height - 1)
        valid = (boxes[:, 2] - boxes[:, 0] >= 2) & (boxes[:, 3] - boxes[:, 1] >= 2)
        boxes, scores = boxes[valid], scores[valid]
        keep = _nms_xyxy(boxes, scores, self.iou)
        return [
            {"bbox": boxes[index].round().astype(int).tolist(), "conf": float(scores[index])}
            for index in keep
        ]


class NcnnOSNetEncoder:
    """OSNet x0.25 NCNN encoder returning normalized 512-D embeddings."""

    input_width = 128
    input_height = 256
    mean_255 = [0.485 * 255.0, 0.456 * 255.0, 0.406 * 255.0]
    norm_255 = [1.0 / (0.229 * 255.0), 1.0 / (0.224 * 255.0), 1.0 / (0.225 * 255.0)]

    def __init__(self, param_path: str, bin_path: str, input_blob: str = "in0",
                 output_blob: str = "out0", num_threads: int = 4,
                 use_vulkan: bool = False, batch_size: int = 1):
        self.input_blob = input_blob
        self.output_blob = output_blob
        self.num_threads = max(1, int(num_threads))
        self.batch_size = 1  # The exported graph has a fixed batch of one.
        self.error: Optional[str] = None
        self.ncnn, self.net = _load_net(param_path, bin_path, self.num_threads, use_vulkan)

    @property
    def available(self) -> bool:
        return self.net is not None

    @classmethod
    def _crop(cls, frame: np.ndarray, bbox: Iterable[int]) -> Optional[np.ndarray]:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = [int(value) for value in bbox]
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        if x2 - x1 < 12 or y2 - y1 < 24:
            return None
        return cv2.resize(
            frame[y1:y2, x1:x2],
            (cls.input_width, cls.input_height),
            interpolation=cv2.INTER_LINEAR,
        )

    def extract(self, frame: np.ndarray, tracks: Iterable[dict]) -> Dict[int, np.ndarray]:
        output: Dict[int, np.ndarray] = {}
        for track in tracks:
            crop = self._crop(frame, track["bbox"])
            if crop is None:
                continue
            mat = self.ncnn.Mat.from_pixels(
                crop,
                self.ncnn.Mat.PixelType.PIXEL_BGR2RGB,
                self.input_width,
                self.input_height,
            )
            mat.substract_mean_normalize(self.mean_255, self.norm_255)
            extractor = _make_extractor(self.net, self.num_threads)
            input_ret = extractor.input(self.input_blob, mat)
            if input_ret not in (None, 0):
                raise RuntimeError(f"NCNN input('{self.input_blob}') failed with code {input_ret}")
            feature = _extract(extractor, self.output_blob).reshape(-1)
            if feature.size != 512:
                raise RuntimeError(f"Expected OSNet embedding size 512, got {feature.size}")
            norm = float(np.linalg.norm(feature))
            if norm > 1e-8:
                output[int(track["track_id"])] = (feature / norm).astype(np.float32, copy=False)
        return output


def _box_iou(a: np.ndarray, b: np.ndarray) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return float(intersection / max(1e-7, area_a + area_b - intersection))


@dataclass
class _MotionTrack:
    track_id: int
    bbox: np.ndarray
    confidence: float
    velocity: np.ndarray
    lost_frames: int = 0
    hits: int = 1

    def predict(self, frame_gap: int) -> None:
        self.bbox = self.bbox + self.velocity * max(1, int(frame_gap))
        self.lost_frames += max(1, int(frame_gap))

    def correct(self, bbox: Sequence[float], confidence: float, frame_gap: int) -> None:
        observed = np.asarray(bbox, dtype=np.float32)
        measured_velocity = (observed - self.bbox) / max(1, int(frame_gap))
        self.velocity = 0.65 * self.velocity + 0.35 * measured_velocity
        self.bbox = observed
        self.confidence = float(confidence)
        self.lost_frames = 0
        self.hits += 1


class LiteByteTracker:
    """Small dependency-free two-stage IoU tracker for the NCNN runtime.

    It follows ByteTrack's important behavior: high-confidence detections create
    tracks and low-confidence detections can keep an existing track alive.
    Long-term identity is still handled by OSNet/PersistentIdentityManager.
    """

    def __init__(self, high_threshold: float = 0.30, low_threshold: float = 0.08,
                 new_track_threshold: float = 0.38, track_buffer: int = 45,
                 match_threshold: float = 0.82):
        self.high_threshold = float(high_threshold)
        self.low_threshold = float(low_threshold)
        self.new_track_threshold = float(new_track_threshold)
        self.track_buffer = max(1, int(track_buffer))
        # FastTrack/ByteTrack configs express match_threshold as maximum cost.
        self.minimum_iou = max(0.08, 1.0 - float(match_threshold))
        self.tracks: List[_MotionTrack] = []
        self.next_id = 1

    @staticmethod
    def _match(tracks: List[_MotionTrack], detections: List[dict],
               track_indices: List[int], detection_indices: List[int],
               minimum_iou: float) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        candidates = []
        for track_index in track_indices:
            for detection_index in detection_indices:
                iou = _box_iou(
                    tracks[track_index].bbox,
                    np.asarray(detections[detection_index]["bbox"], dtype=np.float32),
                )
                if iou >= minimum_iou:
                    score = iou + 0.05 * float(detections[detection_index]["conf"])
                    candidates.append((score, track_index, detection_index))
        candidates.sort(reverse=True)
        used_tracks, used_detections, matches = set(), set(), []
        for _, track_index, detection_index in candidates:
            if track_index in used_tracks or detection_index in used_detections:
                continue
            used_tracks.add(track_index)
            used_detections.add(detection_index)
            matches.append((track_index, detection_index))
        return (
            matches,
            [index for index in track_indices if index not in used_tracks],
            [index for index in detection_indices if index not in used_detections],
        )

    def update(self, detections: List[dict], frame_gap: int = 1) -> List[Dict[str, object]]:
        gap = max(1, int(frame_gap))
        for track in self.tracks:
            track.predict(gap)

        high = [i for i, det in enumerate(detections) if float(det["conf"]) >= self.high_threshold]
        low = [
            i for i, det in enumerate(detections)
            if self.low_threshold <= float(det["conf"]) < self.high_threshold
        ]
        active = list(range(len(self.tracks)))
        matches, unmatched_tracks, unmatched_high = self._match(
            self.tracks, detections, active, high, self.minimum_iou
        )
        for track_index, detection_index in matches:
            det = detections[detection_index]
            self.tracks[track_index].correct(det["bbox"], det["conf"], gap)

        low_matches, unmatched_tracks, _ = self._match(
            self.tracks, detections, unmatched_tracks, low, max(0.12, self.minimum_iou * 0.8)
        )
        for track_index, detection_index in low_matches:
            det = detections[detection_index]
            self.tracks[track_index].correct(det["bbox"], det["conf"], gap)

        for detection_index in unmatched_high:
            det = detections[detection_index]
            if float(det["conf"]) < self.new_track_threshold:
                continue
            self.tracks.append(_MotionTrack(
                track_id=self.next_id,
                bbox=np.asarray(det["bbox"], dtype=np.float32),
                confidence=float(det["conf"]),
                velocity=np.zeros(4, dtype=np.float32),
            ))
            self.next_id += 1

        self.tracks = [track for track in self.tracks if track.lost_frames <= self.track_buffer]
        return [
            {
                "track_id": track.track_id,
                "bbox": track.bbox.round().astype(int).tolist(),
                "conf": round(track.confidence, 3),
            }
            for track in self.tracks
            if track.lost_frames == 0
        ]

    def reset(self) -> None:
        self.tracks.clear()
        self.next_id = 1
