"""Run both NCNN models once and report basic timing/output checks."""

from __future__ import annotations

import argparse
import os
import sys
import time

import cv2
import numpy as np
import yaml

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.ncnn_backend import NcnnOSNetEncoder, NcnnYoloDetector


def resolve(base_dir: str, path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(base_dir, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.pi.yaml")
    parser.add_argument("--image", default=None)
    args = parser.parse_args()

    base_dir = PROJECT_DIR
    config_path = resolve(base_dir, args.config)
    with open(config_path, "r", encoding="utf-8") as handle:
        detector_cfg = (yaml.safe_load(handle) or {})["detector"]

    if args.image:
        image = cv2.imread(resolve(base_dir, args.image))
        if image is None:
            raise FileNotFoundError(args.image)
    else:
        x = np.linspace(0, 255, 1280, dtype=np.uint8)
        image = np.repeat(x[None, :, None], 720, axis=0)
        image = np.repeat(image, 3, axis=2)

    threads = int(detector_cfg.get("ncnn_num_threads", 4))
    detector = NcnnYoloDetector(
        resolve(base_dir, detector_cfg["ncnn_detector_param"]),
        resolve(base_dir, detector_cfg["ncnn_detector_bin"]),
        imgsz=int(detector_cfg.get("imgsz", 640)),
        confidence_threshold=float(detector_cfg.get("confidence_threshold", 0.25)),
        iou_threshold=float(detector_cfg.get("iou_threshold", 0.6)),
        num_threads=threads,
    )
    started = time.perf_counter()
    detections = detector.detect(image)
    detector_ms = (time.perf_counter() - started) * 1000.0

    encoder = NcnnOSNetEncoder(
        resolve(base_dir, detector_cfg["ncnn_reid_param"]),
        resolve(base_dir, detector_cfg["ncnn_reid_bin"]),
        num_threads=threads,
    )
    height, width = image.shape[:2]
    started = time.perf_counter()
    embeddings = encoder.extract(
        image, [{"track_id": 1, "bbox": [0, 0, width, height]}]
    )
    reid_ms = (time.perf_counter() - started) * 1000.0
    embedding = embeddings.get(1)
    if embedding is None or embedding.shape != (512,) or not np.isfinite(embedding).all():
        raise RuntimeError("OSNet NCNN smoke test returned an invalid embedding")

    print(f"YOLO NCNN OK: {detector_ms:.1f} ms, detections={len(detections)}")
    print(f"OSNet NCNN OK: {reid_ms:.1f} ms, embedding=512, norm={np.linalg.norm(embedding):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
