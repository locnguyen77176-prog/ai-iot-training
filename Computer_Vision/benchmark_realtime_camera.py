"""Benchmark a video as a low-latency live camera with a one-frame buffer.

The simulation uses a virtual capture clock. Inference runtime determines which
published frames would have been overwritten while the AI worker was busy, so
the benchmark runs faster than wall-clock playback without becoming the
optimistic sequential-file mode used by the web uploader.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from collections import Counter

import cv2
import numpy as np
import torch
import yaml

from src.tracker import YOLOTracker
from src.video_stream import ThreadedVideoStream
from src.zone_counter import DualZoneCounter


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def seek_forward(cap: cv2.VideoCapture, current_index: int, wanted_index: int):
    """Decode forward without expensive random seeking and return the wanted frame."""
    while current_index < wanted_index:
        if not cap.grab():
            return current_index, None
        current_index += 1
    ok, frame = cap.retrieve()
    return current_index, frame if ok else None


def camera_degrade(frame: np.ndarray, jpeg_quality: int) -> np.ndarray:
    """Approximate a compressed 720p USB-camera frame without synthetic blur."""
    if jpeg_quality >= 100:
        return frame
    ok, encoded = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
    )
    if not ok:
        return frame
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    return decoded if decoded is not None else frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--camera-fps", type=float, default=15.0)
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-seconds", type=float, default=0.0)
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream) or {}
    det = cfg.get("detector", {})
    src = cfg.get("source", {})
    device = args.device or det.get("device", "cuda:0")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")
    source_fps = float(cap.get(cv2.CAP_PROP_FPS)) or 25.0
    source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    source_duration = source_frames / source_fps
    duration = min(source_duration, args.max_seconds) if args.max_seconds > 0 else source_duration
    total_published = max(1, int(np.floor(duration * args.camera_fps)))

    preprocessor = ThreadedVideoStream(
        src=args.video,
        width=1280,
        height=720,
        target_fps=args.camera_fps,
        flip_horizontal=src.get("flip_horizontal", False),
        anti_glare=src.get("anti_glare", {}),
    )

    load_started = time.perf_counter()
    tracker = YOLOTracker(
        model_path=det.get("model_path", "models/yolo26n.pt"),
        device=device,
        confidence_threshold=det.get("confidence_threshold", 0.25),
        iou_threshold=det.get("iou_threshold", 0.60),
        tracker=det.get("tracker", "custom_fasttrack.yaml"),
        imgsz=det.get("imgsz", 640),
        identity_memory_seconds=det.get("identity_memory_seconds", 40),
        identity_similarity_threshold=det.get("identity_similarity_threshold", 0.82),
        reid_model_path=det.get("reid_model_path"),
        reid_similarity_threshold=det.get("reid_similarity_threshold", 0.78),
        reid_ambiguity_margin=det.get("reid_ambiguity_margin", 0.0),
        reid_sample_interval_frames=det.get("reid_sample_interval_frames", 15),
        reid_min_confidence=det.get("reid_min_confidence", 0.55),
        reid_min_bbox_height=det.get("reid_min_bbox_height", 100),
        reid_gallery_size=det.get("reid_gallery_size", 5),
        reid_batch_size=det.get("reid_batch_size", 16),
        reid_max_per_frame=det.get("reid_max_per_frame", 4),
        reid_max_periodic_per_frame=det.get("reid_max_periodic_per_frame", 4),
        reid_periodic_schedule_frames=det.get("reid_periodic_schedule_frames", 3),
        reid_recheck_seconds=det.get("reid_recheck_seconds", 10.0),
    )
    model_load_seconds = time.perf_counter() - load_started

    # Warm up lazy Ultralytics predictor creation, CUDA kernels and OSNet before
    # starting the virtual camera clock. A production server pays this once at
    # startup, not as recurring real-time latency.
    warmup_started = time.perf_counter()
    ok, warmup_frame = cap.read()
    if ok and warmup_frame is not None:
        warmup_frame = preprocessor._prepare_frame(warmup_frame)
        warmup_frame = camera_degrade(
            warmup_frame, max(1, min(100, args.jpeg_quality))
        )
        for _ in range(3):
            tracker.track(warmup_frame)
        tracker.reset()
    warmup_seconds = time.perf_counter() - warmup_started
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    # Evaluation-only horizontal bands for these pedestrian-flow videos.
    counter = DualZoneCounter(
        zone_a=[[0, 70], [1279, 70], [1279, 310], [0, 310]],
        zone_b=[[0, 410], [1279, 410], [1279, 710], [0, 710]],
        in_label="IN",
        out_label="OUT",
        cooldown_seconds=cfg.get("zones", {}).get("cooldown_seconds", 3.0),
        state_ttl_seconds=cfg.get("zones", {}).get("state_ttl_seconds", 120.0),
        min_zone_hits=cfg.get("zones", {}).get("min_zone_hits", 2),
    )

    processing_times = []
    people_per_frame = []
    confidence_values = []
    local_ids = set()
    stable_ids = set()
    event_directions = Counter()
    delayed_corrections = 0
    processed = 0
    published_sequence = 0
    previous_sequence = None
    consumer_ready_time = 0.0
    current_source_index = -1
    wall_started = time.perf_counter()

    while published_sequence < total_published:
        capture_time = published_sequence / args.camera_fps
        process_start_time = max(capture_time, consumer_ready_time)
        wanted_source_index = min(
            source_frames - 1, int(round(capture_time * source_fps))
        )
        current_source_index, frame = seek_forward(cap, current_source_index, wanted_source_index)
        if frame is None:
            break

        frame = preprocessor._prepare_frame(frame)
        frame = camera_degrade(frame, max(1, min(100, args.jpeg_quality)))
        frame_gap = 1 if previous_sequence is None else max(
            1, published_sequence - previous_sequence
        )
        delta_time = frame_gap / args.camera_fps

        started = time.perf_counter()
        tracks = tracker.track(
            frame,
            frame_gap=frame_gap,
            delta_time=delta_time,
            nominal_fps=args.camera_fps,
        )
        events = counter.update(tracks)
        runtime = time.perf_counter() - started

        processing_times.append(runtime)
        people_per_frame.append(len(tracks))
        confidence_values.extend(float(t.get("conf", 0.0)) for t in tracks)
        local_ids.update(int(t.get("local_track_id", t["track_id"])) for t in tracks)
        stable_ids.update(int(t["track_id"]) for t in tracks)
        delayed_corrections += sum("identity_remapped_from" in t for t in tracks)
        event_directions.update(event["direction"] for event in events)
        processed += 1
        previous_sequence = published_sequence

        # The AI becomes ready after `runtime`; the one-slot camera buffer contains
        # the newest frame published by that virtual time. Always advance at least one.
        ready_time = process_start_time + runtime
        consumer_ready_time = ready_time
        published_sequence = max(
            published_sequence + 1,
            int(np.floor(ready_time * args.camera_fps + 1e-9)),
        )

        if processed % 500 == 0:
            print(
                f"[progress] processed={processed} published={published_sequence}/"
                f"{total_published} core_fps={processed / max(sum(processing_times), 1e-9):.2f}",
                flush=True,
            )

    cap.release()
    wall_seconds = time.perf_counter() - wall_started
    dropped = max(0, min(total_published, total_published - processed))
    processing_sum = sum(processing_times)
    result = {
        "video": os.path.abspath(args.video),
        "simulation": {
            "profile": "Logitech C270-like realtime",
            "resolution": [1280, 720],
            "camera_fps": args.camera_fps,
            "buffer": "latest-one-frame",
            "jpeg_quality": args.jpeg_quality,
            "flip_horizontal": bool(src.get("flip_horizontal", False)),
            "anti_glare_enabled": bool(src.get("anti_glare", {}).get("enabled", False)),
            "zones": "evaluation horizontal A(top) -> B(bottom)",
        },
        "source": {
            "fps": source_fps,
            "frames": source_frames,
            "duration_seconds": source_duration,
        },
        "runtime": {
            "device": device,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "python": platform.python_version(),
            "model_load_seconds": model_load_seconds,
            "warmup_seconds": warmup_seconds,
            "benchmark_wall_seconds": wall_seconds,
            "processing_seconds": processing_sum,
            "core_capacity_fps": processed / processing_sum if processing_sum else 0.0,
            "latency_ms_mean": statistics.fmean(processing_times) * 1000 if processing_times else 0.0,
            "latency_ms_p50": percentile(processing_times, 50) * 1000,
            "latency_ms_p95": percentile(processing_times, 95) * 1000,
            "latency_ms_max": max(processing_times, default=0.0) * 1000,
        },
        "realtime": {
            "published_frames": total_published,
            "processed_frames": processed,
            "dropped_frames": dropped,
            "drop_percent": 100.0 * dropped / total_published,
            "effective_ai_fps": processed / duration if duration else 0.0,
            "keeps_realtime": True,
        },
        "detections": {
            "people_total": sum(people_per_frame),
            "people_per_frame_mean": statistics.fmean(people_per_frame) if people_per_frame else 0.0,
            "people_per_frame_max": max(people_per_frame, default=0),
            "confidence_mean": statistics.fmean(confidence_values) if confidence_values else 0.0,
        },
        "tracking": {
            "local_ids": len(local_ids),
            "stable_ids": len(stable_ids),
            "reidentified_total": tracker.identity.reidentified_total,
            "delayed_corrections": delayed_corrections,
            "duplicates_suppressed": tracker.identity.duplicates_suppressed_total,
        },
        "counting": {
            "IN": event_directions.get("IN", 0),
            "OUT": event_directions.get("OUT", 0),
            "note": "No ground-truth passage labels; event totals are not accuracy metrics.",
        },
        "config": {
            "model": det.get("model_path", "models/yolo26n.pt"),
            "imgsz": det.get("imgsz", 640),
            "confidence_threshold": det.get("confidence_threshold", 0.25),
            "reid_max_per_frame": det.get("reid_max_per_frame", 4),
            "reid_recheck_seconds": det.get("reid_recheck_seconds", 10.0),
        },
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
