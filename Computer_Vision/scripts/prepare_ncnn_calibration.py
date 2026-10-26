"""Build a deterministic YOLO NCNN calibration set from videos or images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def letterbox(image: np.ndarray, size: int = 640) -> np.ndarray:
    """Match Ultralytics' centered letterbox geometry and padding color."""
    height, width = image.shape[:2]
    scale = min(size / width, size / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    left = (size - resized_width) // 2
    top = (size - resized_height) // 2
    canvas[top : top + resized_height, left : left + resized_width] = resized
    return canvas


def evenly_spaced_indices(frame_count: int, requested: int) -> list[int]:
    if frame_count <= 0 or requested <= 0:
        return []
    # Exclude the first/last 2% where camera movement or fades are common.
    start = min(frame_count - 1, max(0, round(frame_count * 0.02)))
    end = max(start, min(frame_count - 1, round(frame_count * 0.98) - 1))
    count = min(requested, end - start + 1)
    return sorted({int(round(value)) for value in np.linspace(start, end, count)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=Path, default=Path("uploads"))
    parser.add_argument(
        "--images",
        type=Path,
        help="Use labeled training images instead of extracting frames from videos.",
    )
    parser.add_argument("--output", type=Path, default=Path("datasets/calibration/yolo320"))
    parser.add_argument("--per-video", type=int, default=200)
    parser.add_argument("--max-images", type=int, default=1000)
    parser.add_argument("--size", type=int, default=320)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    image_paths: list[Path] = []

    if args.images is not None:
        candidates = sorted(
            path for path in args.images.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not candidates:
            raise RuntimeError(f"No calibration images found in {args.images}")
        indices = evenly_spaced_indices(len(candidates), min(args.max_images, len(candidates)))
        for sequence, index in enumerate(indices):
            source = candidates[index]
            frame = cv2.imread(str(source))
            if frame is None:
                continue
            destination = args.output / f"calibration_{sequence:04d}.jpg"
            prepared = letterbox(frame, args.size)
            if not cv2.imwrite(str(destination), prepared, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f"Cannot write {destination}")
            image_paths.append(destination.resolve())
        records.append({"images": str(args.images.resolve()), "calibration_frames": len(image_paths)})
    else:
        videos = sorted(
            path for path in args.videos.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        )
        if not videos:
            raise RuntimeError(f"No calibration videos found in {args.videos}")

        for video in videos:
            capture = cv2.VideoCapture(str(video))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            saved = 0
            for sequence, frame_index in enumerate(evenly_spaced_indices(frame_count, args.per_video)):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                prepared = letterbox(frame, args.size)
                destination = args.output / f"{video.stem}_{sequence:04d}.jpg"
                if not cv2.imwrite(str(destination), prepared, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                    raise RuntimeError(f"Cannot write {destination}")
                image_paths.append(destination.resolve())
                saved += 1
            capture.release()
            records.append(
                {
                    "video": str(video.resolve()),
                    "source_frames": frame_count,
                    "source_fps": fps,
                    "calibration_frames": saved,
                }
            )

    list_path = args.output.parent / f"{args.output.name}_calibration.txt"
    list_path.write_text(
        "".join(f"{path.as_posix()}\n" for path in image_paths),
        encoding="utf-8",
    )
    manifest = {
        "input_size": [args.size, args.size],
        "letterbox_color": 114,
        "image_count": len(image_paths),
        "image_list": str(list_path.resolve()),
        "sources": records,
    }
    manifest_path = args.output.parent / f"{args.output.name}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
