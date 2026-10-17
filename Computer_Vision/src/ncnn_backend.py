"""NCNN inference and lightweight tracking for Raspberry Pi deployments.

This module deliberately depends only on numpy, OpenCV and the NCNN Python
binding.  PyTorch and Ultralytics are not imported on the NCNN path.
"""

from __future__ import annotations

import os
import time
from multiprocessing import shared_memory
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


YOLO_OUTPUT_CHANNELS = 84
PERSON_CLASS_SCORE_ROW = 4
OSNET_EMBEDDING_SIZE = 512
NUMERIC_EPSILON = 1e-7
_PROCESS_DETECTOR = None
_PROCESS_DETECTOR_SHM = None
_PROCESS_DETECTOR_INPUT = None

# original_height, original_width, resize_ratio, pad_x, pad_y
LetterboxTransform = Tuple[int, int, float, int, int]


def _read_model_metadata(param_path: str) -> dict:
    """Read optional export metadata stored beside an NCNN model."""
    metadata_path = os.path.join(os.path.dirname(os.path.abspath(param_path)), "metadata.yaml")
    if not os.path.isfile(metadata_path):
        return {}

    import yaml

    with open(metadata_path, "r", encoding="utf-8") as handle:
        metadata = yaml.safe_load(handle) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"NCNN metadata must be a mapping: {metadata_path}")
    return metadata


def _validate_detector_input_size(param_path: str, imgsz: int) -> int:
    """Fail early when runtime input differs from a fixed-shape NCNN export."""
    runtime_size = int(imgsz)
    if runtime_size <= 0:
        raise ValueError(f"Detector imgsz must be positive, got {imgsz!r}")

    exported_size = _read_model_metadata(param_path).get("imgsz")
    if exported_size is None:
        return runtime_size
    if isinstance(exported_size, (int, float)):
        exported_dimensions = [int(exported_size), int(exported_size)]
    elif isinstance(exported_size, (list, tuple)) and len(exported_size) == 2:
        exported_dimensions = [int(value) for value in exported_size]
    else:
        raise ValueError(
            f"Invalid imgsz in NCNN metadata beside {param_path}: {exported_size!r}"
        )

    if exported_dimensions != [runtime_size, runtime_size]:
        exported = "x".join(str(value) for value in exported_dimensions)
        raise ValueError(
            f"Configured detector imgsz={runtime_size} does not match the fixed NCNN "
            f"model input {exported}. Re-export/quantize the model for {runtime_size}x"
            f"{runtime_size}, or restore imgsz={exported_dimensions[0]}."
        )
    return runtime_size


def prepare_detector_input(
    frame: np.ndarray, imgsz: int
) -> Tuple[np.ndarray, LetterboxTransform]:
    """Create the fixed detector tensor before crossing the process boundary."""
    canvas = np.empty((int(imgsz), int(imgsz), 3), dtype=np.uint8)
    transform = prepare_detector_input_into(frame, imgsz, canvas)
    return canvas, transform


def prepare_detector_input_into(
    frame: np.ndarray,
    imgsz: int,
    output: np.ndarray,
) -> LetterboxTransform:
    """Letterbox directly into a reusable/shared buffer without an extra 300 KiB copy."""
    if frame is None or frame.size == 0:
        raise ValueError("Cannot preprocess an empty detector frame")
    expected_shape = (int(imgsz), int(imgsz), 3)
    if output.shape != expected_shape or output.dtype != np.uint8:
        raise ValueError(
            f"Expected uint8 detector output {expected_shape}, got "
            f"{output.dtype} {output.shape}"
        )
    height, width = frame.shape[:2]
    ratio = min(float(imgsz) / width, float(imgsz) / height)
    resized_w = max(1, int(round(width * ratio)))
    resized_h = max(1, int(round(height * ratio)))
    pad_x = (int(imgsz) - resized_w) // 2
    pad_y = (int(imgsz) - resized_h) // 2
    output.fill(114)
    destination = output[pad_y:pad_y + resized_h, pad_x:pad_x + resized_w]
    cv2.resize(
        frame,
        (resized_w, resized_h),
        dst=destination,
        interpolation=cv2.INTER_LINEAR,
    )
    return height, width, ratio, pad_x, pad_y


def initialize_detector_process(
    detector_config: dict,
    shared_memory_name: Optional[str] = None,
    shared_memory_shape: Optional[Tuple[int, int, int]] = None,
) -> None:
    """Load one NCNN detector inside a dedicated worker process."""
    global _PROCESS_DETECTOR, _PROCESS_DETECTOR_SHM, _PROCESS_DETECTOR_INPUT
    cv2.setNumThreads(1)
    _PROCESS_DETECTOR = NcnnYoloDetector(**detector_config)
    if shared_memory_name and shared_memory_shape:
        _PROCESS_DETECTOR_SHM = shared_memory.SharedMemory(
            name=shared_memory_name,
            create=False,
        )
        _PROCESS_DETECTOR_INPUT = np.ndarray(
            tuple(shared_memory_shape),
            dtype=np.uint8,
            buffer=_PROCESS_DETECTOR_SHM.buf,
        )


def detector_process_ready() -> bool:
    """Confirm that the worker initializer loaded the detector successfully."""
    return _PROCESS_DETECTOR is not None


def detect_in_process(frame: np.ndarray) -> Tuple[List[Dict[str, object]], float]:
    """Run detection in the process-local model and return its pure inference time."""
    if _PROCESS_DETECTOR is None:
        raise RuntimeError("NCNN detector process was not initialized")
    started_at = time.perf_counter()
    detections = _PROCESS_DETECTOR.detect(frame)
    return detections, (time.perf_counter() - started_at) * 1000.0


def detect_shared_in_process(
    transform: LetterboxTransform,
    preprocess_ms: float = 0.0,
) -> Tuple[List[Dict[str, object]], float]:
    """Run NCNN directly on the process-shared 320x320 detector input."""
    if _PROCESS_DETECTOR is None or _PROCESS_DETECTOR_INPUT is None:
        raise RuntimeError("Shared-memory NCNN detector was not initialized")
    started_at = time.perf_counter()
    detections = _PROCESS_DETECTOR.detect_preprocessed(
        _PROCESS_DETECTOR_INPUT,
        transform,
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    return detections, max(0.0, float(preprocess_ms)) + elapsed_ms


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
        iou = intersection / np.maximum(union, NUMERIC_EPSILON)
        order = rest[iou <= float(iou_threshold)]
    return keep


class NcnnYoloDetector:
    """YOLO26n NCNN detector producing person boxes in original-image pixels."""

    def __init__(self, param_path: str, bin_path: str, imgsz: int = 640,
                 confidence_threshold: float = 0.25, iou_threshold: float = 0.60,
                 input_blob: str = "in0", output_blob: str = "out0",
                 num_threads: int = 4, use_vulkan: bool = False):
        self.imgsz = _validate_detector_input_size(param_path, imgsz)
        self.conf = float(confidence_threshold)
        self.iou = float(iou_threshold)
        self.input_blob = input_blob
        self.output_blob = output_blob
        self.num_threads = max(1, int(num_threads))
        self.ncnn, self.net = _load_net(param_path, bin_path, self.num_threads, use_vulkan)

    def _letterbox(self, frame: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        image, (_, _, ratio, pad_x, pad_y) = prepare_detector_input(frame, self.imgsz)
        return image, ratio, pad_x, pad_y

    @staticmethod
    def _as_predictions(output: np.ndarray) -> np.ndarray:
        array = np.asarray(output, dtype=np.float32).squeeze()
        if array.ndim == 1:
            if array.size % YOLO_OUTPUT_CHANNELS != 0:
                raise RuntimeError(f"Unexpected YOLO output size: {array.size}")
            array = array.reshape(YOLO_OUTPUT_CHANNELS, -1)
        elif array.ndim != 2:
            raise RuntimeError(f"Unexpected YOLO output shape: {array.shape}")
        if array.shape[0] == YOLO_OUTPUT_CHANNELS:
            return array
        if array.shape[1] == YOLO_OUTPUT_CHANNELS:
            return array.T
        raise RuntimeError(
            f"Expected one YOLO output dimension to be {YOLO_OUTPUT_CHANNELS}, "
            f"got {array.shape}"
        )

    def detect(self, frame: np.ndarray) -> List[Dict[str, object]]:
        if frame is None or frame.size == 0:
            return []
        image, transform = prepare_detector_input(frame, self.imgsz)
        return self.detect_preprocessed(image, transform)

    def detect_preprocessed(
        self,
        image: np.ndarray,
        transform: LetterboxTransform,
    ) -> List[Dict[str, object]]:
        """Infer an already-letterboxed image and restore original coordinates."""
        if image.shape != (self.imgsz, self.imgsz, 3):
            raise ValueError(
                f"Expected detector input {(self.imgsz, self.imgsz, 3)}, got {image.shape}"
            )
        original_height, original_width, ratio, pad_x, pad_y = transform
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
        scores = predictions[PERSON_CLASS_SCORE_ROW]
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
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, original_width - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, original_height - 1)
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
            if feature.size != OSNET_EMBEDDING_SIZE:
                raise RuntimeError(
                    f"Expected OSNet embedding size {OSNET_EMBEDDING_SIZE}, got {feature.size}"
                )
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
    return float(intersection / max(NUMERIC_EPSILON, area_a + area_b - intersection))


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

    def predicted_tracks(self, frame_gap: int = 0) -> List[Dict[str, object]]:
        """Return a non-mutating motion prediction for frames between detections."""
        gap = max(0, int(frame_gap))
        output: List[Dict[str, object]] = []
        for track in self.tracks:
            if track.lost_frames != 0:
                continue
            predicted_bbox = track.bbox + track.velocity * gap
            output.append({
                "track_id": track.track_id,
                "bbox": predicted_bbox.round().astype(int).tolist(),
                "conf": round(track.confidence, 3),
            })
        return output

    def reset(self) -> None:
        self.tracks.clear()
        self.next_id = 1
