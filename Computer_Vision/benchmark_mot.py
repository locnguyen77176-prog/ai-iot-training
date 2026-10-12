"""Benchmark pipeline hiện tại trên một video mà không ghi dữ liệu vào database."""

import argparse
import json
import platform
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import torch
import yaml

from src.tracker import YOLOTracker
from src.zone_counter import DualZoneCounter


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", nargs="?", default="uploads/MOT16-03.mp4")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default="benchmark_mot16_03_fasttrack_osnet.json")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream)
    det, zones = cfg["detector"], cfg["zones"]
    if str(args.device).startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("Benchmark yêu cầu GPU nhưng torch.cuda.is_available() = False")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Không mở được video: {args.video}")
    source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    source_fps = float(cap.get(cv2.CAP_PROP_FPS))
    source_size = [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]

    load_start = time.perf_counter()
    tracker = YOLOTracker(
        model_path=det["model_path"], device=args.device,
        confidence_threshold=det.get("confidence_threshold", 0.25),
        iou_threshold=det.get("iou_threshold", 0.60), tracker=det["tracker"],
        imgsz=det.get("imgsz", 960),
        identity_memory_seconds=det.get("identity_memory_seconds", 120),
        identity_similarity_threshold=det.get("identity_similarity_threshold", 0.82),
        reid_model_path=det.get("reid_model_path"),
        reid_similarity_threshold=det.get("reid_similarity_threshold", 0.78),
        reid_ambiguity_margin=det.get("reid_ambiguity_margin", 0.06),
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
    model_load_seconds = time.perf_counter() - load_start
    counter = DualZoneCounter(
        zones["zone_a"], zones["zone_b"], zones.get("in_label", "IN"),
        zones.get("out_label", "OUT"), zones.get("cooldown_seconds", 3),
        zones.get("state_ttl_seconds", 120), zones.get("min_zone_hits", 2),
    )

    processed = 0
    detection_count = 0
    people_per_frame = []
    confidences = []
    inference_times = []
    stable_frames = defaultdict(list)
    local_ids = set()
    stable_ids = set()
    event_directions = Counter()
    started = time.perf_counter()

    while True:
        ok, frame = cap.read()
        if not ok or frame is None or (args.max_frames and processed >= args.max_frames):
            break
        frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
        t0 = time.perf_counter()
        tracks = tracker.track(frame)
        if processed == 0 and tracker.backend_name != "FASTTracker":
            raise RuntimeError(
                f"Sai tracker backend: cần FASTTracker, nhận {tracker.backend_name}"
            )
        inference_times.append(time.perf_counter() - t0)
        for event in counter.update(tracks):
            event_directions[event["direction"]] += 1

        processed += 1
        people_per_frame.append(len(tracks))
        detection_count += len(tracks)
        for track in tracks:
            stable_id = int(track["track_id"])
            stable_ids.add(stable_id)
            local_ids.add(int(track.get("local_track_id", stable_id)))
            stable_frames[stable_id].append(processed)
            confidences.append(float(track["conf"]))
        if processed % 100 == 0:
            elapsed = time.perf_counter() - started
            print(f"[Benchmark] {processed}/{source_frames} frame - {processed / elapsed:.2f} FPS", flush=True)

    elapsed = time.perf_counter() - started
    cap.release()
    lifetimes = [len(frames) for frames in stable_frames.values()]
    spans = [frames[-1] - frames[0] + 1 for frames in stable_frames.values()]
    reconnects = max(0, len(local_ids) - len(stable_ids))
    report = {
        "video": str(Path(args.video).resolve()),
        "source": {"frames": source_frames, "fps": source_fps, "size": source_size,
                   "duration_seconds": source_frames / source_fps if source_fps else 0},
        "processed_frames": processed,
        "runtime": {
            "backend": tracker.backend_name,
            "external_reid": (
                tracker.reid_encoder.__class__.__name__
                if tracker.reid_encoder is not None else "disabled"
            ),
            "device": tracker.device,
            "gpu": torch.cuda.get_device_name(0) if str(tracker.device).startswith("cuda") else None,
            "cuda": torch.version.cuda,
            "python": platform.python_version(),
            "torch": torch.__version__, "opencv": cv2.__version__,
            "model_load_seconds": round(model_load_seconds, 3),
            "processing_seconds": round(elapsed, 3),
            "pipeline_fps": round(processed / elapsed, 3) if elapsed else 0,
            "realtime_factor": round((processed / elapsed) / source_fps, 3) if elapsed and source_fps else 0,
            "latency_ms_mean": round(statistics.mean(inference_times) * 1000, 2) if inference_times else 0,
            "latency_ms_p95": round(percentile(inference_times, 0.95) * 1000, 2),
        },
        "detections": {
            "total": detection_count,
            "people_per_frame_mean": round(statistics.mean(people_per_frame), 3) if people_per_frame else 0,
            "people_per_frame_max": max(people_per_frame, default=0),
            "confidence_mean": round(statistics.mean(confidences), 4) if confidences else 0,
            "confidence_p05": round(percentile(confidences, 0.05), 4),
        },
        "tracking": {
            "unique_local_ids": len(local_ids), "unique_stable_ids": len(stable_ids),
            "local_ids_reconnected": reconnects,
            "reidentified_events": tracker.identity.reidentified_total,
            "duplicate_boxes_suppressed": tracker.identity.duplicates_suppressed_total,
            "observed_frames_per_id_median": round(statistics.median(lifetimes), 2) if lifetimes else 0,
            "observed_frames_per_id_p95": round(percentile(lifetimes, 0.95), 2),
            "track_span_frames_median": round(statistics.median(spans), 2) if spans else 0,
        },
        "counting": {"in": counter.total_in, "out": counter.total_out,
                     "events": dict(event_directions)},
        "config": {"detector": det, "zones": zones},
        "notes": [
            "Không có ground-truth đi kèm nên các chỉ số tracking không phải MOTA/IDF1.",
            "IN/OUT phụ thuộc trực tiếp vào ROI hiện tại trong config.yaml.",
        ],
    }
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
