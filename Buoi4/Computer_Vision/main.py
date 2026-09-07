import os
import sys
import time
import argparse
import yaml
import cv2
import torch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.video_stream import ThreadedVideoStream
from src.tracker import YOLOTracker
from src.line_counter import VirtualLineCounter
from src.demographics import DemographicsEstimator
from src.db_manager import DatabaseManager
from src.visualizer import Visualizer


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Real-time AI People Counting & Demographics System")
    parser.add_argument("--config", type=str, default="config.yaml", help="Đường dẫn tới file config.yaml")
    parser.add_argument("--source", type=str, default=None, help="Ghi đè nguồn video (0, RTSP URL, hoặc file .mp4)")
    args = parser.parse_args()

    # 1. Tải cấu hình
    cfg = load_config(args.config)
    source_val = args.source if args.source is not None else cfg["source"]["path"]

    print("=" * 65)
    print("  AI PEOPLE COUNTING & DEMOGRAPHICS SYSTEM (REAL-TIME)")
    print("=" * 65)

    # 2. Khởi tạo Database Manager
    db_cfg = cfg.get("database", {})
    db_manager = DatabaseManager(
        db_path=db_cfg.get("db_path", "database.db"),
        save_snapshots=db_cfg.get("save_snapshots", True),
        snapshot_dir=db_cfg.get("snapshot_dir", "captures")
    )

    # 3. Khởi tạo Threaded Video Stream (Chống lag buffer)
    src_cfg = cfg.get("source", {})
    video_stream = ThreadedVideoStream(
        src=source_val,
        reconnect_interval=src_cfg.get("reconnect_interval", 3),
        width=src_cfg.get("width", 1280),
        height=src_cfg.get("height", 720)
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

    # 4. Khởi tạo YOLOv8 + ByteTrack
    det_cfg = cfg.get("detector", {})
    is_cuda = torch.cuda.is_available() and ("cuda" in det_cfg.get("device", "cuda:0"))
    tracker = YOLOTracker(
        model_path=det_cfg.get("model_path", "yolov8n.pt"),
        device=det_cfg.get("device", "cuda:0"),
        confidence_threshold=det_cfg.get("confidence_threshold", 0.5),
        iou_threshold=det_cfg.get("iou_threshold", 0.45),
        tracker=det_cfg.get("tracker", "bytetrack.yaml")
    )

    # 5. Khởi tạo Virtual Line Counter
    line_cfg = cfg.get("counting_line", {})
    line_counter = VirtualLineCounter(
        point_a=line_cfg.get("point_a", [200, 400]),
        point_b=line_cfg.get("point_b", [1080, 400]),
        in_label=line_cfg.get("in_label", "IN"),
        out_label=line_cfg.get("out_label", "OUT"),
        cooldown_seconds=line_cfg.get("cooldown_seconds", 2.5)
    )

    # 6. Khởi tạo Demographics Estimator (Face + Gender)
    demo_cfg = cfg.get("demographics", {})
    demographics = DemographicsEstimator(
        face_model_path=demo_cfg.get("face_model_path", "models/face_detection_yunet_2023mar.onnx"),
        gender_model_path=demo_cfg.get("gender_model_path", "models/gender_googlenet.onnx"),
        face_score_threshold=demo_cfg.get("face_score_threshold", 0.6),
        interval_frames=demo_cfg.get("interval_frames", 3)
    )

    # 7. Khởi tạo Visualizer & OpenCV Window
    ui_cfg = cfg.get("ui", {})
    window_name = ui_cfg.get("window_name", "AI People Counter & Demographics")
    visualizer = Visualizer(config_path=args.config)

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, visualizer.mouse_callback, {"line_counter": line_counter})

    print("[Main] Hệ thống đã khởi động thành công!")
    print("       - Phím 's': Bật chế độ click 2 điểm bằng chuột để chỉnh vạch đếm.")
    print("       - Phím 'r': Reset bộ đếm IN/OUT.")
    print("       - Phím 'q': Thoát chương trình.")

    frame_idx = 0
    fps_calc_start = time.time()
    display_fps = 0.0

    try:
        while True:
            raw_frame = video_stream.read()
            if raw_frame is None:
                time.sleep(0.01)
                continue

            frame_idx += 1
            h_r, w_r = raw_frame.shape[:2]
            if w_r != 1280 or h_r != 720:
                frame = cv2.resize(raw_frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
            else:
                frame = raw_frame.copy()

            # 1. Phát hiện & Bám vết người
            tracks = tracker.track(frame)

            # 2. Phân tích khuôn mặt & nhân khẩu học (Rolling Buffer)
            if demo_cfg.get("enabled", True):
                demographics.process_tracks(frame, tracks, frame_idx)

            # 3. Kiểm tra cắt vạch đếm IN/OUT
            crossing_events = line_counter.update(tracks)

            # 4. Ghi nhận sự kiện vào SQLite khi có người cắt vạch
            for ev in crossing_events:
                track_id = ev['track_id']
                direction = ev['direction']
                bbox = ev['bbox']

                # Lấy kết quả biểu quyết từ rolling buffer
                demo_info = demographics.get_demographics(track_id)
                gender = demo_info['gender']
                gender_conf = demo_info['gender_confidence']

                # Cắt ảnh snapshot của người (hoặc khuôn mặt tốt nhất)
                h_f, w_f = frame.shape[:2]
                x1, y1, x2, y2 = bbox
                person_crop = frame[max(0, y1):min(h_f, y2), max(0, x1):min(w_f, x2)]

                # Lưu vào database
                event_id = db_manager.log_event(
                    track_id=track_id,
                    direction=direction,
                    gender=gender,
                    gender_conf=gender_conf,
                    frame_snapshot=person_crop
                )

                print(f"[EVENT #{event_id}] Track {track_id} -> {direction} | Giới tính: {gender} ({gender_conf})")

            # 5. Tính toán FPS hiển thị
            if frame_idx % 10 == 0:
                elapsed = time.time() - fps_calc_start
                if elapsed > 0:
                    display_fps = 10.0 / elapsed
                fps_calc_start = time.time()

            # 6. Render đồ họa OSD
            frame = visualizer.draw_counting_line(
                frame, line_counter.point_a, line_counter.point_b, 
                line_counter.in_label, line_counter.out_label
            )
            frame = visualizer.draw_tracks(
                frame, tracks, demographics, line_counter.track_history, line_counter.counted_tracks
            )
            frame = visualizer.draw_hud(
                frame, line_counter.total_in, line_counter.total_out, 
                display_fps, is_cuda=is_cuda
            )

            cv2.imshow(window_name, frame)

            # 7. Xử lý phím bấm
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 'q' hoặc ESC
                break
            elif key == ord('s'):
                visualizer.setup_mode = not visualizer.setup_mode
                visualizer.temp_points.clear()
                state_str = "BẬT" if visualizer.setup_mode else "TẮT"
                print(f"[Main] Chế độ cài đặt vạch đếm bằng chuột: {state_str}")
            elif key == ord('r'):
                line_counter.reset_counts()
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
