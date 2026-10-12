import os
import sys
import time
import argparse
import yaml
import cv2

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.video_stream import ThreadedVideoStream
from src.tracker import YOLOTracker
from src.zone_counter import DualZoneCounter
from src.db_manager import DatabaseManager
from src.visualizer import Visualizer


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main():
    parser = argparse.ArgumentParser(description="Real-time AI People Counting System (Dual-Zone ROI FSM)")
    parser.add_argument("--config", type=str, default="config.yaml", help="Đường dẫn tới file config.yaml")
    parser.add_argument("--source", type=str, default=None, help="Ghi đè nguồn video (0, RTSP URL, hoặc file .mp4)")
    args = parser.parse_args()

    # 1. Tải cấu hình
    cfg = load_config(args.config)
    source_val = args.source if args.source is not None else cfg.get("source", {}).get("path", 0)

    print("=" * 65)
    print("  AI PEOPLE COUNTING SYSTEM (DUAL-ZONE ROI STATE MACHINE)")
    print("=" * 65)

    # 2. Khởi tạo Database Manager
    db_cfg = cfg.get("database", {})
    db_manager = DatabaseManager(db_path=db_cfg.get("db_path", "database.db"))

    # 3. Khởi tạo Threaded Video Stream (Chống lag buffer)
    src_cfg = cfg.get("source", {})
    video_stream = ThreadedVideoStream(
        src=source_val,
        reconnect_interval=src_cfg.get("reconnect_interval", 3),
        width=src_cfg.get("width", 1280),
        height=src_cfg.get("height", 720),
        excluded_camera_names=src_cfg.get("excluded_camera_names", []),
        open_timeout_ms=src_cfg.get("open_timeout_ms", 5000),
        read_timeout_ms=src_cfg.get("read_timeout_ms", 5000),
        connect_warmup_frames=src_cfg.get("connect_warmup_frames", 5),
        target_fps=src_cfg.get("target_fps", 15),
        flip_horizontal=src_cfg.get("flip_horizontal", False),
        anti_glare=src_cfg.get("anti_glare", {})
    ).start()

    # Chờ stream nhận frame đầu tiên
    print("[Main] Đang chờ tín hiệu video...")
    for _ in range(30):
        test_frame = video_stream.read()
        if test_frame is not None:
            break
        time.sleep(0.1)

    if test_frame is None:
        print("[Main] Cảnh báo: Chưa nhận được frame từ camera. Vui lòng kiểm tra lại thiết bị/RTSP URL.")

    # 4. Khởi tạo YOLO26n + FastTrack + OSNet bên ngoài
    det_cfg = cfg.get("detector", {})
    backend = str(det_cfg.get("backend", "pytorch")).lower()
    is_cuda = False
    if backend == "pytorch":
        try:
            import torch

            is_cuda = torch.cuda.is_available() and ("cuda" in det_cfg.get("device", "cuda:0"))
        except ImportError:
            pass
    tracker = YOLOTracker(
        model_path=det_cfg.get("model_path", "models/yolo26n.pt"),
        device=det_cfg.get("device", "cuda:0"),
        confidence_threshold=det_cfg.get("confidence_threshold", 0.35),
        iou_threshold=det_cfg.get("iou_threshold", 0.45),
        tracker=det_cfg.get("tracker", "custom_fasttrack.yaml"),
        imgsz=det_cfg.get("imgsz", 640),
        identity_memory_seconds=det_cfg.get("identity_memory_seconds", 120.0),
        identity_similarity_threshold=det_cfg.get("identity_similarity_threshold", 0.82),
        reid_model_path=det_cfg.get("reid_model_path"),
        reid_similarity_threshold=det_cfg.get("reid_similarity_threshold", 0.78),
        reid_ambiguity_margin=det_cfg.get("reid_ambiguity_margin", 0.06),
        reid_sample_interval_frames=det_cfg.get("reid_sample_interval_frames", 15),
        reid_min_confidence=det_cfg.get("reid_min_confidence", 0.55),
        reid_min_bbox_height=det_cfg.get("reid_min_bbox_height", 100),
        reid_gallery_size=det_cfg.get("reid_gallery_size", 5),
        reid_batch_size=det_cfg.get("reid_batch_size", 16),
        reid_max_per_frame=det_cfg.get("reid_max_per_frame", 4),
        reid_max_periodic_per_frame=det_cfg.get("reid_max_periodic_per_frame", 4),
        reid_periodic_schedule_frames=det_cfg.get("reid_periodic_schedule_frames", 3),
        reid_recheck_seconds=det_cfg.get("reid_recheck_seconds", 10.0),
        backend=backend,
        ncnn_detector_param=det_cfg.get("ncnn_detector_param"),
        ncnn_detector_bin=det_cfg.get("ncnn_detector_bin"),
        ncnn_reid_param=det_cfg.get("ncnn_reid_param"),
        ncnn_reid_bin=det_cfg.get("ncnn_reid_bin"),
        ncnn_num_threads=det_cfg.get("ncnn_num_threads", 4),
        ncnn_use_vulkan=det_cfg.get("ncnn_use_vulkan", False),
    )

    # 5. Khởi tạo Dual-Zone Counter (Máy trạng thái FSM 2 Vùng Không Gian)
    zone_cfg = cfg.get("zones", {})
    default_zone_a = [[220, 140], [1060, 140], [1060, 340], [220, 340]]
    default_zone_b = [[220, 400], [1060, 400], [1060, 600], [220, 600]]
    zone_counter = DualZoneCounter(
        zone_a=zone_cfg.get("zone_a", default_zone_a),
        zone_b=zone_cfg.get("zone_b", default_zone_b),
        in_label=zone_cfg.get("in_label", "IN"),
        out_label=zone_cfg.get("out_label", "OUT"),
        cooldown_seconds=zone_cfg.get("cooldown_seconds", 3.0),
        state_ttl_seconds=zone_cfg.get("state_ttl_seconds", 120.0),
        min_zone_hits=zone_cfg.get("min_zone_hits", 2)
    )

    # 6. Khởi tạo Visualizer & OpenCV Window
    ui_cfg = cfg.get("ui", {})
    window_name = ui_cfg.get("window_name", "AI People Counter")
    visualizer = Visualizer(config_path=args.config)

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    print("[Main] Hệ thống đã khởi động thành công!")
    print("       - Phím 'r': Reset bộ đếm IN/OUT.")
    print("       - Phím 'q': Thoát chương trình.")

    frame_idx = 0
    fps_calc_start = time.time()
    display_fps = 0.0
    last_capture_sequence = None
    last_capture_time = None

    try:
        while True:
            capture = video_stream.read_packet(last_capture_sequence)
            if capture is None:
                time.sleep(0.01)
                continue
            raw_frame = capture.frame
            frame_gap = 1 if last_capture_sequence is None else max(
                1, int(capture.sequence - last_capture_sequence)
            )
            delta_time = None if last_capture_time is None else max(
                0.0, float(capture.captured_at - last_capture_time)
            )
            last_capture_sequence = capture.sequence
            last_capture_time = capture.captured_at

            frame_idx += 1
            h_r, w_r = raw_frame.shape[:2]
            if w_r != 1280 or h_r != 720:
                frame = cv2.resize(raw_frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
            else:
                frame = raw_frame.copy()

            # 1. Phát hiện & Bám vết người
            tracks = tracker.track(
                frame,
                frame_gap=frame_gap,
                delta_time=delta_time,
                nominal_fps=getattr(video_stream, "target_fps", 0.0),
            )

            # 2. Xử lý chuyển vùng đếm (Dual-Zone State Machine)
            crossing_events = zone_counter.update(tracks)

            # 3. Ghi nhận sự kiện vào SQLite khi hoàn thành chuyển vùng
            for ev in crossing_events:
                track_id = ev['track_id']
                direction = ev['direction']

                # Lưu vào database
                event_id = db_manager.log_event(
                    track_id=track_id,
                    direction=direction
                )

                print(f"[EVENT #{event_id}] Track #{track_id} -> {direction}")

            # 4. Tính toán FPS hiển thị
            if frame_idx % 10 == 0:
                elapsed = time.time() - fps_calc_start
                if elapsed > 0:
                    display_fps = 10.0 / elapsed
                fps_calc_start = time.time()

            # 5. Render đồ họa OSD 2 Vùng Không Gian
            frame = visualizer.draw_zones(
                frame, zone_counter.zone_a_pts, zone_counter.zone_b_pts, 
                zone_counter.in_label, zone_counter.out_label
            )
            frame = visualizer.draw_tracks(
                frame, tracks, zone_counter.track_history, zone_counter.counted_tracks
            )
            frame = visualizer.draw_hud(
                frame, zone_counter.total_in, zone_counter.total_out, 
                display_fps, is_cuda=is_cuda
            )

            cv2.imshow(window_name, frame)

            # 6. Xử lý phím bấm
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 'q' hoặc ESC
                break
            elif key == ord('r'):
                zone_counter.reset_counts()
                print("[Main] Đã reset bộ đếm IN/OUT!")

    except KeyboardInterrupt:
        print("\n[Main] Nhận tín hiệu dừng từ bàn phím...")
    finally:
        print("[Main] Đang dọn dẹp tài nguyên và tắt hệ thống...")
        video_stream.stop()
        db_manager.close()
        cv2.destroyAllWindows()
        print("[Main] Kết thúc hoàn tất!")


if __name__ == "__main__":
    main()
