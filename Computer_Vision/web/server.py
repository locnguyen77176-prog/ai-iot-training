import os
import sys
import time
import yaml
import sqlite3
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Union, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import cv2
import numpy as np
try:
    import torch
except ImportError:  # NCNN-only Raspberry Pi deployment
    torch = None
from fastapi import FastAPI, Request, HTTPException, Body, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from src.video_stream import (
    ThreadedVideoStream,
    is_live_video_source,
    normalize_video_source,
)
from src.tracker import YOLOTracker
from src.zone_counter import DualZoneCounter
from src.db_manager import DatabaseManager
from src.visualizer import Visualizer


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_VALUE = os.environ.get("VISIONFLOW_CONFIG", "config.yaml")
CONFIG_PATH = (
    _CONFIG_VALUE if os.path.isabs(_CONFIG_VALUE)
    else os.path.join(BASE_DIR, _CONFIG_VALUE)
)
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)


class AIEngineWorker:
    """
    Quản lý luồng xử lý AI (YOLO26n + FastTrack + OSNet bên ngoài) chạy ngầm độc lập với Web Server.
    Cung cấp frame mới nhất đã render OSD để stream ra trình duyệt qua MJPEG.
    """
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.cfg = self._load_config()

        self.db_manager = DatabaseManager(
            db_path=self.cfg.get("database", {}).get("db_path", DB_PATH)
        )

        src_cfg = self.cfg.get("source", {})
        self.source_path = normalize_video_source(src_cfg.get("path", ""))
        self.source_type = src_cfg.get("type", "file")
        print(f"[Config] Đã nạp: {self.config_path}")
        print(f"[Config] Nguồn video từ path: {self.source_path!r}")

        # Bỏ qua kiểm tra đường dẫn cục bộ nếu là luồng stream hoặc là ID của Webcam (0, 1, 2...)
        is_stream = is_live_video_source(self.source_path)

        if not is_stream:
            # Nếu đường dẫn tương đối, ghép với BASE_DIR
            if isinstance(self.source_path, str) and self.source_path and not os.path.isabs(self.source_path):
                self.source_path = os.path.join(BASE_DIR, self.source_path)

            # Nếu không tồn tại, tự động lấy video đầu tiên trong uploads/
            if not self.source_path or not os.path.exists(str(self.source_path)):
                if os.path.exists(UPLOADS_DIR):
                    for f in sorted(os.listdir(UPLOADS_DIR)):
                        if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                            self.source_path = os.path.join(UPLOADS_DIR, f)
                            break

        # Khởi tạo VideoStream (chờ WebApp kết nối)
        self.video_stream = ThreadedVideoStream(
            src=self.source_path,
            reconnect_interval=src_cfg.get("reconnect_interval", 3),
            width=src_cfg.get("width", 1280),
            height=src_cfg.get("height", 720),
            loop_video=True,
            excluded_camera_names=src_cfg.get("excluded_camera_names", []),
            open_timeout_ms=src_cfg.get("open_timeout_ms", 5000),
            read_timeout_ms=src_cfg.get("read_timeout_ms", 5000),
            connect_warmup_frames=src_cfg.get("connect_warmup_frames", 5),
            target_fps=src_cfg.get("target_fps", 15),
            flip_horizontal=src_cfg.get("flip_horizontal", False),
            anti_glare=src_cfg.get("anti_glare", {})
        )

        det_cfg = self.cfg.get("detector", {})
        backend = str(det_cfg.get("backend", "pytorch")).lower()
        self.tracker = YOLOTracker(
            model_path=os.path.join(BASE_DIR, det_cfg.get("model_path", "models/yolo26n.pt")),
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

        zone_cfg = self.cfg.get("zones", {})
        default_zone_a = [[220, 140], [1060, 140], [1060, 340], [220, 340]]
        default_zone_b = [[220, 400], [1060, 400], [1060, 600], [220, 600]]
        self.zone_counter = DualZoneCounter(
            zone_a=zone_cfg.get("zone_a", default_zone_a),
            zone_b=zone_cfg.get("zone_b", default_zone_b),
            in_label=zone_cfg.get("in_label", "IN"),
            out_label=zone_cfg.get("out_label", "OUT"),
            cooldown_seconds=zone_cfg.get("cooldown_seconds", 3.0),
            state_ttl_seconds=zone_cfg.get("state_ttl_seconds", 120.0),
            min_zone_hits=zone_cfg.get("min_zone_hits", 2)
        )
        self.visualizer = Visualizer(config_path=self.config_path)

        self.latest_encoded_frame = None
        self.frame_seq = 0
        self.new_frame_event = threading.Event()
        self.lock = threading.Lock()
        self.render_lock = threading.Lock()
        self.render_event = threading.Event()
        self.latest_render_packet = None
        self.render_seq = 0
        self.running = False
        self.fps = 0.0
        self.ai_fps = 0.0
        self.display_fps = 0.0
        self.is_cuda = (
            backend == "pytorch" and torch is not None and torch.cuda.is_available()
            and "cuda" in det_cfg.get("device", "cuda:0")
        )
        self.thread = None
        self.render_thread = None

    def _load_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def is_active(self) -> bool:
        """Kiểm tra camera và AI pipeline có đang chạy không"""
        return self.running and self.video_stream.is_connected

    def switch_source(self, new_src: Union[int, str], source_type: str = "webcam"):
        """Chuyển đổi nguồn đầu vào giữa Webcam máy tính và Video file tải lên, tự động bật camera"""
        with self.lock:
            self.source_path = new_src
            self.source_type = source_type
            self.zone_counter.reset_counts()
            self.tracker.reset()
            self.video_stream.change_source(new_src)
            self.latest_encoded_frame = None
            self.fps = 0.0
            self.ai_fps = 0.0
            self.display_fps = 0.0
            with self.render_lock:
                self.latest_render_packet = None
                self.render_seq += 1
            print(f"[AIEngineWorker] Đã chuyển đổi nguồn sang: {self.source_path} (loại: {self.source_type})")
        # Luôn đảm bảo camera và luồng AI được kích hoạt tự động
        self.start_camera()

    def start_camera(self):
        """Bật camera phần cứng và khởi động thread AI khi có yêu cầu từ WebApp"""
        with self.lock:
            if self.running and self.thread and self.thread.is_alive():
                # Nếu thread AI đang chạy nhưng video_stream chưa kết nối (do vừa chuyển nguồn)
                if self.video_stream.stopped or not self.video_stream.is_connected:
                    self.video_stream.start()
                if self.render_thread is None or not self.render_thread.is_alive():
                    self.render_thread = threading.Thread(target=self._render_loop, daemon=True)
                    self.render_thread.start()
                return
            print("[AIEngineWorker] Kích hoạt camera phần cứng và tiến trình AI pipeline...")
            self.video_stream.start()
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.render_thread = threading.Thread(target=self._render_loop, daemon=True)
            self.thread.start()
            self.render_thread.start()
            print("[AIEngineWorker] Camera và AI Pipeline đã bắt đầu hoạt động.")

    def stop_camera(self):
        """Tắt camera và giải phóng triệt để tài nguyên phần cứng (tắt đèn webcam)"""
        print("[AIEngineWorker] Dừng camera và giải phóng phần cứng...")
        self.running = False
        self.render_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        if self.render_thread and self.render_thread.is_alive():
            self.render_thread.join(timeout=1.5)
        self.thread = None
        self.render_thread = None
        self.video_stream.stop()
        with self.lock:
            self.latest_encoded_frame = None
            self.fps = 0.0
            self.ai_fps = 0.0
            self.display_fps = 0.0
        with self.render_lock:
            self.latest_render_packet = None
        self.new_frame_event.set()
        print("[AIEngineWorker] Đã tắt camera hoàn tất.")

    def _loop(self):
        ai_timestamps = deque(maxlen=90)
        pacing_source = None
        next_present_at = None
        last_capture_sequence = None
        last_capture_time = None
        while self.running:
            capture = self.video_stream.read_packet(last_capture_sequence)
            if capture is None:
                time.sleep(0.005)
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

            source_key = (str(self.source_path), bool(getattr(self.video_stream, "is_file", False)))
            if source_key != pacing_source:
                pacing_source = source_key
                next_present_at = None
                ai_timestamps.clear()
                frame_gap = 1
                delta_time = None

            # Khung hình đã được chuẩn hóa 1280x720 từ thread nền
            h_r, w_r = raw_frame.shape[:2]
            if w_r == 1280 and h_r == 720:
                frame = raw_frame
            else:
                frame = cv2.resize(raw_frame, (1280, 720), interpolation=cv2.INTER_LINEAR)

            # 1. Phát hiện và bám vết bằng FastTrack; OSNet nối stable ID bên ngoài.
            tracks = self.tracker.track(
                frame,
                frame_gap=frame_gap,
                delta_time=delta_time,
                nominal_fps=getattr(self.video_stream, "target_fps", 0.0),
            )

            # 2. Xử lý máy trạng thái FSM 2 Vùng Không Gian (Dual-Zone State Machine)
            events = self.zone_counter.update(tracks)
            for ev in events:
                track_id = ev['track_id']
                direction = ev['direction']

                self.db_manager.log_event(
                    track_id=track_id,
                    direction=direction,
                    gender="N/A",
                    gender_conf=0.0,
                    estimated_age="N/A"
                )

            # Video file vẫn phải đi đúng timeline; camera live luôn ưu tiên frame mới nhất.
            if getattr(self.video_stream, "is_file", False):
                frame_delay = max(0.001, float(getattr(self.video_stream, "frame_delay", 0.033)))
                now = time.perf_counter()
                if next_present_at is None:
                    next_present_at = now
                else:
                    next_present_at += frame_delay
                    if now - next_present_at > frame_delay * 2:
                        next_present_at = now
                wait_time = next_present_at - time.perf_counter()
                if wait_time > 0:
                    time.sleep(wait_time)

            # Rolling AI FPS over recent frames is steadier than independent 10-frame windows.
            now = time.perf_counter()
            if ai_timestamps and now - ai_timestamps[-1] > 1.0:
                ai_timestamps.clear()
            ai_timestamps.append(now)
            if len(ai_timestamps) >= 2:
                elapsed = ai_timestamps[-1] - ai_timestamps[0]
                ai_fps = (len(ai_timestamps) - 1) / elapsed if elapsed > 0 else 0.0
                with self.lock:
                    self.ai_fps = round(ai_fps, 1)
                    self.fps = self.ai_fps

            # Snapshot only immutable/copy data. Renderer may safely work on the previous result.
            packet = {
                "frame": frame,
                "tracks": [dict(track) for track in tracks],
                "zone_a": [list(point) for point in self.zone_counter.zone_a_pts],
                "zone_b": [list(point) for point in self.zone_counter.zone_b_pts],
                "in_label": self.zone_counter.in_label,
                "out_label": self.zone_counter.out_label,
                "track_history": {
                    track_id: list(points) for track_id, points in self.zone_counter.track_history.items()
                },
                "counted_tracks": {
                    track_id: dict(data) for track_id, data in self.zone_counter.counted_tracks.items()
                },
                "total_in": self.zone_counter.total_in,
                "total_out": self.zone_counter.total_out,
                "ai_fps": self.ai_fps,
            }
            with self.render_lock:
                self.latest_render_packet = packet
                self.render_seq += 1
            self.render_event.set()

    def _render_loop(self):
        """Render overlays and JPEG independently so browser work never blocks AI inference."""
        last_render_seq = -1
        display_timestamps = deque(maxlen=90)
        while self.running:
            if not self.render_event.wait(timeout=0.1):
                continue
            self.render_event.clear()
            with self.render_lock:
                packet = self.latest_render_packet
                render_seq = self.render_seq
            if packet is None or render_seq == last_render_seq:
                continue
            last_render_seq = render_seq

            frame = packet["frame"]
            self.visualizer.draw_zones(
                frame, packet["zone_a"], packet["zone_b"],
                packet["in_label"], packet["out_label"],
            )
            self.visualizer.draw_tracks(
                frame, packet["tracks"], packet["track_history"], packet["counted_tracks"],
            )
            self.visualizer.draw_hud(
                frame, packet["total_in"], packet["total_out"],
                packet["ai_fps"], is_cuda=self.is_cuda,
            )

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 68])
            if not ret:
                continue

            now = time.perf_counter()
            if display_timestamps and now - display_timestamps[-1] > 1.0:
                display_timestamps.clear()
            display_timestamps.append(now)
            display_fps = 0.0
            if len(display_timestamps) >= 2:
                elapsed = display_timestamps[-1] - display_timestamps[0]
                display_fps = (len(display_timestamps) - 1) / elapsed if elapsed > 0 else 0.0

            with self.lock:
                self.latest_encoded_frame = buffer.tobytes()
                self.frame_seq += 1
                self.display_fps = round(display_fps, 1)
            self.new_frame_event.set()

    def get_frame_synchronized(self, last_seq: int, timeout: float = 0.08) -> Tuple[Optional[bytes], int]:
        """Lấy frame mới nhất một cách đồng bộ, không gửi lại frame trùng lặp"""
        with self.lock:
            if self.frame_seq != last_seq and self.latest_encoded_frame is not None:
                return self.latest_encoded_frame, self.frame_seq

        if self.new_frame_event.wait(timeout=timeout):
            self.new_frame_event.clear()
            with self.lock:
                return self.latest_encoded_frame, self.frame_seq

        return None, last_seq

    def update_zones(self, zone_a: List[List[int]], zone_b: List[List[int]]):
        self.zone_counter.set_zones(zone_a, zone_b)
        self.visualizer._save_zones_to_config(zone_a, zone_b)

    def stop(self):
        self.stop_camera()
        self.db_manager.close()


def create_standby_frame() -> bytes:
    """Tạo frame chờ độ nét cao khi Camera đang TẮT (tiết kiệm CPU & hiển thị đẹp mắt)"""
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (18, 15, 23)  # Màu nền slate-dark #170f12 (BGR)

    # Box trung tâm bo viền
    cv2.rectangle(img, (320, 200), (960, 520), (33, 27, 41), -1)
    cv2.rectangle(img, (320, 200), (960, 520), (75, 60, 95), 2)

    # Chấm tròn cảnh báo camera tắt
    cv2.circle(img, (640, 260), 28, (45, 30, 45), -1)
    cv2.circle(img, (640, 260), 28, (68, 68, 239), 3) # Đỏ
    cv2.circle(img, (640, 260), 10, (68, 68, 239), -1)

    # Tiêu đề
    cv2.putText(img, "CAMERA DANG O CHE DO TAT", (460, 330),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (241, 245, 249), 2, cv2.LINE_AA)
    
    cv2.putText(img, "Phan cung Webcam da duoc giai phong hoan toan", (410, 375),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (148, 163, 184), 1, cv2.LINE_AA)
    cv2.putText(img, "(Den camera tren may tinh da tat de bao ve quyen rieng tu)", (360, 405),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 116, 139), 1, cv2.LINE_AA)

    # Nút bấm hướng dẫn
    cv2.rectangle(img, (460, 440), (820, 485), (16, 185, 129), -1)
    cv2.putText(img, "BAM 'BAT CAMERA' DE MO", (485, 470),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)

    ret, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ret else b''


STANDBY_FRAME_BYTES = create_standby_frame()


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """Run camera/AI with the server, independently from browser sessions."""
    global ai_worker, is_camera_requested
    with camera_lock:
        worker = get_ai_worker()
        if worker.cfg.get("source", {}).get("always_on", True):
            is_camera_requested = True
            worker.start_camera()
            print("[Server] Camera/AI đã tự khởi động và hoạt động độc lập với trình duyệt.")

    try:
        yield
    finally:
        with camera_lock:
            is_camera_requested = False
            if ai_worker is not None:
                ai_worker.stop()
                ai_worker = None


# Khởi tạo Web Server
app = FastAPI(
    title="VisionFlow AI People Counting System",
    version="1.0.0",
    lifespan=app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# Đảm bảo bảng SQLite và các cột (migration) sẵn sàng ngay khi server khởi động
try:
    DatabaseManager(db_path=DB_PATH)
except Exception as e:
    print(f"[Server] Cảnh báo khởi tạo database: {e}")

# Quản lý singleton AI Engine
ai_worker: Optional[AIEngineWorker] = None
camera_lock = threading.Lock()
is_camera_requested: bool = False


def get_ai_worker(auto_create: bool = True) -> Optional[AIEngineWorker]:
    global ai_worker
    if ai_worker is None and auto_create:
        ai_worker = AIEngineWorker(CONFIG_PATH)
    return ai_worker


@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Render trang chủ Dashboard"""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/video_feed")
def video_feed():
    """Luồng video MJPEG siêu mượt: Đồng bộ theo từng frame kết xuất, triệt tiêu frame trùng lặp"""
    def generate():
        last_seq = -1
        while True:
            global ai_worker
            if ai_worker is not None and ai_worker.is_active():
                frame_bytes, last_seq = ai_worker.get_frame_synchronized(last_seq, timeout=0.08)
                if frame_bytes is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    continue
            else:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + STANDBY_FRAME_BYTES + b'\r\n')
                time.sleep(0.4)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/camera/status")
def get_camera_status():
    """Lấy trạng thái hoạt động thực tế của camera và nguồn đầu vào"""
    global ai_worker, is_camera_requested
    active = ai_worker is not None and ai_worker.is_active()
    fps = ai_worker.fps if active else 0.0

    source_type = "file"
    source_name = "Tệp Video"
    source_val = ""

    if ai_worker is not None:
        source_type = getattr(ai_worker, "source_type", "file")
        source_val = str(ai_worker.source_path)
        source_name = os.path.basename(source_val) if source_val else "Tệp Video"

    return {
        "is_active": active,
        "is_requested": is_camera_requested,
        "fps": fps,
        "ai_fps": ai_worker.ai_fps if active else 0.0,
        "display_fps": ai_worker.display_fps if active else 0.0,
        "source": source_val,
        "source_type": source_type,
        "source_name": source_name,
        "backend": ai_worker.tracker.backend_name if ai_worker is not None else "not_initialized",
        "cuda_available": bool(torch is not None and torch.cuda.is_available())
    }


@app.post("/api/upload_video")
async def upload_video(file: UploadFile = File(...)):
    """Tải lên file video để chạy kiểm thử mô hình AI"""
    valid_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail=f"Định dạng video không hỗ trợ ({ext}). Vui lòng tải .mp4, .avi, .mkv, .mov.")

    clean_name = os.path.basename(file.filename)
    save_path = os.path.join(UPLOADS_DIR, clean_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    print(f"[Upload] Đã lưu video kiểm thử: {save_path} ({len(content)} bytes)")

    # Tự động kích hoạt AI engine và chuyển sang video vừa upload
    global is_camera_requested
    with camera_lock:
        is_camera_requested = True
        worker = get_ai_worker()
        worker.switch_source(save_path, source_type="file")

    return {
        "status": "success",
        "filename": clean_name,
        "path": save_path,
        "source_type": "file",
        "message": f"Đã tải lên và bắt đầu kiểm thử với video: {clean_name}"
    }


@app.post("/api/set_source")
def set_source(data: dict = Body(...)):
    """Chuyển đổi nguồn giữa Webcam máy tính và Video file đã tải lên"""
    source_type = data.get("source_type", "webcam")
    worker = get_ai_worker()

    global is_camera_requested
    with camera_lock:
        if source_type == "webcam":
            is_camera_requested = True
            cfg_path = worker.cfg.get("source", {}).get("path", 0)
            worker.switch_source(cfg_path, source_type="webcam")
            return {
                "status": "success",
                "source_type": "webcam",
                "source_path": cfg_path,
                "source_name": f"Camera ({cfg_path})",
                "is_active": True,
                "message": f"Đã bật nguồn Camera: {cfg_path}"
            }
        elif source_type == "file":
            filename = data.get("filename")
            if not filename:
                raise HTTPException(status_code=400, detail="Thiếu tên file video kiểm thử")
            filepath = os.path.join(UPLOADS_DIR, filename)
            if not os.path.exists(filepath):
                raise HTTPException(status_code=404, detail=f"Không tìm thấy file: {filename}")

            is_camera_requested = True
            worker.switch_source(filepath, source_type="file")

            return {
                "status": "success",
                "source_type": "file",
                "filename": filename,
                "source_name": filename,
                "message": f"Đã chuyển sang video kiểm thử: {filename}"
            }
        else:
            raise HTTPException(status_code=400, detail="source_type không hợp lệ (hỗ trợ 'webcam' hoặc 'file')")


@app.get("/api/videos")
def list_uploaded_videos():
    """Liệt kê danh sách các file video kiểm thử đã có trong thư mục uploads/"""
    videos = []
    if os.path.exists(UPLOADS_DIR):
        for fname in sorted(os.listdir(UPLOADS_DIR)):
            fpath = os.path.join(UPLOADS_DIR, fname)
            if os.path.isfile(fpath):
                ext = os.path.splitext(fname)[1].lower()
                if ext in {".mp4", ".avi", ".mkv", ".mov", ".wmv"}:
                    size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2)
                    videos.append({
                        "filename": fname,
                        "size_mb": size_mb
                    })

    worker = get_ai_worker(auto_create=False)
    current_source = worker.source_path if worker else 0
    current_type = getattr(worker, "source_type", "webcam") if worker else "webcam"

    return {
        "videos": videos,
        "current_source": str(current_source),
        "current_type": current_type
    }


@app.post("/api/camera/start")
def start_camera():
    """WebApp yêu cầu bật camera để tiến hành giám sát AI"""
    global is_camera_requested
    with camera_lock:
        is_camera_requested = True
        worker = get_ai_worker()
        worker.start_camera()
    return {"status": "success", "message": "Camera đã được bật thành công", "is_active": True}


@app.post("/api/camera/stop")
def stop_camera():
    """WebApp yêu cầu tắt camera và giải phóng phần cứng (tắt đèn webcam)"""
    global is_camera_requested, ai_worker
    with camera_lock:
        is_camera_requested = False
        if ai_worker is not None:
            ai_worker.stop_camera()
    return {"status": "success", "message": "Camera đã được tắt và giải phóng phần cứng", "is_active": False}


@app.post("/api/camera/heartbeat")
def camera_heartbeat():
    """Return capture status for the open WebApp tab."""
    active = ai_worker is not None and ai_worker.is_active()
    return {"status": "ok", "is_active": active}


@app.get("/api/stats")
def get_stats():
    """Trả về các số liệu thống kê thời gian thực từ SQLite mà KHÔNG ép bật camera"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Thống kê theo ngày hôm nay
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Tổng IN và OUT trong ngày hôm nay (Reset lúc 00:00)
    cursor.execute("SELECT COUNT(*) FROM people_counts WHERE direction = 'IN' AND date(timestamp) = date(?)", (today_str,))
    total_in = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM people_counts WHERE direction = 'OUT' AND date(timestamp) = date(?)", (today_str,))
    total_out = cursor.fetchone()[0]

    current_occupancy = max(0, total_in - total_out)

    # Thống kê theo giờ hôm nay (24h)
    cursor.execute("""
        SELECT strftime('%H', timestamp) as hr, direction, COUNT(*)
        FROM people_counts
        WHERE date(timestamp) = date(?)
        GROUP BY hr, direction
    """, (today_str,))
    hourly_raw = cursor.fetchall()

    hourly_in = [0] * 24
    hourly_out = [0] * 24
    for hr, direction, count in hourly_raw:
        if hr is not None:
            idx = int(hr)
            if direction == "IN":
                hourly_in[idx] = count
            else:
                hourly_out[idx] = count

    conn.close()

    cuda_available = bool(torch is not None and torch.cuda.is_available())
    gpu_name = torch.cuda.get_device_name(0) if cuda_available else "CPU/NCNN"

    return {
        "total_in": total_in,
        "total_out": total_out,
        "current_occupancy": current_occupancy,
        "total_traffic": total_in + total_out,
        "in_percentage": "+20.2%",
        "out_percentage": "+15.7%",
        "occupancy_trend": "-32.4%",
        "hourly_traffic": {
            "hours": [f"{h:02d}:00" for h in range(24)],
            "in": hourly_in,
            "out": hourly_out
        },
        "system": {
            "fps": ai_worker.fps if (ai_worker is not None and ai_worker.is_active()) else 0.0,
            "ai_fps": ai_worker.ai_fps if (ai_worker is not None and ai_worker.is_active()) else 0.0,
            "display_fps": ai_worker.display_fps if (ai_worker is not None and ai_worker.is_active()) else 0.0,
            "gpu": gpu_name,
            "backend": ai_worker.tracker.backend_name if ai_worker is not None else "not_initialized",
            "cuda_available": cuda_available,
            "camera_connected": (ai_worker is not None and ai_worker.is_active())
        }
    }


@app.get("/api/events")
def get_events(limit: int = 50, direction: str = "all"):
    """Lấy danh sách các sự kiện người cắt qua vạch"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, timestamp, track_id, direction FROM people_counts"
    conditions = []
    params = []

    if direction in ["IN", "OUT"]:
        conditions.append("direction = ?")
        params.append(direction)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append({
            "id": r[0],
            "timestamp": r[1],
            "track_id": r[2],
            "direction": r[3]
        })

    return {"events": events}


@app.get("/api/zones")
def get_zones():
    """Lấy tọa độ 2 vùng đếm không gian hiện tại"""
    worker = get_ai_worker()
    return worker.zone_counter.get_zones()


@app.post("/api/zones")
def update_zones(data: dict = Body(...)):
    """Cập nhật tọa độ 2 vùng không gian"""
    worker = get_ai_worker()
    z_a = data.get("zone_a")
    z_b = data.get("zone_b")
    if not z_a or not z_b or len(z_a) < 3 or len(z_b) < 3:
        raise HTTPException(status_code=400, detail="Tọa độ Vùng A và Vùng B không hợp lệ (tối thiểu 3 điểm)")

    worker.update_zones(z_a, z_b)
    return {"status": "success", "zone_a": z_a, "zone_b": z_b}


@app.post("/api/reset_counts")
def reset_counts():
    """Reset bộ đếm tạm thời"""
    worker = get_ai_worker()
    worker.zone_counter.reset_counts()
    return {"status": "success"}


@app.get("/api/export/excel")
@app.get("/api/export/csv")
def export_excel():
    """Xuất toàn bộ báo cáo lưu lượng và phân tích theo giờ ra file Excel (.xlsx) chuẩn thương mại"""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import BarChart, Reference

    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    cursor = conn.cursor()

    # 1. Lấy dữ liệu tổng quan
    cursor.execute("SELECT COUNT(*) FROM people_counts WHERE direction = 'IN'")
    total_in = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM people_counts WHERE direction = 'OUT'")
    total_out = cursor.fetchone()[0] or 0

    total_traffic = total_in + total_out
    current_occupancy = max(0, total_in - total_out)

    # 2. Thống kê theo 24 khung giờ
    cursor.execute("""
        SELECT strftime('%H', timestamp) as hr, direction, COUNT(*)
        FROM people_counts
        GROUP BY hr, direction
    """)
    hourly_raw = cursor.fetchall()

    hourly_in = [0] * 24
    hourly_out = [0] * 24
    for hr, direction, count in hourly_raw:
        if hr is not None:
            idx = int(hr)
            if 0 <= idx < 24:
                if direction == "IN":
                    hourly_in[idx] = count
                else:
                    hourly_out[idx] = count

    # Tính lưu lượng và hiện diện tích lũy từng giờ
    hourly_traffic = [hourly_in[i] + hourly_out[i] for i in range(24)]

    cumulative_occ = 0
    hourly_occupancy = []
    for i in range(24):
        cumulative_occ += (hourly_in[i] - hourly_out[i])
        hourly_occupancy.append(max(0, cumulative_occ))

    # Tìm khung giờ lưu lượng lớn nhất và bé nhất
    max_traffic_val = max(hourly_traffic) if hourly_traffic else 0
    max_hours = [i for i, v in enumerate(hourly_traffic) if v == max_traffic_val] if max_traffic_val > 0 else []

    min_traffic_val = min(hourly_traffic) if hourly_traffic else 0
    min_hours = [i for i, v in enumerate(hourly_traffic) if v == min_traffic_val]

    if max_hours:
        max_hour_str = ", ".join([f"{h:02d}:00 - {h:02d}:59" for h in max_hours])
        max_hour_detail = f"{max_hour_str} ({max_traffic_val} lượt)"
    else:
        max_hour_detail = "Chưa ghi nhận lưu lượng"

    if min_hours and len(min_hours) < 24:
        min_hour_str = ", ".join([f"{h:02d}:00 - {h:02d}:59" for h in min_hours[:4]])
        if len(min_hours) > 4:
            min_hour_str += f" (+{len(min_hours)-4} khung giờ khác)"
        min_hour_detail = f"{min_hour_str} ({min_traffic_val} lượt)"
    elif min_hours:
        min_hour_detail = f"Tất cả các khung giờ đều đạt {min_traffic_val} lượt"
    else:
        min_hour_detail = "Chưa có dữ liệu"

    # 3. Lấy toàn bộ danh sách chi tiết (Raw Log)
    cursor.execute("SELECT id, timestamp, track_id, direction FROM people_counts ORDER BY id ASC")
    raw_rows = cursor.fetchall()
    conn.close()

    # ================= KHỞI TẠO WORKBOOK EXCEL =================
    wb = openpyxl.Workbook()

    # Định nghĩa màu sắc & Font chuẩn
    font_title = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
    font_sub = Font(name="Segoe UI", size=9, italic=True, color="64748B")
    font_section = Font(name="Segoe UI", size=11, bold=True, color="0F172A")
    font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Segoe UI", size=10, bold=True)
    font_regular = Font(name="Segoe UI", size=10)
    font_kpi_val = Font(name="Segoe UI", size=13, bold=True, color="1E293B")

    fill_header_navy = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    fill_header_blue = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    fill_kpi_in = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    fill_kpi_out = PatternFill(start_color="FFE4E6", end_color="FFE4E6", fill_type="solid")
    fill_kpi_total = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
    fill_kpi_occ = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    fill_stripe = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    thin_border_side = Side(border_style="thin", color="CBD5E1")
    cell_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    # ------------------ SHEET 1: TỔNG HỢP & LƯU LƯỢNG ------------------
    ws1 = wb.active
    ws1.title = "Báo Cáo Lưu Lượng"
    ws1.views.sheetView[0].showGridLines = True

    # Tiêu đề
    ws1.merge_cells("A1:E1")
    ws1["A1"] = "BÁO CÁO THỐNG KÊ LƯU LƯỢNG NGƯỜI RA VÀO (SMARTGATE AI)"
    ws1["A1"].font = font_title
    ws1["A1"].alignment = align_left

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ws1.merge_cells("A2:E2")
    ws1["A2"] = f"Thời gian trích xuất: {now_str} | Trạm giám sát: Cổng Chính #01 | Hệ thống: VisionFlow AI Tracker"
    ws1["A2"].font = font_sub
    ws1["A2"].alignment = align_left

    # BẢNG 1: TỔNG QUAN CHỈ SỐ KPI
    ws1["A4"] = "1. CHỈ SỐ TỔNG QUAN LƯU LƯỢNG"
    ws1["A4"].font = font_section

    kpi_headers = ["Tổng Lượt Vào (IN)", "Tổng Lượt Ra (OUT)", "Tổng Lưu Lượng (IN + OUT)", "Hiện Diện Tức Thời (Occupancy)"]
    kpi_vals = [total_in, total_out, total_traffic, current_occupancy]
    kpi_fills = [fill_kpi_in, fill_kpi_out, fill_kpi_total, fill_kpi_occ]

    for col_idx, (h_txt, val, fill_color) in enumerate(zip(kpi_headers, kpi_vals, kpi_fills), start=1):
        c_head = ws1.cell(row=5, column=col_idx, value=h_txt)
        c_head.font = Font(name="Segoe UI", size=9, bold=True, color="334155")
        c_head.alignment = align_center
        c_head.fill = fill_color
        c_head.border = cell_border

        c_val = ws1.cell(row=6, column=col_idx, value=val)
        c_val.font = font_kpi_val
        c_val.alignment = align_center
        c_val.fill = fill_color
        c_val.border = cell_border
        c_val.number_format = "#,##0"

    # BẢNG 2: PHÂN TÍCH KHUNG GIỜ CAO ĐIỂM / THẤP ĐIỂM
    ws1["A8"] = "2. PHÂN TÍCH KHUNG GIỜ CAO ĐIỂM & THẤP ĐIỂM"
    ws1["A8"].font = font_section

    ws1["A9"] = "Khung giờ lưu lượng LỚN NHẤT (Peak):"
    ws1["A9"].font = font_bold
    ws1.merge_cells("B9:E9")
    ws1["B9"] = max_hour_detail
    ws1["B9"].font = Font(name="Segoe UI", size=10, bold=True, color="059669")

    ws1["A10"] = "Khung giờ lưu lượng BÉ NHẤT (Min):"
    ws1["A10"].font = font_bold
    ws1.merge_cells("B10:E10")
    ws1["B10"] = min_hour_detail
    ws1["B10"].font = Font(name="Segoe UI", size=10, italic=True, color="475569")

    # BẢNG 3: BẢNG CHI TIẾT 24 KHUNG GIỜ
    ws1["A12"] = "3. BẢNG THỐNG KÊ CHI TIẾT TỪNG KHUNG GIỜ (24H)"
    ws1["A12"].font = font_section

    table_headers = ["Khung Giờ", "Lượt Vào (IN)", "Lượt Ra (OUT)", "Hiện Diện (Occupancy)", "Tổng Lưu Lượng"]
    for col_idx, h_txt in enumerate(table_headers, start=1):
        cell = ws1.cell(row=13, column=col_idx, value=h_txt)
        cell.font = font_header
        cell.fill = fill_header_navy
        cell.alignment = align_center
        cell.border = cell_border

    start_row = 14
    for i in range(24):
        curr_row = start_row + i
        slot_label = f"{i:02d}:00 - {i:02d}:59"
        v_in = hourly_in[i]
        v_out = hourly_out[i]
        v_occ = hourly_occupancy[i]
        v_traffic = hourly_traffic[i]

        row_data = [slot_label, v_in, v_out, v_occ, v_traffic]
        row_fill = fill_stripe if (i % 2 == 1) else None

        for col_idx, val in enumerate(row_data, start=1):
            c = ws1.cell(row=curr_row, column=col_idx, value=val)
            c.font = font_regular
            c.border = cell_border
            if row_fill:
                c.fill = row_fill
            if col_idx == 1:
                c.alignment = align_center
            else:
                c.alignment = align_right
                c.number_format = "#,##0"

    # Dòng Tổng Cộng cuối bảng
    total_row = start_row + 24
    ws1.cell(row=total_row, column=1, value="TỔNG CỘNG").font = font_header
    ws1.cell(row=total_row, column=1).alignment = align_center
    ws1.cell(row=total_row, column=1).fill = fill_header_blue
    ws1.cell(row=total_row, column=1).border = cell_border

    ws1.cell(row=total_row, column=2, value=f"=SUM(B{start_row}:B{total_row-1})").font = font_header
    ws1.cell(row=total_row, column=2).alignment = align_right
    ws1.cell(row=total_row, column=2).fill = fill_header_blue
    ws1.cell(row=total_row, column=2).border = cell_border

    ws1.cell(row=total_row, column=3, value=f"=SUM(C{start_row}:C{total_row-1})").font = font_header
    ws1.cell(row=total_row, column=3).alignment = align_right
    ws1.cell(row=total_row, column=3).fill = fill_header_blue
    ws1.cell(row=total_row, column=3).border = cell_border

    ws1.cell(row=total_row, column=4, value=current_occupancy).font = font_header
    ws1.cell(row=total_row, column=4).alignment = align_right
    ws1.cell(row=total_row, column=4).fill = fill_header_blue
    ws1.cell(row=total_row, column=4).border = cell_border

    ws1.cell(row=total_row, column=5, value=f"=SUM(E{start_row}:E{total_row-1})").font = font_header
    ws1.cell(row=total_row, column=5).alignment = align_right
    ws1.cell(row=total_row, column=5).fill = fill_header_blue
    ws1.cell(row=total_row, column=5).border = cell_border

    # TỰ ĐỘNG CHÈN BIỂU ĐỒ CỘT NATIVE EXCEL CHART
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = "Biểu Đồ Lưu Lượng Vào / Ra Theo Khung Giờ (24h)"
    chart.y_axis.title = "Số Lượng Người"
    chart.x_axis.title = "Khung Giờ"
    chart.width = 18
    chart.height = 12

    data_ref = Reference(ws1, min_col=2, min_row=13, max_col=3, max_row=total_row-1)
    cats_ref = Reference(ws1, min_col=1, min_row=14, max_row=total_row-1)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    chart.legend.legendPos = "tr"
    ws1.add_chart(chart, "G4")

    # Tự căn chỉnh độ rộng cột Sheet 1
    col_widths_1 = {"A": 22, "B": 18, "C": 18, "D": 24, "E": 20}
    for col_l, w in col_widths_1.items():
        ws1.column_dimensions[col_l].width = w

    # ------------------ SHEET 2: NHẬT KÝ CHI TIẾT (RAW AUDIT LOG) ------------------
    ws2 = wb.create_sheet(title="Nhật Ký Chi Tiết")
    ws2.views.sheetView[0].showGridLines = True

    ws2["A1"] = "NHẬT KÝ LỊCH SỬ NGƯỜI RA VÀO TỪNG LƯỢT"
    ws2["A1"].font = font_title
    ws2["A2"] = f"Tổng số bản ghi: {len(raw_rows)} sự kiện | Trích xuất từ SQLite Database"
    ws2["A2"].font = font_sub

    raw_headers = ["STT", "Thời Gian Ghi Nhận", "Mã Đối Tượng (Track ID)", "Hướng Di Chuyển", "Trạng Thái"]
    for col_idx, h_txt in enumerate(raw_headers, start=1):
        cell = ws2.cell(row=4, column=col_idx, value=h_txt)
        cell.font = font_header
        cell.fill = fill_header_navy
        cell.alignment = align_center
        cell.border = cell_border

    for r_idx, r in enumerate(raw_rows, start=5):
        dir_text = "VÀO (IN)" if r[3] == "IN" else "RA (OUT)"
        dir_color = "059669" if r[3] == "IN" else "E11D48"
        dir_fill = fill_kpi_in if r[3] == "IN" else fill_kpi_out

        c_stt = ws2.cell(row=r_idx, column=1, value=r_idx-4)
        c_time = ws2.cell(row=r_idx, column=2, value=r[1])
        c_id = ws2.cell(row=r_idx, column=3, value=f"ID #{r[2]}")
        c_dir = ws2.cell(row=r_idx, column=4, value=dir_text)
        c_status = ws2.cell(row=r_idx, column=5, value="Đã Xác Thực")

        c_stt.alignment = align_center
        c_time.alignment = align_center
        c_id.alignment = align_center
        c_dir.alignment = align_center
        c_status.alignment = align_center

        c_dir.font = Font(name="Segoe UI", size=10, bold=True, color=dir_color)
        c_dir.fill = dir_fill

        for c in [c_stt, c_time, c_id, c_dir, c_status]:
            c.border = cell_border

    col_widths_2 = {"A": 10, "B": 24, "C": 26, "D": 20, "E": 18}
    for col_l, w in col_widths_2.items():
        ws2.column_dimensions[col_l].width = w

    # ================= LƯU VÀO STREAMING RESPONSE =================
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"Bao_Cao_Luu_Luong_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/clear_history")
def clear_history():
    """Xóa toàn bộ lịch sử trong database để bắt đầu chu kỳ đếm mới."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM people_counts")
    conn.commit()
    conn.close()

    worker = get_ai_worker()
    worker.zone_counter.reset_counts()
    return {"status": "success", "message": "Đã xóa toàn bộ lịch sử!"}
