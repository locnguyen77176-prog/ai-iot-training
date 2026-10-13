import os
import sys
import time
from collections import deque
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TRACKER_PATH = os.path.join(BASE_DIR, "custom_fasttrack.yaml")
if not os.path.exists(DEFAULT_TRACKER_PATH):
    DEFAULT_TRACKER_PATH = "fasttrack.yaml"


def _resolve_project_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _load_yaml_mapping(path: str) -> Dict[str, Any]:
    """Load optional tracker settings without making startup depend on the file."""
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


@dataclass
class _IdentityProfile:
    stable_id: int
    descriptor: np.ndarray
    bbox: List[int]
    center: Tuple[float, float]
    last_seen: float
    reid_descriptor: Optional[np.ndarray] = None
    reid_gallery: List[np.ndarray] = field(default_factory=list)
    local_ids: set = field(default_factory=set)
    observations: int = 1
    created_at: float = 0.0
    recheck_until: float = 0.0
    recheck_candidate_id: Optional[int] = None
    recheck_candidate_hits: int = 0


class PersistentIdentityManager:
    """Ánh xạ ID ngắn hạn của MOT sang ID ổn định bằng dấu hiệu ngoại hình."""

    def __init__(self, memory_seconds: float = 120.0,
                 appearance_threshold: float = 0.82,
                 spatial_threshold: float = 0.30,
                 reid_threshold: float = 0.78,
                 reid_ambiguity_margin: float = 0.06,
                 reid_gallery_size: int = 5,
                 reid_recheck_seconds: float = 10.0,
                 require_reid_for_match: bool = False):
        # 0 = giữ hồ sơ đến khi reset/đổi nguồn; số dương = TTL tính bằng giây.
        requested_memory = float(memory_seconds)
        self.memory_seconds: Optional[float] = None if requested_memory <= 0 else max(1.0, requested_memory)
        self.appearance_threshold = float(np.clip(appearance_threshold, 0.0, 1.0))
        self.spatial_threshold = float(np.clip(spatial_threshold, 0.0, 1.0))
        self.reid_threshold = float(np.clip(reid_threshold, 0.0, 1.0))
        self.reid_ambiguity_margin = max(0.0, float(reid_ambiguity_margin))
        self.reid_gallery_size = max(1, int(reid_gallery_size))
        self.reid_recheck_seconds = max(0.0, float(reid_recheck_seconds))
        self.require_reid_for_match = bool(require_reid_for_match)
        self.local_to_stable: Dict[int, int] = {}
        self.profiles: Dict[int, _IdentityProfile] = {}
        self.active_local_ids: set = set()
        self.next_stable_id = 1
        self.reidentified_total = 0
        self.duplicates_suppressed_total = 0

    @staticmethod
    def _box_metrics(a: List[int], b: List[int]) -> Tuple[float, float, float]:
        ax1, ay1, ax2, ay2 = [float(v) for v in a]
        bx1, by1, bx2, by2 = [float(v) for v in b]
        iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
        intersection = iw * ih
        area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
        area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
        iou = intersection / max(1.0, area_a + area_b - intersection)
        containment = intersection / min(area_a, area_b)
        ac, bc = ((ax1 + ax2) / 2, (ay1 + ay2) / 2), ((bx1 + bx2) / 2, (by1 + by2) / 2)
        center_distance = float(np.hypot(ac[0] - bc[0], ac[1] - bc[1]))
        normalized_distance = center_distance / max(1.0, np.sqrt(max(area_a, area_b)))
        return iou, containment, normalized_distance

    def _suppress_duplicate_tracks(self, tracks: List[Dict[str, Any]],
                                   reid_features: Dict[int, np.ndarray]) -> List[Dict[str, Any]]:
        """Giữ một bbox cho mỗi người và ưu tiên ID đã được ánh xạ từ trước."""
        ordered = sorted(
            tracks,
            key=lambda t: (int(t["track_id"]) in self.local_to_stable, float(t.get("conf", 0.0))),
            reverse=True,
        )
        kept: List[Dict[str, Any]] = []
        for candidate in ordered:
            candidate_id = int(candidate["track_id"])
            candidate_feat = reid_features.get(candidate_id)
            is_duplicate = False
            for accepted in kept:
                accepted_id = int(accepted["track_id"])
                iou, containment, center_distance = self._box_metrics(candidate["bbox"], accepted["bbox"])
                accepted_feat = reid_features.get(accepted_id)
                deep_similarity = None
                if candidate_feat is not None and accepted_feat is not None:
                    ca = np.asarray(candidate_feat, dtype=np.float32).reshape(-1)
                    aa = np.asarray(accepted_feat, dtype=np.float32).reshape(-1)
                    denom = float(np.linalg.norm(ca) * np.linalg.norm(aa))
                    if denom > 1e-8:
                        deep_similarity = float(np.dot(ca, aa) / denom)

                # Hình học gần như trùng tuyệt đối, hoặc hình học + ReID cùng xác nhận.
                if iou >= 0.86 or containment >= 0.96:
                    is_duplicate = True
                elif deep_similarity is not None:
                    is_duplicate = (
                        (iou >= 0.70 and deep_similarity >= 0.78)
                        or (deep_similarity >= 0.92 and (iou >= 0.35 or center_distance <= 0.20))
                    )
                else:
                    is_duplicate = iou >= 0.80 or containment >= 0.92
                if is_duplicate:
                    break
            if not is_duplicate:
                kept.append(candidate)
        self.duplicates_suppressed_total += len(tracks) - len(kept)
        return kept

    @staticmethod
    def _histogram(crop: np.ndarray) -> np.ndarray:
        if crop.size == 0:
            return np.zeros(384, dtype=np.float32)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hs = cv2.calcHist([hsv], [0, 1], None, [16, 12], [0, 180, 0, 256]).ravel()
        hv = cv2.calcHist([hsv], [0, 2], None, [16, 12], [0, 180, 0, 256]).ravel()
        feat = np.concatenate((hs, hv)).astype(np.float32)
        norm = float(np.linalg.norm(feat))
        return feat / norm if norm > 1e-8 else feat

    @classmethod
    def extract_descriptor(cls, frame: np.ndarray, bbox: List[int]) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x2 - x1 < 12 or y2 - y1 < 24:
            return None

        person = frame[y1:y2, x1:x2]
        ph = person.shape[0]
        pad = max(1, int(person.shape[1] * 0.12))
        upper = person[int(ph * 0.18):int(ph * 0.58), pad:-pad]
        lower = person[int(ph * 0.55):int(ph * 0.95), pad:-pad]
        if upper.size == 0 or lower.size == 0:
            return None
        descriptor = np.concatenate((cls._histogram(upper), cls._histogram(lower)))
        norm = float(np.linalg.norm(descriptor))
        return descriptor / norm if norm > 1e-8 else None

    @staticmethod
    def _similarity(a: np.ndarray, b: np.ndarray) -> float:
        a, b = np.asarray(a).reshape(-1), np.asarray(b).reshape(-1)
        if a.shape != b.shape:
            return 0.0
        return float(np.clip(np.dot(a, b), 0.0, 1.0))

    def _gallery_similarity(self, descriptor: np.ndarray, profile: _IdentityProfile) -> float:
        gallery = profile.reid_gallery
        if not gallery and profile.reid_descriptor is not None:
            gallery = [profile.reid_descriptor]
        similarities = sorted(
            (self._similarity(descriptor, sample) for sample in gallery), reverse=True
        )
        if not similarities:
            return 0.0
        # Best view dominates, while a second good view makes the match less brittle.
        return similarities[0] if len(similarities) == 1 else 0.8 * similarities[0] + 0.2 * similarities[1]

    def _append_reid_sample(self, profile: _IdentityProfile, descriptor: np.ndarray) -> None:
        descriptor = np.asarray(descriptor, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(descriptor))
        if norm <= 1e-8:
            return
        descriptor = descriptor / norm
        if profile.reid_gallery:
            novelty = 1.0 - max(self._similarity(descriptor, old) for old in profile.reid_gallery)
            if novelty < 0.01:
                return
        profile.reid_gallery.append(descriptor.copy())
        if len(profile.reid_gallery) > self.reid_gallery_size:
            profile.reid_gallery.pop(0)
        profile.reid_descriptor = np.mean(profile.reid_gallery, axis=0)
        mean_norm = float(np.linalg.norm(profile.reid_descriptor))
        if mean_norm > 1e-8:
            profile.reid_descriptor /= mean_norm

    def _new_profile(self, local_id: int, descriptor: np.ndarray,
                     reid_descriptor: Optional[np.ndarray],
                     bbox: List[int], center: Tuple[float, float], now: float) -> int:
        stable_id = self.next_stable_id
        self.next_stable_id += 1
        self.profiles[stable_id] = _IdentityProfile(
            stable_id=stable_id, descriptor=descriptor.copy(), bbox=list(bbox),
            center=center, last_seen=now,
            reid_descriptor=None if reid_descriptor is None else reid_descriptor.copy(),
            reid_gallery=[] if reid_descriptor is None else [reid_descriptor.copy()],
            local_ids={local_id},
            created_at=now,
            recheck_until=now + self.reid_recheck_seconds,
        )
        return stable_id

    def should_recheck(self, stable_id: Optional[int], now: Optional[float] = None) -> bool:
        """Whether a recently-created identity may still be corrected by later OSNet crops."""
        if stable_id is None or self.reid_recheck_seconds <= 0:
            return False
        profile = self.profiles.get(stable_id)
        if profile is None:
            return False
        current = time.monotonic() if now is None else float(now)
        return current <= profile.recheck_until

    def _match_inactive(self, descriptor: Optional[np.ndarray],
                        reid_descriptor: Optional[np.ndarray],
                        center: Tuple[float, float],
                        frame_shape: Tuple[int, ...], now: float,
                        reserved: set,
                        created_before: Optional[float] = None) -> Optional[int]:
        diagonal = max(1.0, float(np.hypot(frame_shape[1], frame_shape[0])))
        candidates = []
        for stable_id, profile in self.profiles.items():
            if (stable_id in reserved
                    or (self.memory_seconds is not None and now - profile.last_seen > self.memory_seconds)):
                continue
            if created_before is not None and profile.created_at >= created_before:
                continue
            has_color = (descriptor is not None and np.linalg.norm(descriptor) > 1e-8
                         and np.linalg.norm(profile.descriptor) > 1e-8)
            color_similarity = self._similarity(descriptor, profile.descriptor) if has_color else 0.0
            has_deep_reid = reid_descriptor is not None and profile.reid_descriptor is not None
            if has_deep_reid:
                reid_similarity = self._gallery_similarity(reid_descriptor, profile)
                similarity = (0.88 * reid_similarity + 0.12 * color_similarity
                              if has_color else reid_similarity)
                if reid_similarity < self.reid_threshold or similarity < 0.72:
                    continue
            else:
                if self.require_reid_for_match:
                    continue
                reid_similarity = 0.0
                similarity = color_similarity
                if similarity < self.appearance_threshold:
                    continue
            distance = float(np.hypot(center[0] - profile.center[0], center[1] - profile.center[1])) / diagonal
            elapsed = max(0.0, now - profile.last_seen)
            # Cho phép đi từ A sang B khi khuất vài giây; deep ReID mạnh được nới thêm.
            allowed_distance = min(0.85, self.spatial_threshold + 0.05 * elapsed)
            if reid_similarity >= 0.84:
                allowed_distance = max(allowed_distance, 0.65)
            if distance > allowed_distance:
                continue
            candidates.append((similarity - 0.10 * distance, stable_id))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        # Nếu hai người quá giống nhau, ưu tiên ID mới thay vì gán nhầm ID cũ.
        if (len(candidates) > 1
                and candidates[0][0] - candidates[1][0] < self.reid_ambiguity_margin):
            return None
        return candidates[0][1]

    def update(self, frame: np.ndarray, tracks: List[Dict[str, Any]],
               now: Optional[float] = None,
               reid_features: Optional[Dict[int, np.ndarray]] = None,
               update_appearance: bool = True) -> List[Dict[str, Any]]:
        now = time.monotonic() if now is None else float(now)
        reid_features = reid_features or {}
        tracks = self._suppress_duplicate_tracks(tracks, reid_features)
        current_local_ids = {int(t["track_id"]) for t in tracks}
        reserved = {self.local_to_stable[lid] for lid in current_local_ids if lid in self.local_to_stable}

        output = []
        for track in tracks:
            item = dict(track)
            local_id = int(item["track_id"])
            bbox = item["bbox"]
            center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
            needs_initial_descriptor = local_id not in self.local_to_stable
            descriptor = (
                self.extract_descriptor(frame, bbox)
                if update_appearance or needs_initial_descriptor else None
            )
            deep_descriptor = reid_features.get(local_id)
            if deep_descriptor is not None:
                deep_descriptor = np.asarray(deep_descriptor, dtype=np.float32).reshape(-1)
                deep_norm = float(np.linalg.norm(deep_descriptor))
                deep_descriptor = deep_descriptor / deep_norm if deep_norm > 1e-8 else None

            stable_id = self.local_to_stable.get(local_id)
            is_new_mapping = stable_id is None
            was_reidentified = False
            if stable_id is None:
                stable_id = None if descriptor is None and deep_descriptor is None else self._match_inactive(
                    descriptor, deep_descriptor, center, frame.shape, now, reserved
                )
                was_reidentified = stable_id is not None
                if was_reidentified:
                    self.reidentified_total += 1
                if stable_id is None:
                    fallback = descriptor if descriptor is not None else np.zeros(768, dtype=np.float32)
                    stable_id = self._new_profile(
                        local_id, fallback, deep_descriptor, bbox, center, now
                    )
                self.local_to_stable[local_id] = stable_id
                self.profiles[stable_id].local_ids.add(local_id)
                reserved.add(stable_id)

            profile = self.profiles[stable_id]
            remapped_from = None
            # Reconsider a recent provisional identity with later, clearer OSNet
            # crops. Profiles that already had an embedding need two consecutive
            # agreements before remapping, which prevents one blurred crop from
            # rewriting a journey permanently.
            if (not is_new_mapping and deep_descriptor is not None
                    and self.should_recheck(stable_id, now)):
                matched_id = self._match_inactive(
                    descriptor, deep_descriptor, center, frame.shape, now, reserved,
                    created_before=profile.created_at,
                )
                if matched_id is None or matched_id == stable_id:
                    profile.recheck_candidate_id = None
                    profile.recheck_candidate_hits = 0
                else:
                    if profile.recheck_candidate_id == matched_id:
                        profile.recheck_candidate_hits += 1
                    else:
                        profile.recheck_candidate_id = matched_id
                        profile.recheck_candidate_hits = 1

                required_hits = 1 if profile.reid_descriptor is None else 2
                if (matched_id is not None and matched_id != stable_id
                        and profile.recheck_candidate_hits >= required_hits):
                    provisional_id = stable_id
                    profile.local_ids.discard(local_id)
                    self.local_to_stable[local_id] = matched_id
                    self.profiles[matched_id].local_ids.add(local_id)
                    reserved.discard(provisional_id)
                    reserved.add(matched_id)
                    if not profile.local_ids:
                        self.profiles.pop(provisional_id, None)

                    stable_id = matched_id
                    profile = self.profiles[stable_id]
                    profile.recheck_until = 0.0
                    profile.recheck_candidate_id = None
                    profile.recheck_candidate_hits = 0
                    remapped_from = provisional_id
                    was_reidentified = True
                    self.reidentified_total += 1
                    print(
                        f"[ReID] Local #{local_id}: Stable #{provisional_id} -> "
                        f"Stable #{stable_id} (delayed correction)"
                    )
            # Không làm bẩn hồ sơ bằng crop mờ/che khuất có confidence thấp.
            if descriptor is not None and (is_new_mapping or float(item.get("conf", 1.0)) >= 0.45):
                alpha = 0.88 if profile.observations > 4 else 0.65
                blended = alpha * profile.descriptor + (1.0 - alpha) * descriptor
                norm = float(np.linalg.norm(blended))
                if norm > 1e-8:
                    profile.descriptor = blended / norm
                profile.observations += 1
            if (deep_descriptor is not None and not was_reidentified
                    and (is_new_mapping or float(item.get("conf", 1.0)) >= 0.45)):
                self._append_reid_sample(profile, deep_descriptor)
            profile.bbox, profile.center, profile.last_seen = list(bbox), center, now

            item["local_track_id"] = local_id
            item["track_id"] = stable_id
            item["reidentified"] = was_reidentified
            if remapped_from is not None:
                item["identity_remapped_from"] = remapped_from
            output.append(item)

        self.active_local_ids = current_local_ids
        expired = [] if self.memory_seconds is None else [
            sid for sid, p in self.profiles.items() if now - p.last_seen > self.memory_seconds
        ]
        for sid in expired:
            del self.profiles[sid]
            for lid, mapped_sid in list(self.local_to_stable.items()):
                if mapped_sid == sid:
                    del self.local_to_stable[lid]
        return output

    def reset(self) -> None:
        self.local_to_stable.clear()
        self.profiles.clear()
        self.active_local_ids.clear()
        self.next_stable_id = 1
        self.reidentified_total = 0
        self.duplicates_suppressed_total = 0


class YOLOTracker:
    """Phát hiện người, FastTrack ngắn hạn và OSNet bên ngoài cho ID dài hạn."""

    def __init__(self, model_path: str = "models/yolo26n.pt", device: str = "cuda:0",
                 confidence_threshold: float = 0.25, iou_threshold: float = 0.60,
                 tracker: str = DEFAULT_TRACKER_PATH, imgsz: int = 640,
                 identity_memory_seconds: float = 120.0,
                 identity_similarity_threshold: float = 0.82,
                 reid_model_path: Optional[str] = None,
                 reid_similarity_threshold: float = 0.78,
                 reid_ambiguity_margin: float = 0.06,
                 reid_sample_interval_frames: int = 15,
                 reid_min_confidence: float = 0.55,
                 reid_min_bbox_height: int = 100,
                 reid_gallery_size: int = 5,
                 reid_batch_size: int = 16,
                 reid_max_per_frame: int = 4,
                 reid_max_periodic_per_frame: int = 4,
                 reid_periodic_schedule_frames: int = 3,
                 reid_recheck_seconds: float = 10.0,
                 backend: str = "pytorch",
                 ncnn_detector_param: Optional[str] = None,
                 ncnn_detector_bin: Optional[str] = None,
                 ncnn_reid_param: Optional[str] = None,
                 ncnn_reid_bin: Optional[str] = None,
                 ncnn_num_threads: int = 4,
                 ncnn_reid_num_threads: Optional[int] = None,
                 ncnn_use_vulkan: bool = False,
                 ncnn_async_detection: bool = False,
                 ncnn_detection_interval_frames: int = 1):
        self.backend = str(backend).strip().lower()
        if self.backend not in {"pytorch", "ncnn"}:
            raise ValueError(f"Unsupported detector backend: {backend!r}")
        self.model_path = model_path
        self.conf = confidence_threshold
        self.iou = iou_threshold
        self.imgsz = int(imgsz)
        self.tracker = tracker if os.path.isabs(tracker) else os.path.join(BASE_DIR, tracker)
        if not os.path.exists(self.tracker):
            self.tracker = tracker
        self.identity = PersistentIdentityManager(
            identity_memory_seconds,
            identity_similarity_threshold,
            reid_threshold=reid_similarity_threshold,
            reid_ambiguity_margin=reid_ambiguity_margin,
            reid_gallery_size=reid_gallery_size,
            reid_recheck_seconds=reid_recheck_seconds,
        )
        self.reid_sample_interval = max(1, int(reid_sample_interval_frames))
        self.reid_min_confidence = float(reid_min_confidence)
        self.reid_min_bbox_height = max(24, int(reid_min_bbox_height))
        self.reid_max_per_frame = max(1, int(reid_max_per_frame))
        self.reid_max_periodic_per_frame = max(0, min(
            self.reid_max_per_frame, int(reid_max_periodic_per_frame)
        ))
        self.reid_periodic_schedule_frames = max(1, int(reid_periodic_schedule_frames))
        self._frame_index = 0
        self._reid_last_sample: Dict[int, int] = {}

        self.ncnn_async_detection = self.backend == "ncnn" and bool(ncnn_async_detection)
        self.ncnn_detection_interval_frames = max(1, int(ncnn_detection_interval_frames))
        self._detector_executor: Optional[ProcessPoolExecutor] = None
        self._detector_callable = None
        self._detector_future: Optional[Future] = None
        self._detector_future_frame: Optional[np.ndarray] = None
        self._detector_future_sequence = 0
        self._detector_future_generation = 0
        self._detector_last_submit_sequence: Optional[int] = None
        self._detector_last_applied_sequence: Optional[int] = None
        self._detector_generation = 0
        self._ncnn_sequence = 0
        self._detector_timestamps = deque(maxlen=30)
        self._detector_fps = 0.0
        self._detector_latency_ms = 0.0
        self._detector_result_applied = False
        self._detector_reid_frame: Optional[np.ndarray] = None
        self._detector_reid_tracks: List[Dict[str, object]] = []

        self.reid_encoder = None
        self.local_tracker = None
        if self.backend == "ncnn":
            # NCNN already parallelizes inference. Avoid nested OpenCV worker pools
            # competing with the web/render process for the same Pi CPU cores.
            cv2.setNumThreads(1)
            from src.ncnn_backend import (
                LiteByteTracker,
                NcnnOSNetEncoder,
                NcnnYoloDetector,
                detect_in_process,
                detector_process_ready,
                initialize_detector_process,
            )

            detector_param = _resolve_project_path(ncnn_detector_param)
            detector_bin = _resolve_project_path(ncnn_detector_bin)
            reid_num_threads = (
                max(1, int(ncnn_reid_num_threads))
                if ncnn_reid_num_threads is not None else max(1, int(ncnn_num_threads))
            )
            if not detector_param or not detector_bin:
                raise ValueError("NCNN backend requires ncnn_detector_param and ncnn_detector_bin")
            self.device = "cpu"
            if self.ncnn_async_detection:
                detector_config = {
                    "param_path": detector_param,
                    "bin_path": detector_bin,
                    "imgsz": self.imgsz,
                    "confidence_threshold": self.conf,
                    "iou_threshold": self.iou,
                    "num_threads": ncnn_num_threads,
                    "use_vulkan": ncnn_use_vulkan,
                }
                self.model = None
                self._detector_callable = detect_in_process
                self._detector_executor = ProcessPoolExecutor(
                    max_workers=1,
                    mp_context=get_context("spawn"),
                    initializer=initialize_detector_process,
                    initargs=(detector_config,),
                )
                detector_ready = self._detector_executor.submit(
                    detector_process_ready
                ).result(timeout=60)
                if not detector_ready:
                    raise RuntimeError("NCNN detector process failed to initialize")
                print(
                    f"[Tracker] YOLO26n NCNN runs in a dedicated process "
                    f"({ncnn_num_threads} threads, imgsz: {self.imgsz})"
                )
            else:
                print(
                    f"[Tracker] Loading YOLO26n NCNN on CPU "
                    f"({ncnn_num_threads} threads, imgsz: {self.imgsz})..."
                )
                self.model = NcnnYoloDetector(
                    detector_param, detector_bin, imgsz=self.imgsz,
                    confidence_threshold=self.conf, iou_threshold=self.iou,
                    num_threads=ncnn_num_threads, use_vulkan=ncnn_use_vulkan,
                )
            tracker_config = _load_yaml_mapping(self.tracker)
            self.local_tracker = LiteByteTracker(
                high_threshold=tracker_config.get("track_high_thresh", 0.30),
                low_threshold=tracker_config.get("track_low_thresh", 0.08),
                new_track_threshold=tracker_config.get("new_track_thresh", 0.38),
                track_buffer=tracker_config.get("track_buffer", 45),
                match_threshold=tracker_config.get("match_thresh", 0.82),
            )
            if ncnn_reid_param and ncnn_reid_bin:
                self.identity.require_reid_for_match = True
                self.reid_encoder = NcnnOSNetEncoder(
                    _resolve_project_path(ncnn_reid_param),
                    _resolve_project_path(ncnn_reid_bin),
                    num_threads=reid_num_threads, use_vulkan=ncnn_use_vulkan,
                    batch_size=reid_batch_size,
                )
                print(
                    f"[ReID] OSNet x0.25 NCNN FP32 enabled "
                    f"({reid_num_threads} thread(s))"
                )
            return

        import torch
        from ultralytics import YOLO
        from src.osnet_reid import OSNetReIDEncoder

        if "cuda" in device and not torch.cuda.is_available():
            print("[Tracker] CUDA không khả dụng, tự động chuyển về CPU.")
            self.device = "cpu"
        else:
            self.device = device
            if "cuda" in self.device:
                torch.backends.cudnn.benchmark = True

        print(f"[Tracker] Tải {self.model_path} trên {self.device} "
              f"(tracker: {os.path.basename(self.tracker)}, imgsz: {self.imgsz})...")
        self.model = YOLO(self.model_path)

        self.reid_encoder: Optional[OSNetReIDEncoder] = None
        if reid_model_path:
            # If OSNet was explicitly requested, never silently reconnect IDs by color alone.
            self.identity.require_reid_for_match = True
            resolved_reid_path = (
                reid_model_path if os.path.isabs(reid_model_path)
                else os.path.join(BASE_DIR, reid_model_path)
            )
            encoder = OSNetReIDEncoder(resolved_reid_path, device=self.device, batch_size=reid_batch_size)
            if encoder.available:
                self.reid_encoder = encoder
                print(f"[ReID] OSNet x0.25 enabled: {resolved_reid_path}")
            else:
                print(f"[ReID] OSNet disabled ({encoder.error}); long-term ID recovery is disabled.")

    def _advance_kalman_for_gap(self, frame_gap: int) -> None:
        """Advance existing FastTrack states for live frames skipped by the AI worker."""
        extra_steps = min(8, max(0, int(frame_gap) - 1))
        if extra_steps <= 0:
            return
        predictor = getattr(self.model, "predictor", None)
        backends = getattr(predictor, "trackers", []) or []
        for backend in backends:
            pool = []
            seen = set()
            for attr in ("tracked_stracks", "lost_stracks"):
                for track in getattr(backend, attr, []) or []:
                    marker = id(track)
                    if marker not in seen and getattr(track, "mean", None) is not None:
                        seen.add(marker)
                        pool.append(track)
            for _ in range(extra_steps):
                if pool and hasattr(backend, "multi_predict"):
                    backend.multi_predict(pool)

    @staticmethod
    def _build_tracked_objects(
        ids: List[int],
        boxes: List[List[int]],
        confidences: List[float],
        frame_shape: Tuple[int, ...],
    ) -> List[Dict[str, Any]]:
        """Normalize backend output and derive the head region used by identity matching."""
        frame_height, frame_width = frame_shape[:2]
        tracked_objects: List[Dict[str, Any]] = []
        for local_id, bbox, confidence in zip(ids, boxes, confidences):
            x1, y1, x2, y2 = [int(value) for value in bbox]
            x1 = min(frame_width - 1, max(0, x1))
            x2 = min(frame_width - 1, max(0, x2))
            y1 = min(frame_height - 1, max(0, y1))
            y2 = min(frame_height - 1, max(0, y2))
            clipped_bbox = [x1, y1, x2, y2]
            width = max(1, x2 - x1)
            height = max(1, y2 - y1)
            head_height = max(18, int(height * 0.25))
            head_width = max(18, int(width * 0.60))
            head_center_x = int((x1 + x2) / 2)
            head_bbox = [
                max(0, int(head_center_x - head_width / 2)),
                max(0, y1),
                min(frame_width - 1, int(head_center_x + head_width / 2)),
                min(frame_height - 1, y1 + head_height),
            ]
            tracked_objects.append({
                "track_id": local_id,
                "bbox": clipped_bbox,
                "head_bbox": head_bbox,
                "head_point": (head_center_x, int(head_bbox[1] + head_height * 0.5)),
                "conf": round(float(confidence), 3),
            })
        return tracked_objects

    def _select_reid_requests(
        self, tracked_objects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Select a bounded, quality-filtered set of tracks for OSNet inference."""
        urgent_requests = []
        periodic_requests = []
        for item in tracked_objects:
            local_id = int(item["track_id"])
            bbox_height = int(item["bbox"][3]) - int(item["bbox"][1])
            last_sample = self._reid_last_sample.get(local_id, -self.reid_sample_interval)
            is_new_local_id = local_id not in self.identity.local_to_stable
            stable_id = self.identity.local_to_stable.get(local_id)
            profile = self.identity.profiles.get(stable_id) if stable_id is not None else None
            needs_initial_reid = is_new_local_id or (
                profile is not None and profile.reid_descriptor is None
            )
            is_due = self._frame_index - last_sample >= self.reid_sample_interval
            needs_identity_recheck = (
                profile is not None
                and self.identity.should_recheck(stable_id)
                and is_due
            )
            has_quality = (
                float(item.get("conf", 0.0)) >= self.reid_min_confidence
                and bbox_height >= self.reid_min_bbox_height
            )
            if not has_quality:
                continue

            priority = (float(item.get("conf", 0.0)), bbox_height)
            if needs_initial_reid or needs_identity_recheck:
                urgent_requests.append((priority, item))
            elif is_due and self._frame_index % self.reid_periodic_schedule_frames == 0:
                periodic_requests.append((priority, item))

        urgent_requests.sort(key=lambda pair: pair[0], reverse=True)
        periodic_requests.sort(key=lambda pair: pair[0], reverse=True)
        requests = [item for _, item in urgent_requests[:self.reid_max_per_frame]]
        periodic_budget = min(
            self.reid_max_per_frame - len(requests),
            self.reid_max_periodic_per_frame,
        )
        requests.extend(item for _, item in periodic_requests[:periodic_budget])
        return requests

    def _submit_ncnn_detection(self, frame: np.ndarray) -> None:
        if self._detector_executor is None:
            return
        self._detector_future_sequence = self._ncnn_sequence
        self._detector_future_generation = self._detector_generation
        self._detector_last_submit_sequence = self._ncnn_sequence
        detector_frame = np.ascontiguousarray(frame.copy())
        self._detector_future_frame = detector_frame
        self._detector_future = self._detector_executor.submit(
            self._detector_callable,
            detector_frame,
        )

    def _record_detector_completion(self, inference_ms: float) -> None:
        completed_at = time.perf_counter()
        latency_ms = max(0.0, float(inference_ms))
        if self._detector_latency_ms <= 0:
            self._detector_latency_ms = latency_ms
        else:
            self._detector_latency_ms = 0.8 * self._detector_latency_ms + 0.2 * latency_ms
        self._detector_timestamps.append(completed_at)
        if len(self._detector_timestamps) >= 2:
            elapsed = self._detector_timestamps[-1] - self._detector_timestamps[0]
            if elapsed > 0:
                self._detector_fps = (
                    (len(self._detector_timestamps) - 1) / elapsed
                )

    def _track_ncnn_async(
        self, frame: np.ndarray, effective_gap: int
    ) -> List[Dict[str, object]]:
        """Keep the realtime pipeline moving while NCNN detects in another process."""
        self._ncnn_sequence += max(1, int(effective_gap))
        self._detector_result_applied = False

        if self._detector_future is not None and self._detector_future.done():
            future = self._detector_future
            result_sequence = self._detector_future_sequence
            result_generation = self._detector_future_generation
            self._detector_future = None
            detector_frame = self._detector_future_frame
            self._detector_future_frame = None
            detections, inference_ms = future.result()
            self._record_detector_completion(inference_ms)

            if result_generation == self._detector_generation:
                detection_gap = 1
                if self._detector_last_applied_sequence is not None:
                    detection_gap = max(
                        1,
                        result_sequence - self._detector_last_applied_sequence,
                    )
                corrected_tracks = self.local_tracker.update(
                    detections,
                    frame_gap=detection_gap,
                )
                self._detector_last_applied_sequence = result_sequence
                self._detector_result_applied = True
                self._detector_reid_frame = detector_frame
                self._detector_reid_tracks = corrected_tracks

        frames_since_submit = (
            self.ncnn_detection_interval_frames
            if self._detector_last_submit_sequence is None
            else self._ncnn_sequence - self._detector_last_submit_sequence
        )
        if (
            self._detector_future is None
            and frames_since_submit >= self.ncnn_detection_interval_frames
        ):
            self._submit_ncnn_detection(frame)

        if self._detector_last_applied_sequence is None:
            return []
        prediction_gap = max(
            0,
            self._ncnn_sequence - self._detector_last_applied_sequence,
        )
        return self.local_tracker.predicted_tracks(prediction_gap)

    def track(self, frame: np.ndarray, frame_gap: int = 1,
              delta_time: Optional[float] = None,
              nominal_fps: Optional[float] = None) -> List[Dict[str, Any]]:
        if frame is None or frame.size == 0:
            return []

        self._frame_index += 1
        effective_gap = max(1, int(frame_gap))
        if delta_time is not None and nominal_fps is not None and nominal_fps > 0:
            elapsed_steps = max(1, int(round(float(delta_time) * float(nominal_fps))))
            effective_gap = max(effective_gap, elapsed_steps)
        if self.backend == "ncnn":
            if self.ncnn_async_detection:
                raw_tracks = self._track_ncnn_async(frame, effective_gap)
            else:
                detections = self.model.detect(frame)
                raw_tracks = self.local_tracker.update(detections, frame_gap=effective_gap)
                self._detector_result_applied = True
            ids = [int(item["track_id"]) for item in raw_tracks]
            xyxys = [item["bbox"] for item in raw_tracks]
            confs = [float(item["conf"]) for item in raw_tracks]
        else:
            import torch

            # FastTrack performs one Kalman prediction inside model.track(). Pre-advance
            # once per skipped published frame so fast motion is not underestimated.
            self._advance_kalman_for_gap(effective_gap)
            with torch.inference_mode():
                results = self.model.track(
                    source=frame, persist=True, tracker=self.tracker, classes=[0],
                    conf=self.conf, iou=self.iou, device=self.device, verbose=False, imgsz=self.imgsz,
                )
            if not results or results[0].boxes is None or results[0].boxes.id is None:
                return self.identity.update(frame, [])
            boxes = results[0].boxes
            ids = boxes.id.int().cpu().tolist()
            xyxys = boxes.xyxy.int().cpu().tolist()
            confs = boxes.conf.cpu().tolist()
        tracked_objects = self._build_tracked_objects(ids, xyxys, confs, frame.shape)

        # OSNet work is bounded per frame to prevent latency spikes in crowds.
        reid_features: Dict[int, np.ndarray] = {}
        if self.reid_encoder is not None:
            reid_frame = frame
            reid_tracks = tracked_objects
            if (
                self.backend == "ncnn"
                and self.ncnn_async_detection
                and self._detector_result_applied
                and self._detector_reid_frame is not None
            ):
                reid_frame = self._detector_reid_frame
                ids = [int(item["track_id"]) for item in self._detector_reid_tracks]
                boxes = [item["bbox"] for item in self._detector_reid_tracks]
                confidences = [float(item["conf"]) for item in self._detector_reid_tracks]
                reid_tracks = self._build_tracked_objects(
                    ids,
                    boxes,
                    confidences,
                    reid_frame.shape,
                )
            requests = self._select_reid_requests(reid_tracks)
            reid_features = self.reid_encoder.extract(reid_frame, requests)
            for local_id in reid_features:
                self._reid_last_sample[local_id] = self._frame_index
        self._detector_reid_frame = None
        self._detector_reid_tracks = []
        update_appearance = not (
            self.backend == "ncnn"
            and self.ncnn_async_detection
            and not self._detector_result_applied
        )
        return self.identity.update(
            frame,
            tracked_objects,
            reid_features=reid_features,
            update_appearance=update_appearance,
        )

    @property
    def backend_name(self) -> str:
        """Tên tracker thực tế mà Ultralytics đã khởi tạo."""
        if self.backend == "ncnn":
            return "LiteByteTracker/NCNN"
        predictor = getattr(self.model, "predictor", None)
        trackers = getattr(predictor, "trackers", []) or []
        return trackers[0].__class__.__name__ if trackers else "not_initialized"

    @property
    def detector_fps(self) -> float:
        return round(self._detector_fps, 1)

    @property
    def detector_latency_ms(self) -> float:
        return round(self._detector_latency_ms, 1)

    def reset(self) -> None:
        """Xóa trạng thái khi đổi nguồn để ID nguồn cũ không rò sang nguồn mới."""
        self.identity.reset()
        self._frame_index = 0
        self._reid_last_sample.clear()
        if self.backend == "ncnn":
            self._detector_generation += 1
            self._detector_last_applied_sequence = None
            self._detector_last_submit_sequence = None
            self._ncnn_sequence = 0
            self._detector_timestamps.clear()
            self._detector_fps = 0.0
            self._detector_latency_ms = 0.0
            self._detector_result_applied = False
            self._detector_reid_frame = None
            self._detector_reid_tracks = []
            if self.local_tracker is not None:
                self.local_tracker.reset()
            return
        predictor = getattr(self.model, "predictor", None)
        for tracker in getattr(predictor, "trackers", []) or []:
            if hasattr(tracker, "reset"):
                tracker.reset()

    def close(self) -> None:
        """Release the optional detector worker during application shutdown."""
        if self._detector_future is not None:
            self._detector_future.cancel()
            self._detector_future = None
        self._detector_future_frame = None
        if self._detector_executor is not None:
            self._detector_executor.shutdown(wait=False, cancel_futures=True)
            self._detector_executor = None
