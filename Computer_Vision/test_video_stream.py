import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from src.video_stream import ThreadedVideoStream


class CameraSelectionTests(unittest.TestCase):
    def _resolve(self, device_output):
        stream = ThreadedVideoStream(
            src="auto_usb",
            excluded_camera_names=["ACER HD User Facing"],
        )
        with patch("shutil.which", return_value="ffmpeg"), patch(
            "subprocess.run", return_value=SimpleNamespace(stdout=device_output)
        ):
            return stream._resolve_camera_source()

    def test_selects_any_physical_usb_camera(self):
        output = "\n".join([
            '"ACER HD User Facing" (none)',
            '"Generic USB Camera XYZ" (none)',
            '"OBS Virtual Camera" (video)',
        ])
        self.assertEqual(self._resolve(output), 1)

    def test_never_falls_back_to_integrated_or_virtual_camera(self):
        output = "\n".join([
            '"ACER HD User Facing" (none)',
            '"OBS Virtual Camera" (video)',
        ])
        self.assertIsNone(self._resolve(output))

    def test_disconnected_stream_does_not_return_stale_frame(self):
        stream = ThreadedVideoStream(src=0)
        stream.stopped = False
        stream.grabbed = True
        stream.frame = np.zeros((2, 2, 3), dtype=np.uint8)
        stream.is_connected = False
        self.assertIsNone(stream.read())

    def test_live_packet_is_returned_only_once_per_sequence(self):
        stream = ThreadedVideoStream(src=0)
        stream.stopped = False
        stream.grabbed = True
        stream.is_connected = True
        stream.frame = np.zeros((2, 2, 3), dtype=np.uint8)
        stream.frame_sequence = 7
        stream.frame_captured_at = 12.5

        packet = stream.read_packet(last_sequence=6)

        self.assertIsNotNone(packet)
        self.assertEqual(packet.sequence, 7)
        self.assertEqual(packet.captured_at, 12.5)
        self.assertIsNone(stream.read_packet(last_sequence=7))

    def test_numeric_path_uses_exact_index_without_auto_detection(self):
        stream = ThreadedVideoStream(src=1, excluded_camera_names=["anything"])
        with patch("subprocess.run") as enumerate_devices:
            self.assertEqual(stream._resolve_camera_source(), 1)
        enumerate_devices.assert_not_called()

    def test_ip_path_is_not_treated_as_a_file_or_usb_camera(self):
        source = "rtsp://camera.local/live"
        self.assertFalse(ThreadedVideoStream._check_if_file(source))
        self.assertFalse(ThreadedVideoStream._is_usb_source(source))

    def test_horizontal_flip_corrects_mirrored_camera(self):
        stream = ThreadedVideoStream(src=0, flip_horizontal=True)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, 0] = (10, 20, 30)

        corrected = stream._prepare_frame(frame)

        self.assertTrue(np.all(corrected[:, -1] == (10, 20, 30)))
        self.assertTrue(np.all(corrected[:, 0] == (0, 0, 0)))

    def test_anti_glare_compresses_harsh_highlights(self):
        stream = ThreadedVideoStream(
            src=0,
            anti_glare={
                "enabled": True,
                "auto": True,
                "threshold": 210,
                "min_bright_ratio": 0.04,
                "highlight_compression": 0.60,
            },
        )
        frame = np.full((720, 1280, 3), 245, dtype=np.uint8)
        frame[:, :320] = 100

        corrected = stream._prepare_frame(frame)

        self.assertLess(float(corrected[:, 640:].mean()), 235.0)
        self.assertGreater(
            float(corrected[:, 640:].mean()),
            float(corrected[:, :320].mean()),
        )

    def test_anti_glare_auto_leaves_normal_light_unchanged(self):
        stream = ThreadedVideoStream(
            src=0,
            anti_glare={"enabled": True, "auto": True, "threshold": 210},
        )
        frame = np.full((720, 1280, 3), 100, dtype=np.uint8)

        corrected = stream._prepare_frame(frame)

        np.testing.assert_array_equal(corrected, frame)


class CameraBackendTests(unittest.TestCase):
    def test_windows_falls_back_from_dshow_to_msmf(self):
        attempted_backends = []

        class FakeCapture:
            def __init__(self, index, backend):
                attempted_backends.append(backend)
                self.backend = backend
                self.released = False

            def isOpened(self):
                return not self.released and self.backend == cv2.CAP_MSMF

            def set(self, *_args):
                return True

            def read(self):
                return True, np.zeros((4, 4, 3), dtype=np.uint8)

            def release(self):
                self.released = True

        stream = ThreadedVideoStream(src=0)
        with patch("platform.system", return_value="Windows"), patch(
            "cv2.VideoCapture", side_effect=FakeCapture
        ):
            grabbed, frame = stream._open_usb_camera(0)

        self.assertTrue(grabbed)
        self.assertIsNotNone(frame)
        self.assertEqual(attempted_backends[:2], [cv2.CAP_DSHOW, cv2.CAP_MSMF])

    def test_usb_requests_configured_target_fps(self):
        properties = []

        class FakeCapture:
            def __init__(self, _index, _backend):
                self.released = False

            def isOpened(self):
                return not self.released

            def set(self, prop, value):
                properties.append((prop, value))
                return True

            def read(self):
                return True, np.zeros((4, 4, 3), dtype=np.uint8)

            def release(self):
                self.released = True

        stream = ThreadedVideoStream(src=0, target_fps=15)
        with patch("platform.system", return_value="Windows"), patch(
            "cv2.VideoCapture", side_effect=FakeCapture
        ):
            grabbed, _ = stream._open_usb_camera(0)

        self.assertTrue(grabbed)
        self.assertIn((cv2.CAP_PROP_FPS, 15.0), properties)

    def test_usb_requests_mjpg_before_resolution_and_fps(self):
        properties = []

        class FakeCapture:
            def __init__(self, _index, _backend):
                self.released = False

            def isOpened(self):
                return not self.released

            def set(self, prop, value):
                properties.append((prop, value))
                return True

            def read(self):
                return True, np.zeros((720, 1280, 3), dtype=np.uint8)

            def release(self):
                self.released = True

        stream = ThreadedVideoStream(
            src=0,
            width=1280,
            height=720,
            target_fps=15,
            fourcc="mjpg",
        )
        with patch("platform.system", return_value="Linux"), patch(
            "cv2.VideoCapture", side_effect=FakeCapture
        ):
            grabbed, _ = stream._open_usb_camera(0)

        self.assertTrue(grabbed)
        fourcc_index = next(
            index for index, (prop, _value) in enumerate(properties)
            if prop == cv2.CAP_PROP_FOURCC
        )
        width_index = next(
            index for index, (prop, _value) in enumerate(properties)
            if prop == cv2.CAP_PROP_FRAME_WIDTH
        )
        fps_index = next(
            index for index, (prop, _value) in enumerate(properties)
            if prop == cv2.CAP_PROP_FPS
        )
        self.assertLess(fourcc_index, width_index)
        self.assertLess(fourcc_index, fps_index)
        self.assertEqual(stream.fourcc, "MJPG")

    def test_linux_retries_when_first_backend_ignores_mjpg(self):
        attempted_backends = []

        class FakeCapture:
            def __init__(self, _index, backend):
                attempted_backends.append(backend)
                self.backend = backend
                self.released = False

            def isOpened(self):
                return not self.released

            def set(self, _prop, _value):
                return True

            def get(self, prop):
                if prop == cv2.CAP_PROP_FOURCC:
                    value = "YUYV" if self.backend == cv2.CAP_V4L2 else "MJPG"
                    return cv2.VideoWriter_fourcc(*value)
                if prop == cv2.CAP_PROP_FRAME_WIDTH:
                    return 1280
                if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                    return 720
                if prop == cv2.CAP_PROP_FPS:
                    return 10 if self.backend == cv2.CAP_V4L2 else 15
                return 0

            def read(self):
                return True, np.zeros((720, 1280, 3), dtype=np.uint8)

            def release(self):
                self.released = True

        stream = ThreadedVideoStream(
            src=0,
            width=1280,
            height=720,
            target_fps=15,
            fourcc="MJPG",
        )
        with patch("platform.system", return_value="Linux"), patch(
            "cv2.VideoCapture", side_effect=FakeCapture
        ):
            grabbed, _ = stream._open_usb_camera(0)

        self.assertTrue(grabbed)
        self.assertEqual(attempted_backends, [cv2.CAP_V4L2, cv2.CAP_ANY])
        self.assertEqual(stream.negotiated_fourcc, "MJPG")
        self.assertEqual(stream.negotiated_fps, 15.0)

    def test_rtsp_uses_open_and_read_timeouts(self):
        opened_with = []

        class FakeCapture:
            def __init__(self, *args):
                opened_with.append(args)

            def isOpened(self):
                return False

        stream = ThreadedVideoStream(
            src="rtsp://camera.local/live",
            open_timeout_ms=4321,
            read_timeout_ms=5432,
        )
        with patch("cv2.VideoCapture", side_effect=FakeCapture):
            stream._open_network_or_file()

        self.assertEqual(opened_with[0][0], "rtsp://camera.local/live")
        self.assertEqual(opened_with[0][1], cv2.CAP_FFMPEG)
        self.assertIn(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, opened_with[0][2])
        self.assertIn(4321, opened_with[0][2])
        self.assertIn(cv2.CAP_PROP_READ_TIMEOUT_MSEC, opened_with[0][2])
        self.assertIn(5432, opened_with[0][2])


if __name__ == "__main__":
    unittest.main()
