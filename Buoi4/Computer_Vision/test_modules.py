import os
import sys
import shutil
import numpy as np
import cv2

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.line_counter import VirtualLineCounter, segments_intersect
from src.db_manager import DatabaseManager
from src.visualizer import Visualizer


def test_line_intersection_math():
    print("[Test 1] Kiểm tra toán học giao cắt vector vạch ảo...")
    # Vạch ngang từ (100, 300) đến (500, 300)
    A = (100, 300)
    B = (500, 300)

    # Điểm di chuyển từ trên xuống dưới (300, 250) -> (300, 350)
    C1 = (300, 250)
    D1 = (300, 350)
    assert segments_intersect(A, B, C1, D1) == True, "Lỗi: Điểm cắt nhau nhưng thuật toán trả về False"

    # Điểm di chuyển song song không cắt (300, 200) -> (400, 200)
    C2 = (300, 200)
    D2 = (400, 200)
    assert segments_intersect(A, B, C2, D2) == False, "Lỗi: Điểm không cắt nhưng thuật toán trả về True"

    print(" -> Thuật toán giao cắt đoạn thẳng: PASS!")


def test_line_counter_logic():
    print("[Test 2] Kiểm tra VirtualLineCounter (IN/OUT & Debounce)...")
    counter = VirtualLineCounter(point_a=[100, 300], point_b=[500, 300], cooldown_seconds=2.0)

    # Mô phỏng người ID=1 đi từ trên xuống dưới (IN)
    # Frame 1: ở trên vạch
    tracks_f1 = [{'track_id': 1, 'bbox': [280, 200, 320, 280], 'conf': 0.9}]
    events_f1 = counter.update(tracks_f1)
    assert len(events_f1) == 0, "Frame 1 chưa cắt vạch"

    # Frame 2: bước qua vạch (y_bottom từ 280 -> 320)
    tracks_f2 = [{'track_id': 1, 'bbox': [280, 240, 320, 320], 'conf': 0.9}]
    events_f2 = counter.update(tracks_f2)
    assert len(events_f2) == 1, "Frame 2 phải phát hiện cắt vạch"
    assert events_f2[0]['direction'] == "IN", f"Kỳ vọng IN, thực tế: {events_f2[0]['direction']}"
    assert counter.total_in == 1, "Tổng IN phải là 1"

    # Frame 3: người ID=1 vẫn đang ở gần vạch (y_bottom từ 320 -> 290 - quay đầu ngay)
    tracks_f3 = [{'track_id': 1, 'bbox': [280, 210, 320, 290], 'conf': 0.9}]
    events_f3 = counter.update(tracks_f3)
    assert len(events_f3) == 0, "Cooldown phải chặn đếm lặp trong 2s"

    print(" -> Logic Đếm IN/OUT & Cooldown: PASS!")


def test_db_manager():
    print("[Test 3] Kiểm tra DatabaseManager (SQLite & Snapshot)...")
    test_db = "test_database.db"
    test_dir = "test_captures"
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    db = DatabaseManager(db_path=test_db, save_snapshots=True, snapshot_dir=test_dir)
    dummy_crop = np.zeros((100, 100, 3), dtype=np.uint8)

    row_id = db.log_event(
        track_id=10,
        direction="IN",
        gender="Male",
        gender_conf=0.95,
        estimated_age="(25-32)",
        frame_snapshot=dummy_crop
    )
    assert row_id == 1, "ID bản ghi đầu tiên phải là 1"

    summary = db.get_summary()
    assert summary["total_in"] == 1
    assert summary["male_count"] == 1
    assert summary["female_count"] == 0

    # Kiểm tra file snapshot có được tạo không
    assert os.path.exists(test_dir), "Thư mục captures phải tồn tại"
    files = os.listdir(test_dir)
    assert len(files) == 1, "Phải có 1 file ảnh snapshot được lưu"

    db.close()
    os.remove(test_db)
    shutil.rmtree(test_dir)
    print(" -> SQLite Database & Snapshot Logging: PASS!")


def test_visualizer_rendering():
    print("[Test 4] Kiểm tra Visualizer OSD Canvas...")
    vis = Visualizer()
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)

    canvas = vis.draw_hud(canvas, total_in=5, total_out=2, fps=30.0, is_cuda=True)
    canvas = vis.draw_counting_line(canvas, (200, 400), (1080, 400))

    assert canvas.shape == (720, 1280, 3)
    # Đảm bảo canvas không còn đen hoàn toàn
    assert np.mean(canvas) > 0, "Canvas phải có các chi tiết HUD và vạch được vẽ"

    print(" -> Visualizer Rendering: PASS!")


def test_vietnamese_labels_and_percent():
    print("[Test 5] Kiểm tra nhãn Tiếng Việt (Nam/Nữ) và tỷ lệ phần trăm (%) trên Bounding Box...")
    from src.demographics import DemographicsEstimator
    demo = DemographicsEstimator(
        face_model_path="models/face_detection_yunet_2023mar.onnx",
        gender_model_path="models/gender_googlenet.onnx"
    )
    demo._ensure_buffer(1)
    demo.buffers[1]['latest_gender'] = 'Nam'
    demo.buffers[1]['latest_gender_conf'] = 0.92

    demo._ensure_buffer(2)
    demo.buffers[2]['latest_gender'] = 'Nữ'
    demo.buffers[2]['latest_gender_conf'] = 0.88

    # Kiểm tra get_display_info
    g1, c1 = demo.get_display_info(1)
    assert g1 == "Nam" and c1 == 0.92, f"Kỳ vọng Nam 0.92, thực tế {g1} {c1}"

    g2, c2 = demo.get_display_info(2)
    assert g2 == "Nữ" and c2 == 0.88, f"Kỳ vọng Nữ 0.88, thực tế {g2} {c2}"

    # Kiểm tra Visualizer vẽ OSD có nhãn và %
    vis = Visualizer()
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    tracks = [
        {'track_id': 1, 'bbox': [100, 100, 200, 300]},
        {'track_id': 2, 'bbox': [400, 100, 500, 300]}
    ]
    canvas = vis.draw_tracks(canvas, tracks, demo, {}, {})
    assert canvas is not None and np.mean(canvas) > 0

    # Kiểm tra DatabaseManager với Nam và Nữ
    test_db = "test_vn_database.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    db = DatabaseManager(db_path=test_db, save_snapshots=False)
    db.log_event(track_id=1, direction="IN", gender="Nam", gender_conf=0.92)
    db.log_event(track_id=2, direction="OUT", gender="Nữ", gender_conf=0.88)
    db.log_event(track_id=3, direction="IN", gender="Male", gender_conf=0.85)  # Legacy record
    db.log_event(track_id=4, direction="OUT", gender="Female", gender_conf=0.90)  # Legacy record

    summary = db.get_summary()
    assert summary["male_count"] == 2, f"Kỳ vọng 2 Nam, thực tế: {summary['male_count']}"
    assert summary["female_count"] == 2, f"Kỳ vọng 2 Nữ, thực tế: {summary['female_count']}"
    db.close()
    if os.path.exists(test_db):
        os.remove(test_db)

    print(" -> Nhãn Nam/Nữ và Tỷ Lệ Phần Trăm (%): PASS!")


if __name__ == "__main__":
    print("=== CHẠY KIỂM THỬ ĐỘC LẬP CÁC MODULE CỐT LÕI ===")
    test_line_intersection_math()
    test_line_counter_logic()
    test_db_manager()
    test_visualizer_rendering()
    test_vietnamese_labels_and_percent()
    print("\n>>> TẤT CẢ CÁC KIỂM THỬ ĐƠN VỊ ĐỀU THÀNH CÔNG! <<<")
