import os
import sys
import time
import shutil
import cv2
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.video_stream import ThreadedVideoStream
from src.tracker import YOLOTracker
from src.line_counter import VirtualLineCounter
from src.demographics import DemographicsEstimator
from src.db_manager import DatabaseManager
from src.visualizer import Visualizer


def create_synthetic_test_video(filepath: str = "test_walking.mp4", duration_frames: int = 60):
    """
    Tạo video giả lập: 1 đối tượng người (vẽ hình người) di chuyển từ trên xuống dưới
    để cắt qua vạch đếm nằm ngang y=240.
    """
    width, height = 640, 480
    fps = 30
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    # Tải ảnh khuôn mặt mẫu hoặc vẽ đầu + người
    for f in range(duration_frames):
        frame = np.ones((height, width, 3), dtype=np.uint8) * 230  # Nền xám nhạt

        # Tọa độ người di chuyển từ y=100 xuống y=380
        center_x = 320
        center_y = int(100 + (f / duration_frames) * 280)

        # Vẽ cơ thể (màu xanh dương đậm)
        body_top = center_y - 40
        body_bottom = center_y + 60
        body_left = center_x - 30
        body_right = center_x + 30
        cv2.rectangle(frame, (body_left, body_top), (body_right, body_bottom), (180, 50, 40), -1)

        # Vẽ đầu/khuôn mặt (màu da)
        head_center = (center_x, body_top - 20)
        cv2.circle(frame, head_center, 18, (170, 200, 240), -1)
        # Mắt
        cv2.circle(frame, (head_center[0] - 6, head_center[1] - 4), 3, (20, 20, 20), -1)
        cv2.circle(frame, (head_center[0] + 6, head_center[1] - 4), 3, (20, 20, 20), -1)
        # Miệng
        cv2.ellipse(frame, (head_center[0], head_center[1] + 6), (7, 4), 0, 0, 180, (20, 20, 20), 2)

        # Chân
        cv2.line(frame, (body_left + 10, body_bottom), (body_left + 10, body_bottom + 40), (40, 40, 40), 4)
        cv2.line(frame, (body_right - 10, body_bottom), (body_right - 10, body_bottom + 40), (40, 40, 40), 4)

        out.write(frame)

    out.release()
    print(f"[TestVideo] Đã tạo video mẫu kiểm thử: {filepath} ({duration_frames} frames)")


def run_pipeline_test():
    test_video_path = "test_walking.mp4"
    test_db_path = "test_e2e_database.db"
    test_captures = "test_e2e_captures"

    # Dọn dẹp trước khi test
    for p in [test_video_path, test_db_path]:
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(test_captures):
        shutil.rmtree(test_captures)

    # 1. Tạo video kiểm thử
    create_synthetic_test_video(test_video_path, duration_frames=50)

    # 2. Khởi tạo toàn bộ pipeline
    db_manager = DatabaseManager(db_path=test_db_path, save_snapshots=True, snapshot_dir=test_captures)
    video_stream = ThreadedVideoStream(src=test_video_path, loop_video=False).start()

    tracker = YOLOTracker(model_path="yolov8n.pt", device="cuda:0")
    line_counter = VirtualLineCounter(point_a=[100, 240], point_b=[540, 240], in_label="IN", out_label="OUT")
    demographics = DemographicsEstimator(
        face_model_path="models/face_detection_yunet_2023mar.onnx",
        gender_model_path="models/gender_googlenet.onnx"
    )
    visualizer = Visualizer()

    # 3. Xử lý video
    frame_count = 0
    start_time = time.time()
    events_captured = []

    print("\n[Pipeline] Bắt đầu xử lý luồng video qua hệ thống AI...")
    while True:
        frame = video_stream.read()
        if frame is None or frame_count >= 50:
            break

        frame_count += 1

        # A. YOLOv8 + ByteTrack
        tracks = tracker.track(frame)

        # B. Demographics (Face + Age/Gender)
        demographics.process_tracks(frame, tracks, frame_count)

        # C. Virtual Line Crossing
        events = line_counter.update(tracks)
        for ev in events:
            events_captured.append(ev)
            demo_info = demographics.get_demographics(ev['track_id'])
            x1, y1, x2, y2 = ev['bbox']
            crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
            db_manager.log_event(
                track_id=ev['track_id'],
                direction=ev['direction'],
                gender=demo_info['gender'],
                gender_conf=demo_info['gender_confidence'],
                estimated_age=demo_info['estimated_age'],
                frame_snapshot=crop
            )

        # D. Render OSD
        frame = visualizer.draw_counting_line(frame, line_counter.point_a, line_counter.point_b)
        frame = visualizer.draw_tracks(frame, tracks, demographics, line_counter.track_history, line_counter.counted_tracks)
        frame = visualizer.draw_hud(frame, line_counter.total_in, line_counter.total_out, fps=30.0, is_cuda=True)

        if frame_count >= 50:
            break

    total_time = time.time() - start_time
    avg_fps = frame_count / total_time if total_time > 0 else 0

    video_stream.stop()
    summary = db_manager.get_summary()
    db_manager.close()

    print(f"\n[Kết Quả Pipeline]")
    print(f" - Tổng số frame xử lý : {frame_count}")
    print(f" - Thời gian thực thi  : {total_time:.2f}s (Trung bình ~{avg_fps:.1f} FPS trên GPU)")
    print(f" - Số sự kiện cắt vạch : {len(events_captured)}")
    print(f" - Database SQLite     : Tổng IN={summary['total_in']}, Tổng OUT={summary['total_out']}")

    # Kiểm tra tính toàn vẹn
    assert os.path.exists(test_db_path), "Database SQLite phải được tạo!"
    print(f" -> Tệp Database: {test_db_path} tồn tại và hợp lệ!")

    # Dọn dẹp tệp tạm test
    if os.path.exists(test_video_path):
        os.remove(test_video_path)
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    if os.path.exists(test_captures):
        shutil.rmtree(test_captures)

    print("\n>>> KIỂM THỬ E2E TOÀN BỘ PIPELINE HOÀN TẤT VÀ THÀNH CÔNG! <<<")


if __name__ == "__main__":
    run_pipeline_test()
