import unittest
from unittest.mock import patch

import cv2
import numpy as np

from src.ncnn_backend import (
    LiteByteTracker,
    NcnnYoloDetector,
    _nms_xyxy,
    _validate_detector_input_size,
    prepare_detector_input,
    prepare_detector_input_into,
)


class NcnnMetadataTests(unittest.TestCase):
    def test_accepts_runtime_size_matching_export_metadata(self):
        with patch("src.ncnn_backend._read_model_metadata", return_value={"imgsz": [640, 640]}):
            self.assertEqual(_validate_detector_input_size("model.ncnn.param", 640), 640)

    def test_rejects_runtime_size_different_from_fixed_export(self):
        with patch("src.ncnn_backend._read_model_metadata", return_value={"imgsz": [640, 640]}):
            with self.assertRaisesRegex(ValueError, "does not match.*640x640"):
                _validate_detector_input_size("model.ncnn.param", 416)

    def test_allows_model_without_metadata(self):
        with patch("src.ncnn_backend._read_model_metadata", return_value={}):
            self.assertEqual(_validate_detector_input_size("model.ncnn.param", 320), 320)


class NcnnPostprocessTests(unittest.TestCase):
    def test_prepares_720p_as_exact_320_square_with_reversible_transform(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        image, transform = prepare_detector_input(frame, 320)

        self.assertEqual(image.shape, (320, 320, 3))
        self.assertTrue(image.flags.c_contiguous)
        self.assertEqual(transform, (720, 1280, 0.25, 0, 70))
        self.assertTrue(np.all(image[:70] == 114))
        self.assertTrue(np.all(image[250:] == 114))

    def test_prepares_directly_into_reusable_detector_buffer(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :, 1] = 77
        output = np.empty((320, 320, 3), dtype=np.uint8)

        transform = prepare_detector_input_into(frame, 320, output)

        self.assertEqual(transform, (720, 1280, 0.25, 0, 70))
        self.assertTrue(np.all(output[:70] == 114))
        self.assertTrue(np.all(output[70:250, :, 1] == 77))
        self.assertTrue(np.all(output[250:] == 114))

    def test_reusable_detector_buffer_requires_exact_shape_and_dtype(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "Expected uint8 detector output"):
            prepare_detector_input_into(
                frame,
                320,
                np.empty((640, 640, 3), dtype=np.uint8),
            )

    def test_direct_shared_buffer_is_pixel_identical_to_reference_letterbox(self):
        rng = np.random.default_rng(1234)
        frame = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)
        expected = np.full((320, 320, 3), 114, dtype=np.uint8)
        expected[70:250] = cv2.resize(
            frame,
            (320, 180),
            interpolation=cv2.INTER_LINEAR,
        )
        actual = np.empty_like(expected)

        transform = prepare_detector_input_into(frame, 320, actual)

        self.assertEqual(transform, (720, 1280, 0.25, 0, 70))
        np.testing.assert_array_equal(actual, expected)

    def test_accepts_both_common_yolo_output_layouts(self):
        detector = NcnnYoloDetector.__new__(NcnnYoloDetector)
        detector.output_channels = 84
        channels_first = np.zeros((1, 84, 8400), dtype=np.float32)
        candidates_first = np.zeros((1, 8400, 84), dtype=np.float32)
        self.assertEqual(detector._as_predictions(channels_first).shape, (84, 8400))
        self.assertEqual(detector._as_predictions(candidates_first).shape, (84, 8400))

        detector.output_channels = 5
        single_class = np.zeros((1, 5, 2100), dtype=np.float32)
        self.assertEqual(detector._as_predictions(single_class).shape, (5, 2100))

    def test_nms_removes_heavily_overlapping_box(self):
        boxes = np.asarray([[0, 0, 100, 100], [5, 5, 98, 98], [150, 0, 230, 100]], dtype=np.float32)
        scores = np.asarray([0.9, 0.8, 0.7], dtype=np.float32)
        self.assertEqual(_nms_xyxy(boxes, scores, 0.6), [0, 2])


class LiteByteTrackerTests(unittest.TestCase):
    def test_keeps_id_for_a_moving_detection(self):
        tracker = LiteByteTracker(new_track_threshold=0.3)
        first = tracker.update([{"bbox": [10, 10, 60, 110], "conf": 0.9}])
        second = tracker.update([{"bbox": [14, 10, 64, 110], "conf": 0.9}])
        self.assertEqual(first[0]["track_id"], second[0]["track_id"])

    def test_low_confidence_detection_does_not_create_but_can_continue_track(self):
        tracker = LiteByteTracker(high_threshold=0.3, low_threshold=0.08, new_track_threshold=0.38)
        self.assertEqual(tracker.update([{"bbox": [10, 10, 60, 110], "conf": 0.2}]), [])
        first = tracker.update([{"bbox": [10, 10, 60, 110], "conf": 0.9}])
        continued = tracker.update([{"bbox": [12, 10, 62, 110], "conf": 0.2}])
        self.assertEqual(first[0]["track_id"], continued[0]["track_id"])

    def test_predicts_intermediate_frame_without_mutating_tracker_state(self):
        tracker = LiteByteTracker(new_track_threshold=0.3)
        tracker.update([{"bbox": [10, 10, 60, 110], "conf": 0.9}])
        tracker.update([{"bbox": [20, 10, 70, 110], "conf": 0.9}])

        predicted = tracker.predicted_tracks(frame_gap=2)
        current = tracker.predicted_tracks(frame_gap=0)

        self.assertEqual(predicted[0]["bbox"], [27, 10, 77, 110])
        self.assertEqual(current[0]["bbox"], [20, 10, 70, 110])


if __name__ == "__main__":
    unittest.main()
