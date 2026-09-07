import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import queue
import threading
import cv2
from typing import Optional, Union


class ThreadedVideoStream:
    """
    Luồng đọc video nền (Background Daemon Thread) chuyên dụng cho Webcam, RTSP và Video.
    - Triệt tiêu hoàn toàn hiện tượng trễ/lag buffer camera bằng cách chỉ lưu trữ frame mới nhất.
    - Tự động phát hiện mất tín hiệu và thử kết nối lại (Auto-reconnect).
    - Đo đạc tốc độ khung hình (FPS) nguồn thực tế.
    """
    def __init__(self, src: Union[int, str] = 0, reconnect_interval: int = 3, 
                 width: Optional[int] = None, height: Optional[int] = None,
                 loop_video: bool = True):
        # Chuyển đổi "0" thành số nguyên 0 nếu là webcam
        if isinstance(src, str) and src.isdigit():
            src = int(src)
        self.src = src
        self.reconnect_interval = reconnect_interval
        self.width = width
        self.height = height
        self.loop_video = loop_video

        self.cap = None
        self.frame = None
        self.grabbed = False
        self.stopped = True
        self.is_connected = False

        self.lock = threading.Lock()
        self.frame_queue = queue.Queue(maxsize=3)
        self.fps = 0.0
        self._fps_count = 0
        self._fps_start_time = time.time()
        self.thread = None

        self.is_file = self._check_if_file(self.src)
        self.file_fps = 30.0
        self.frame_delay = 0.033

    @staticmethod
    def _check_if_file(src: Union[int, str]) -> bool:
        if isinstance(src, int):
            return False
        if isinstance(src, str):
            if src.startswith("rtsp://") or src.startswith("http://") or src.startswith("https://"):
                return False
            return True
        return False

    def _connect(self) -> bool:
        """Thử kết nối với nguồn video (Webcam, RTSP hoặc File Video)"""
        try:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                time.sleep(0.15)

            self.is_file = self._check_if_file(self.src)

            # Đối với RTSP trên Windows/Linux, cấu hình backend FFMPEG tối ưu
            if isinstance(self.src, str) and self.src.startswith("rtsp"):
                self.cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            elif isinstance(self.src, int):
                # Đối với Webcam máy tính: Trên Windows ưu tiên cv2.CAP_DSHOW để mở ngay lập tức,
                # tránh lỗi 'MFVideoCallback::OnReadSample is failed with error status: -1072873821' của MSMF.
                import platform
                if platform.system() == "Windows":
                    self.cap = cv2.VideoCapture(self.src, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        time.sleep(0.2)
                        self.cap = cv2.VideoCapture(self.src, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        self.cap = cv2.VideoCapture(self.src)
                else:
                    self.cap = cv2.VideoCapture(self.src)

                if self.cap is not None and self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if self.width:
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    if self.height:
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            else:
                self.cap = cv2.VideoCapture(self.src)

            if self.cap is not None and self.cap.isOpened():
                if self.is_file:
                    fps = self.cap.get(cv2.CAP_PROP_FPS)
                    if fps and 5.0 <= fps <= 120.0:
                        self.file_fps = fps
                    else:
                        self.file_fps = 25.0
                    self.frame_delay = 1.0 / self.file_fps

                grabbed, frame = self.cap.read()
                # Nếu lần đọc đầu thất bại với webcam (do độ phân giải không tương thích), mở lại với mặc định
                if (not grabbed or frame is None) and isinstance(self.src, int):
                    print(f"[VideoStream] Thử lại mở webcam {self.src} với cấu hình mặc định...")
                    self.cap.release()
                    import platform
                    if platform.system() == "Windows":
                        self.cap = cv2.VideoCapture(self.src, cv2.CAP_DSHOW)
                    else:
                        self.cap = cv2.VideoCapture(self.src)
                    if self.cap is not None and self.cap.isOpened():
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        grabbed, frame = self.cap.read()

                if grabbed and frame is not None:
                    with self.lock:
                        self.frame = frame
                        self.grabbed = True
                        self.is_connected = True
                    print(f"[VideoStream] Đã kết nối thành công tới: {self.src} (is_file={self.is_file})")
                    return True

            print(f"[VideoStream] Chưa thể mở nguồn: {self.src}")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"[VideoStream] Ngoại lệ khi mở stream: {e}")
            self.is_connected = False
            return False

    def start(self):
        """Khởi động luồng đọc frame chạy ngầm và kết nối camera"""
        if not self.stopped and self.thread is not None and self.thread.is_alive():
            return self

        self.stopped = False
        print(f"[VideoStream] Đang khởi động luồng đọc: {self.src}...")
        self._connect()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return self

    def change_source(self, new_src: Union[int, str]):
        """Thay đổi nguồn đầu vào (Webcam hoặc Video file) mượt mà và tự động bật nguồn mới"""
        if isinstance(new_src, str) and new_src.isdigit():
            new_src = int(new_src)

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
        print(f"[VideoStream] Đã chuyển đổi nguồn sang: {self.src} (is_file={self.is_file})")

        # Tự động khởi động và kết nối nguồn mới ngay lập tức
        self.start()

    def _update(self):
        """Vòng lặp đọc frame liên tục trên thread nền"""
        while not self.stopped:
            if not self.is_connected or self.cap is None or not self.cap.isOpened():
                time.sleep(self.reconnect_interval)
                if not self.stopped:
                    print(f"[VideoStream] Đang thử kết nối lại tới: {self.src}...")
                    self._connect()
                continue

            grabbed, frame = self.cap.read()

            if not grabbed or frame is None:
                # Nếu là video file và được bật lặp lại -> Tua về đầu video
                if self.is_file and self.loop_video and self.cap is not None and self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.01)
                    continue

                with self.lock:
                    self.is_connected = False
                print(f"[VideoStream] Mất tín hiệu hoặc kết thúc nguồn: {self.src}")
                time.sleep(0.5)
                continue

            # Chuẩn hóa độ phân giải 1280x720 ngay trên thread nền để giải phóng CPU cho luồng AI chính
            h_f, w_f = frame.shape[:2]
            if w_f != 1280 or h_f != 720:
                frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)

            # Đối với Video File: Đẩy vào Queue tuần tự để AI xử lý mượt mà, không bao giờ rơi rớt frame
            if self.is_file:
                try:
                    self.frame_queue.put(frame, timeout=0.2)
                    with self.lock:
                        self.grabbed = True
                        self.is_connected = True
                except queue.Full:
                    pass
            else:
                # Đối với Live Webcam/RTSP: Chỉ giữ frame mới nhất để triệt tiêu độ trễ
                with self.lock:
                    self.frame = frame
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
                return self.frame_queue.get(timeout=0.03)
            except queue.Empty:
                return None
        else:
            with self.lock:
                if not self.grabbed or self.frame is None:
                    return None
                return self.frame.copy()

    def get_fps(self) -> float:
        """Lấy FPS của luồng đầu vào"""
        return self.fps

    def stop(self):
        """Dừng luồng và giải phóng hoàn toàn camera phần cứng (tắt đèn webcam)"""
        self.stopped = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        self.thread = None

        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except Exception:
                break

        with self.lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.frame = None
            self.grabbed = False
            self.is_connected = False
            self.fps = 0.0
        print(f"[VideoStream] Đã giải phóng hoàn toàn phần cứng camera ({self.src}). Đèn camera đã tắt.")
