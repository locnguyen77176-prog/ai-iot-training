import queue
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


VideoSource = Union[int, str]
AUTO_USB_SOURCE = "auto_usb"
NETWORK_PREFIXES = ("rtsp://", "http://", "https://")
VIRTUAL_OR_INTERNAL_MARKERS = (
    "integrated", "built-in", "user facing", "front facing",
    "virtual", "obs", "nvidia broadcast", "lsvcam",
)


@dataclass(frozen=True)

class FramePacket:
    """A unique captured frame plus timing metadata for real-time tracking."""

    frame: cv2.Mat
    sequence: int
    captured_at: float


def normalize_video_source(source: VideoSource) -> VideoSource:
    """Convert a numeric YAML/CLI string to an exact camera index."""
    if isinstance(source, str):
        source = source.strip()
        if source.isdigit():
            return int(source)
    return source


def is_network_source(source: VideoSource) -> bool:
    return isinstance(source, str) and source.casefold().startswith(NETWORK_PREFIXES)


def is_live_video_source(source: VideoSource) -> bool:
    source = normalize_video_source(source)
    return (
        isinstance(source, int)
        or is_network_source(source)
        or (isinstance(source, str) and source.casefold() == AUTO_USB_SOURCE)
    )


class ThreadedVideoStream:
    """
    Luồng đọc video nền (Background Daemon Thread) chuyên dụng cho Webcam, RTSP và Video.
    - Triệt tiêu hoàn toàn hiện tượng trễ/lag buffer camera bằng cách chỉ lưu trữ frame mới nhất.
    - Tự động phát hiện mất tín hiệu và thử kết nối lại (Auto-reconnect).
    - Đo đạc tốc độ khung hình (FPS) nguồn thực tế.
    """
    def __init__(self, src: VideoSource = 0, reconnect_interval: int = 3,
                 width: Optional[int] = None, height: Optional[int] = None,
                 loop_video: bool = True,
                 excluded_camera_names: Optional[Sequence[str]] = None,
                 open_timeout_ms: int = 5000,
                 read_timeout_ms: int = 5000,
                 connect_warmup_frames: int = 5,
                 target_fps: Optional[float] = None,
                 flip_horizontal: bool = False,
                 anti_glare: Optional[Mapping[str, Any]] = None):
        self.src = normalize_video_source(src)
        self.excluded_camera_names = list(excluded_camera_names or [])
        self.active_src = self.src
        self.reconnect_interval = reconnect_interval
        self.width = width
        self.height = height
        self.loop_video = loop_video
        self.open_timeout_ms = max(1000, int(open_timeout_ms))
        self.read_timeout_ms = max(1000, int(read_timeout_ms))
        self.connect_warmup_frames = max(1, int(connect_warmup_frames))
        requested_fps = 0.0 if target_fps is None else float(target_fps)
        self.target_fps = requested_fps if requested_fps > 0 else 0.0
        self.flip_horizontal = bool(flip_horizontal)

        glare_cfg = dict(anti_glare or {})
        self.anti_glare_enabled = bool(glare_cfg.get("enabled", False))
        self.anti_glare_auto = bool(glare_cfg.get("auto", True))
        self.glare_threshold = int(np.clip(glare_cfg.get("threshold", 210), 128, 250))
        self.glare_min_bright_ratio = float(np.clip(
            glare_cfg.get("min_bright_ratio", 0.04), 0.0, 1.0
        ))
        self.glare_local_contrast = float(np.clip(
            glare_cfg.get("local_contrast_strength", 0.55), 0.0, 1.0
        ))
        highlight_compression = float(np.clip(
            glare_cfg.get("highlight_compression", 0.60), 0.0, 0.95
        ))
        grid_size = max(2, int(glare_cfg.get("clahe_grid_size", 8)))
        clip_limit = max(0.5, float(glare_cfg.get("clahe_clip_limit", 2.0)))
        self._glare_clahe = cv2.createCLAHE(
            clipLimit=clip_limit,
            tileGridSize=(grid_size, grid_size),
        )
        values = np.arange(256, dtype=np.float32)
        highlights = values > self.glare_threshold
        values[highlights] = self.glare_threshold + (
            values[highlights] - self.glare_threshold
        ) * (1.0 - highlight_compression)
        self._glare_lut = np.clip(values, 0, 255).astype(np.uint8)

        self.cap = None
        self.frame = None
        self.frame_sequence = 0
        self.frame_captured_at = 0.0
        self._next_live_publish_at = 0.0
        self.grabbed = False
        self.stopped = True
        self.is_connected = False

        self.lock = threading.Lock()
        # Khóa riêng cho VideoCapture: không release/reopen trong lúc thread đang read().
        self.capture_lock = threading.RLock()
        self.frame_queue = queue.Queue(maxsize=3)
        self.fps = 0.0
        self._fps_count = 0
        self._fps_start_time = time.time()
        self.thread = None
        self._stop_event = threading.Event()

        self.is_file = self._check_if_file(self.src)
        self.file_fps = 30.0
        self.frame_delay = 0.033

    @staticmethod
    def _check_if_file(src: VideoSource) -> bool:
        if isinstance(src, int):
            return False
        if isinstance(src, str):
            normalized = src.casefold()
            if normalized == AUTO_USB_SOURCE:
                return False
            if is_network_source(src):
                return False
            return True
        return False

    @staticmethod
    def _is_usb_source(src: VideoSource) -> bool:
        return isinstance(src, int) or (
            isinstance(src, str) and src.casefold() == AUTO_USB_SOURCE
        )

    def _resolve_camera_source(self) -> Optional[VideoSource]:
        """Select the first physical external camera and reject built-in/virtual cameras."""
        if not (isinstance(self.src, str) and self.src.casefold() == AUTO_USB_SOURCE):
            return self.src

        if platform.system() != "Windows":
            print("[VideoStream] auto_usb trên hệ điều hành này dùng camera index 0.")
            return 0

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("[VideoStream] Không tìm thấy FFmpeg nên không thể xác định camera USB an toàn.")
            return None

        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=6,
                creationflags=flags,
                check=False,
            )
            camera_names = re.findall(r'"([^"]+)"\s+\((?:video|none)\)', result.stdout)
            excluded = [name.casefold() for name in self.excluded_camera_names]
            for index, name in enumerate(camera_names):
                normalized = name.casefold()
                is_excluded = any(item in normalized for item in excluded)
                is_internal_or_virtual = any(
                    marker in normalized for marker in VIRTUAL_OR_INTERNAL_MARKERS
                )
                if not is_excluded and not is_internal_or_virtual:
                    print(f'[VideoStream] Đã chọn camera USB "{name}" tại index {index}.')
                    return index
                print(f'[VideoStream] Bỏ qua camera tích hợp/ảo "{name}".')
            print("[VideoStream] Không tìm thấy camera USB vật lý; webcam tích hợp sẽ không được mở.")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[VideoStream] Không thể dò camera USB ({exc}); webcam tích hợp sẽ không được mở.")
        return None

    def _release_capture(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except cv2.error:
                pass
            self.cap = None

    def _prepare_frame(self, frame: cv2.Mat) -> cv2.Mat:
        """Normalize resolution and apply the configured camera orientation."""
        height, width = frame.shape[:2]
        if width != 1280 or height != 720:
            frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
        if self.flip_horizontal:
            frame = cv2.flip(frame, 1)
        if self.anti_glare_enabled:
            frame = self._reduce_glare(frame)
        return frame

    def _reduce_glare(self, frame: cv2.Mat) -> cv2.Mat:
        """Compress harsh highlights and restore local luminance contrast."""
        if self.anti_glare_auto:
            sample = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            bright_mask = cv2.compare(gray, self.glare_threshold, cv2.CMP_GE)
            bright_ratio = cv2.countNonZero(bright_mask) / float(gray.size)
            if bright_ratio < self.glare_min_bright_ratio:
                return frame

        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        luminance, channel_a, channel_b = cv2.split(lab)
        local_luminance = self._glare_clahe.apply(luminance)
        luminance = cv2.addWeighted(
            luminance,
            1.0 - self.glare_local_contrast,
            local_luminance,
            self.glare_local_contrast,
            0,
        )
        luminance = cv2.LUT(luminance, self._glare_lut)
        corrected_lab = cv2.merge((luminance, channel_a, channel_b))
        return cv2.cvtColor(corrected_lab, cv2.COLOR_LAB2BGR)

    def _read_warmup_frame(self) -> Tuple[bool, Optional[cv2.Mat]]:
        """Allow a newly opened USB camera a few frames to become ready."""
        for _ in range(self.connect_warmup_frames):
            if self.cap is None or not self.cap.isOpened():
                break
            grabbed, frame = self.cap.read()
            if grabbed and frame is not None:
                return True, frame
            time.sleep(0.08)
        return False, None

    def _open_network_or_file(self):
        params = []
        if not self.is_file:
            params = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_ms,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_ms,
            ]
        try:
            self.cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG, params)
        except (TypeError, cv2.error):
            # Older OpenCV builds do not accept constructor parameters.
            self.cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG)
        if self.cap is not None and self.cap.isOpened() and not self.is_file:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _open_usb_camera(self, camera_index: int) -> Tuple[bool, Optional[cv2.Mat]]:
        """Try stable Windows camera backends in order, releasing each failed handle."""
        if platform.system() == "Windows":
            backends = [
                ("DirectShow", cv2.CAP_DSHOW),
                ("Media Foundation", cv2.CAP_MSMF),
                ("Auto", cv2.CAP_ANY),
            ]
        else:
            backends = [("Auto", cv2.CAP_ANY)]

        for backend_name, backend in backends:
            self._release_capture()
            try:
                self.cap = cv2.VideoCapture(camera_index, backend)
                if self.cap is None or not self.cap.isOpened():
                    continue
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if self.width:
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                if self.height:
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                if self.target_fps > 0:
                    self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                grabbed, frame = self._read_warmup_frame()
                if grabbed:
                    print(f"[VideoStream] Camera USB đang dùng backend {backend_name}.")
                    return True, frame
            except cv2.error:
                pass
            self._release_capture()
        return False, None

    def _connect(self) -> bool:
        """Connect once; the background loop keeps retrying after any failure."""
        try:
            grabbed, frame = False, None
            with self.capture_lock:
                if self.cap is not None:
                    self._release_capture()
                    time.sleep(0.15)

                self.is_file = self._check_if_file(self.src)
                capture_src = self._resolve_camera_source()
                self.active_src = capture_src

                is_usb_source = self._is_usb_source(self.src)
                if is_usb_source and capture_src is None:
                    self.is_connected = False
                    self.grabbed = False
                    self.frame = None
                    return False

                if is_usb_source:
                    grabbed, frame = self._open_usb_camera(int(capture_src))
                else:
                    self._open_network_or_file()

                if self.cap is not None and self.cap.isOpened():
                    if self.is_file:
                        fps = self.cap.get(cv2.CAP_PROP_FPS)
                        self.file_fps = fps if fps and 5.0 <= fps <= 120.0 else 25.0
                        self.frame_delay = 1.0 / self.file_fps

                    if not is_usb_source:
                        grabbed, frame = self.cap.read()

                if grabbed and frame is not None:
                    frame = self._prepare_frame(frame)
                    # Không lồng state lock trong capture lock để tránh deadlock lúc stop().
                    captured_at = time.perf_counter()
                    self.frame = frame
                    self.frame_sequence += 1
                    self.frame_captured_at = captured_at
                    self._next_live_publish_at = (
                        captured_at + 1.0 / self.target_fps
                        if not self.is_file and self.target_fps > 0 else captured_at
                    )
                    self.grabbed = True
                    self.is_connected = True
                    print(f"[VideoStream] Đã kết nối thành công tới: {self.active_src} (is_file={self.is_file})")
                    return True

                self._release_capture()
            print(f"[VideoStream] Chưa thể mở nguồn: {self.src}; hệ thống sẽ tự thử lại.")
            self.is_connected = False
            self.grabbed = False
            self.frame = None
            return False
        except Exception as exc:
            print(f"[VideoStream] Ngoại lệ khi mở stream: {exc}")
            with self.capture_lock:
                self._release_capture()
            self.is_connected = False
            self.grabbed = False
            self.frame = None
            return False

    def start(self):
        """Khởi động luồng đọc frame chạy ngầm và kết nối camera"""
        if not self.stopped and self.thread is not None and self.thread.is_alive():
            return self

        self.stopped = False
        self._stop_event.clear()
        self._next_live_publish_at = 0.0
        print(f"[VideoStream] Đang khởi động luồng đọc: {self.src}...")
        if self.anti_glare_enabled:
            mode = "tự động" if self.anti_glare_auto else "luôn bật"
            print(f"[VideoStream] Chống lóa đang bật ({mode}).")
        self._connect()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return self

    def change_source(self, new_src: VideoSource):
        """Thay đổi nguồn đầu vào (Webcam hoặc Video file) mượt mà và tự động bật nguồn mới"""
        new_src = normalize_video_source(new_src)

        # Dừng nguồn cũ
        self.stop()

        # Xóa sạch queue cũ khi đổi nguồn
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except Exception:
                break

        self.src = new_src
        self.is_file = self._check_if_file(new_src)
        with self.lock:
            self.frame_sequence = 0
            self.frame_captured_at = 0.0
            self._next_live_publish_at = 0.0
        print(f"[VideoStream] Đã chuyển đổi nguồn sang: {self.src} (is_file={self.is_file})")

        # Tự động khởi động và kết nối nguồn mới ngay lập tức
        self.start()

    def _update(self):
        """Vòng lặp đọc frame liên tục trên thread nền"""
        while not self.stopped:
            if not self.is_connected or self.cap is None or not self.cap.isOpened():
                if self._stop_event.wait(self.reconnect_interval):
                    break
                if not self.stopped:
                    print(f"[VideoStream] Đang thử kết nối lại tới: {self.src}...")
                    self._connect()
                continue

            try:
                with self.capture_lock:
                    cap = self.cap
                    grabbed, frame = cap.read() if cap is not None else (False, None)
            except cv2.error as exc:
                print(f"[VideoStream] Lỗi đọc frame tạm thời: {exc}. Đang phục hồi nguồn...")
                grabbed, frame = False, None

            if not grabbed or frame is None:
                # File hết/chập chờn: tua và đọc lại ngay, không rơi vào reconnect 3 giây.
                if self.is_file and self.loop_video:
                    try:
                        with self.capture_lock:
                            cap = self.cap
                            rewound = bool(cap is not None and cap.isOpened()
                                           and cap.set(cv2.CAP_PROP_POS_FRAMES, 0))
                            grabbed, frame = cap.read() if rewound else (False, None)
                    except cv2.error:
                        grabbed, frame = False, None
                    if not grabbed or frame is None:
                        # Backend có thể tự đóng ở EOF; mở lại ngay trong cùng thread.
                        if not self._connect():
                            time.sleep(0.2)
                        continue

                else:
                    with self.lock:
                        self.is_connected = False
                        self.grabbed = False
                        self.frame = None
                        self.fps = 0.0
                    with self.capture_lock:
                        self._release_capture()
                    print(f"[VideoStream] Mất tín hiệu hoặc kết thúc nguồn: {self.src}")
                    self._stop_event.wait(0.5)
                    continue

            frame = self._prepare_frame(frame)
            captured_at = time.perf_counter()

            # Keep live publication stable and bounded without building a backlog.
            if not self.is_file and self.target_fps > 0:
                publish_interval = 1.0 / self.target_fps
                # Allow modest driver jitter; otherwise a nominal 15 FPS camera
                # arriving a millisecond early could accidentally be reduced to 7.5 FPS.
                if captured_at + publish_interval * 0.20 < self._next_live_publish_at:
                    continue
                self._next_live_publish_at = captured_at + publish_interval

            with self.lock:
                self.frame_sequence += 1
                sequence = self.frame_sequence
                self.frame_captured_at = captured_at
            packet = FramePacket(frame=frame, sequence=sequence, captured_at=captured_at)

            # File: chờ consumer lấy frame (back-pressure), tuyệt đối không đọc/bỏ frame kế tiếp.
            if self.is_file:
                queued = False
                while not self.stopped and not queued:
                    try:
                        self.frame_queue.put(packet, timeout=0.1)
                        queued = True
                    except queue.Full:
                        continue
                if queued:
                    with self.lock:
                        self.grabbed = True
                        self.is_connected = True
            else:
                # Đối với Live Webcam/RTSP: Chỉ giữ frame mới nhất để triệt tiêu độ trễ
                with self.lock:
                    self.frame = frame
                    self.frame_sequence = sequence
                    self.frame_captured_at = captured_at
                    self.grabbed = True
                    self.is_connected = True
                time.sleep(0.002)

            # Tính toán FPS nguồn
            self._fps_count += 1
            elapsed = time.time() - self._fps_start_time
            if elapsed >= 1.0:
                self.fps = round(self._fps_count / elapsed, 1)
                self._fps_count = 0
                self._fps_start_time = time.time()

    def read(self) -> Optional[cv2.Mat]:
        """Lấy frame tiếp theo (non-blocking cho live camera, tuần tự cho video file)"""
        if self.stopped:
            return None

        if self.is_file:
            try:
                packet = self.frame_queue.get(timeout=0.03)
                return packet.frame if isinstance(packet, FramePacket) else packet
            except queue.Empty:
                return None
        else:
            with self.lock:
                if not self.is_connected or not self.grabbed or self.frame is None:
                    return None
                return self.frame.copy()

    def read_packet(self, last_sequence: Optional[int] = None) -> Optional[FramePacket]:
        """Return a unique frame packet with sequence and monotonic capture time."""
        if self.stopped:
            return None

        if self.is_file:
            try:
                packet = self.frame_queue.get(timeout=0.03)
                if isinstance(packet, FramePacket):
                    return packet
                return FramePacket(packet, self.frame_sequence, time.perf_counter())
            except queue.Empty:
                return None

        with self.lock:
            if not self.is_connected or not self.grabbed or self.frame is None:
                return None
            if last_sequence is not None and self.frame_sequence <= last_sequence:
                return None
            return FramePacket(
                frame=self.frame.copy(),
                sequence=self.frame_sequence,
                captured_at=self.frame_captured_at,
            )

    def stop(self):
        """Dừng luồng và giải phóng hoàn toàn camera phần cứng (tắt đèn webcam)"""
        self.stopped = True
        self._stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        self.thread = None

        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except Exception:
                break

        with self.lock:
            with self.capture_lock:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
            self.frame = None
            self.frame_sequence = 0
            self.frame_captured_at = 0.0
            self.grabbed = False
            self.is_connected = False
            self.fps = 0.0
        print(f"[VideoStream] Đã giải phóng hoàn toàn phần cứng camera ({self.src}). Đèn camera đã tắt.")
