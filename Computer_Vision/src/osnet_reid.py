"""Lightweight OSNet inference wrapper for long-term person re-identification."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Dict, Iterable, Optional

import cv2
import numpy as np
import torch


def _load_osnet_factory():
    """Load only torchreid's OSNet model module, avoiding its training dependencies."""
    try:
        from torchreid.reid.models.osnet import osnet_x0_25

        return osnet_x0_25
    except Exception as import_error:
        spec = importlib.util.find_spec("torchreid")
        if spec is None or not spec.submodule_search_locations:
            raise RuntimeError("torchreid is not installed") from import_error

        module_path = Path(next(iter(spec.submodule_search_locations))) / "reid" / "models" / "osnet.py"
        if not module_path.exists():
            raise RuntimeError(f"Cannot locate torchreid OSNet module: {module_path}") from import_error

        module_spec = importlib.util.spec_from_file_location("_visionflow_torchreid_osnet", module_path)
        if module_spec is None or module_spec.loader is None:
            raise RuntimeError(f"Cannot load torchreid OSNet module: {module_path}") from import_error
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return module.osnet_x0_25


class OSNetReIDEncoder:
    """Extract normalized 512-D person embeddings from an OSNet x0.25 checkpoint."""

    input_width = 128
    input_height = 256
    mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
    std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)

    def __init__(self, checkpoint: str, device: str = "cpu", batch_size: int = 16):
        self.checkpoint = os.path.abspath(checkpoint)
        self.device = torch.device(device)
        self.batch_size = max(1, int(batch_size))
        self.model = None
        self.error: Optional[str] = None

        try:
            if not os.path.isfile(self.checkpoint):
                raise FileNotFoundError(self.checkpoint)
            state = torch.load(self.checkpoint, map_location="cpu", weights_only=True)
            if isinstance(state, dict) and "state_dict" in state:
                state = state["state_dict"]
            if not isinstance(state, dict):
                raise TypeError("checkpoint does not contain a state_dict")
            state = {str(k).removeprefix("module."): v for k, v in state.items()}

            classifier = state.get("classifier.weight")
            num_classes = int(classifier.shape[0]) if classifier is not None else 1000
            factory = _load_osnet_factory()
            model = factory(num_classes=num_classes, pretrained=False, loss="softmax")
            missing, unexpected = model.load_state_dict(state, strict=False)
            important_missing = [k for k in missing if not k.startswith("classifier.")]
            important_unexpected = [k for k in unexpected if not k.startswith("classifier.")]
            if important_missing or important_unexpected:
                raise RuntimeError(
                    f"incompatible checkpoint (missing={important_missing[:3]}, "
                    f"unexpected={important_unexpected[:3]})"
                )
            self.model = model.eval().to(self.device)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return self.model is not None

    @classmethod
    def _prepare_crop(cls, frame: np.ndarray, bbox: Iterable[int]) -> Optional[torch.Tensor]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x2 - x1 < 12 or y2 - y1 < 24:
            return None
        crop = frame[y1:y2, x1:x2]
        crop = cv2.resize(crop, (cls.input_width, cls.input_height), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb = (rgb - cls.mean) / cls.std
        return torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)))

    @torch.inference_mode()
    def extract(self, frame: np.ndarray, tracks: Iterable[dict]) -> Dict[int, np.ndarray]:
        """Return embeddings keyed by local track ID for all valid crops."""
        if self.model is None:
            return {}

        prepared = []
        for track in tracks:
            tensor = self._prepare_crop(frame, track["bbox"])
            if tensor is not None:
                prepared.append((int(track["track_id"]), tensor))

        output: Dict[int, np.ndarray] = {}
        for start in range(0, len(prepared), self.batch_size):
            chunk = prepared[start:start + self.batch_size]
            batch = torch.stack([item[1] for item in chunk]).to(self.device, non_blocking=True)
            features = self.model(batch)
            features = torch.nn.functional.normalize(features.float(), dim=1).cpu().numpy()
            for (track_id, _), feature in zip(chunk, features):
                output[track_id] = feature.astype(np.float32, copy=False)
        return output
