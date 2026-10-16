import unittest
from collections import deque
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.ncnn_backend import LiteByteTracker
from src.tracker import PersistentIdentityManager, YOLOTracker
from src.zone_counter import DualZoneCounter


def make_person_frame(color, bbox=(30, 20, 90, 180)):
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    x1, y1, x2, y2 = bbox
    frame[y1:y2, x1:x2] = color
    return frame


class KalmanTimingTests(unittest.TestCase):
    def test_frame_gap_adds_the_missing_prediction_steps(self):
        calls = []
        track = SimpleNamespace(mean=np.zeros(8, dtype=np.float32))
        backend = SimpleNamespace(
            tracked_stracks=[track],
            lost_stracks=[],
            multi_predict=lambda pool: calls.append(len(pool)),
        )
        wrapper = YOLOTracker.__new__(YOLOTracker)
        wrapper.model = SimpleNamespace(
            predictor=SimpleNamespace(trackers=[backend])
        )

        wrapper._advance_kalman_for_gap(4)

        self.assertEqual(calls, [1, 1, 1])


class TrackerPipelineHelperTests(unittest.TestCase):
    def test_builds_clipped_head_regions_from_backend_tracks(self):
        tracks = YOLOTracker._build_tracked_objects(
            [7], [[0, 5, 50, 105]], [0.8764], (100, 80, 3)
        )

        self.assertEqual(tracks[0]["track_id"], 7)
        self.assertEqual(tracks[0]["bbox"], [0, 5, 50, 99])
        self.assertEqual(tracks[0]["head_bbox"], [10, 5, 40, 28])
        self.assertEqual(tracks[0]["conf"], 0.876)

    def test_reid_selection_is_quality_filtered_prioritized_and_bounded(self):
        wrapper = YOLOTracker.__new__(YOLOTracker)
        wrapper.identity = SimpleNamespace(
            local_to_stable={},
            profiles={},
            should_recheck=lambda _stable_id: False,
        )
        wrapper._frame_index = 6
        wrapper._reid_last_sample = {}
        wrapper.reid_sample_interval = 3
        wrapper.reid_min_confidence = 0.5
        wrapper.reid_min_bbox_height = 80
        wrapper.reid_max_per_frame = 2
        wrapper.reid_max_periodic_per_frame = 1
        wrapper.reid_periodic_schedule_frames = 3
        tracks = [
            {"track_id": 1, "bbox": [0, 0, 20, 120], "conf": 0.7},
            {"track_id": 2, "bbox": [0, 0, 20, 100], "conf": 0.9},
            {"track_id": 3, "bbox": [0, 0, 20, 70], "conf": 0.99},
        ]

        selected = wrapper._select_reid_requests(tracks)

        self.assertEqual([item["track_id"] for item in selected], [2, 1])

    def test_async_ncnn_returns_motion_tracks_between_detector_results(self):
        class ImmediateExecutor:
            @staticmethod
            def submit(function, *args):
                future = Future()
                future.set_result(function(*args))
                return future

        wrapper = YOLOTracker.__new__(YOLOTracker)
        wrapper._detector_callable = lambda _transform, _preprocess_ms: (
            [{"bbox": [10, 10, 60, 110], "conf": 0.9}],
            417.0,
        )
        wrapper._detector_preprocessor = lambda _frame, _imgsz: (
            np.zeros((320, 320, 3), dtype=np.uint8),
            (120, 80, 2.6666666667, 53, 0),
        )
        wrapper._detector_input_view = np.zeros((320, 320, 3), dtype=np.uint8)
        wrapper.local_tracker = LiteByteTracker(new_track_threshold=0.3)
        wrapper._detector_executor = ImmediateExecutor()
        wrapper._detector_future = None
        wrapper._detector_future_sequence = 0
        wrapper._detector_future_generation = 0
        wrapper._detector_last_submit_sequence = None
        wrapper._detector_last_applied_sequence = None
        wrapper._detector_generation = 0
        wrapper._ncnn_sequence = 0
        wrapper._detector_timestamps = deque(maxlen=30)
        wrapper._detector_fps = 0.0
        wrapper._detector_latency_ms = 0.0
        wrapper.ncnn_detection_interval_frames = 1
        wrapper.imgsz = 320
        frame = np.zeros((120, 80, 3), dtype=np.uint8)

        first = wrapper._track_ncnn_async(frame, effective_gap=1)
        second = wrapper._track_ncnn_async(frame, effective_gap=1)

        self.assertEqual(first, [])
        self.assertEqual(second[0]["track_id"], 1)


class PersistentIdentityTests(unittest.TestCase):
    def test_skips_color_descriptor_on_interpolated_frame(self):
        manager = PersistentIdentityManager(memory_seconds=30)
        frame = make_person_frame((20, 40, 220))
        track = {"track_id": 1, "bbox": [30, 20, 90, 180], "conf": 0.9}
        manager.update(frame, [track], now=1.0)

        with patch.object(manager, "extract_descriptor", wraps=manager.extract_descriptor) as extract:
            manager.update(frame, [track], now=1.1, update_appearance=False)

        extract.assert_not_called()

    def test_suppresses_duplicate_boxes_and_keeps_existing_id(self):
        manager = PersistentIdentityManager(memory_seconds=0)
        frame = make_person_frame((20, 40, 220), [30, 20, 100, 190])
        initial = manager.update(
            frame, [{"track_id": 4, "bbox": [30, 20, 100, 190], "conf": 0.90}],
            now=1.0, reid_features={4: np.array([1.0, 0.0, 0.0])},
        )
        duplicated = manager.update(
            frame,
            [
                {"track_id": 4, "bbox": [30, 20, 100, 190], "conf": 0.72},
                {"track_id": 88, "bbox": [32, 22, 101, 189], "conf": 0.95},
            ],
            now=2.0,
            reid_features={4: np.array([1.0, 0.0, 0.0]), 88: np.array([0.99, 0.01, 0.0])},
        )
        self.assertEqual(len(duplicated), 1)
        self.assertEqual(duplicated[0]["local_track_id"], 4)
        self.assertEqual(duplicated[0]["track_id"], initial[0]["track_id"])

    def test_keeps_overlapping_boxes_for_different_people(self):
        manager = PersistentIdentityManager(memory_seconds=0)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        tracks = manager.update(
            frame,
            [
                {"track_id": 1, "bbox": [30, 20, 110, 200], "conf": 0.90},
                {"track_id": 2, "bbox": [55, 20, 135, 200], "conf": 0.91},
            ],
            now=1.0,
            reid_features={1: np.array([1.0, 0.0]), 2: np.array([0.0, 1.0])},
        )
        self.assertEqual(len(tracks), 2)

    def test_zero_memory_ttl_keeps_identity_for_whole_session(self):
        manager = PersistentIdentityManager(memory_seconds=0, appearance_threshold=0.8)
        bbox = [30, 20, 90, 180]
        frame = make_person_frame((20, 40, 220), bbox)
        first = manager.update(frame, [{"track_id": 1, "bbox": bbox}], now=1.0)
        manager.update(frame, [], now=10_000.0)
        second = manager.update(frame, [{"track_id": 99, "bbox": bbox}], now=10_001.0)
        self.assertEqual(first[0]["track_id"], second[0]["track_id"])

    def test_reconnects_new_local_id_to_same_stable_id(self):
        manager = PersistentIdentityManager(memory_seconds=30, appearance_threshold=0.80)
        bbox1 = [30, 20, 90, 180]
        first = manager.update(make_person_frame((20, 40, 220), bbox1),
                               [{"track_id": 7, "bbox": bbox1}], now=1.0)
        manager.update(make_person_frame((0, 0, 0)), [], now=2.0)

        bbox2 = [45, 20, 105, 180]
        second = manager.update(make_person_frame((20, 40, 220), bbox2),
                                [{"track_id": 91, "bbox": bbox2}], now=4.0)
        self.assertEqual(first[0]["track_id"], second[0]["track_id"])
        self.assertTrue(second[0]["reidentified"])
        self.assertEqual(second[0]["local_track_id"], 91)

    def test_does_not_merge_different_appearance(self):
        manager = PersistentIdentityManager(memory_seconds=30, appearance_threshold=0.90)
        bbox = [30, 20, 90, 180]
        first = manager.update(make_person_frame((20, 40, 220), bbox),
                               [{"track_id": 1, "bbox": bbox}], now=1.0)
        manager.update(make_person_frame((0, 0, 0)), [], now=2.0)
        second = manager.update(make_person_frame((20, 220, 40), bbox),
                                [{"track_id": 2, "bbox": bbox}], now=3.0)
        self.assertNotEqual(first[0]["track_id"], second[0]["track_id"])

    def test_never_merges_two_similar_people_visible_together(self):
        manager = PersistentIdentityManager(memory_seconds=30, appearance_threshold=0.80)
        a, b = [20, 20, 80, 180], [180, 20, 240, 180]
        frame = make_person_frame((100, 80, 200), a)
        frame[20:180, 180:240] = (100, 80, 200)
        tracks = manager.update(frame, [{"track_id": 1, "bbox": a}, {"track_id": 2, "bbox": b}], now=1.0)
        self.assertEqual(len({t["track_id"] for t in tracks}), 2)

    def test_deep_reid_recovers_id_after_move_from_zone_a_to_b(self):
        manager = PersistentIdentityManager(memory_seconds=30, appearance_threshold=0.82)
        zone_a_bbox = [30, 20, 90, 180]
        zone_b_bbox = [150, 40, 210, 200]
        first_frame = make_person_frame((20, 40, 220), zone_a_bbox)
        deep_a = np.array([1.0, 0.1, 0.0, 0.0], dtype=np.float32)
        first = manager.update(
            first_frame, [{"track_id": 7, "bbox": zone_a_bbox, "conf": 0.9}],
            now=1.0, reid_features={7: deep_a}
        )
        manager.update(make_person_frame((0, 0, 0)), [], now=2.0)

        # Ánh sáng/màu crop thay đổi và tracker cấp local ID mới ở vùng B.
        second_frame = make_person_frame((35, 55, 185), zone_b_bbox)
        deep_b = np.array([0.98, 0.12, 0.01, 0.0], dtype=np.float32)
        second = manager.update(
            second_frame, [{"track_id": 99, "bbox": zone_b_bbox, "conf": 0.88}],
            now=5.0, reid_features={99: deep_b}
        )
        self.assertEqual(first[0]["track_id"], second[0]["track_id"])
        self.assertTrue(second[0]["reidentified"])

    def test_deep_reid_rejects_different_person(self):
        manager = PersistentIdentityManager(memory_seconds=30, appearance_threshold=0.82)
        bbox = [30, 20, 90, 180]
        frame = make_person_frame((20, 40, 220), bbox)
        first = manager.update(frame, [{"track_id": 1, "bbox": bbox, "conf": 0.9}],
                               now=1.0, reid_features={1: np.array([1, 0, 0, 0])})
        manager.update(frame, [], now=2.0)
        second = manager.update(frame, [{"track_id": 2, "bbox": bbox, "conf": 0.9}],
                                now=4.0, reid_features={2: np.array([0, 1, 0, 0])})
        self.assertNotEqual(first[0]["track_id"], second[0]["track_id"])

    def test_reid_rejects_ambiguous_gallery_match(self):
        manager = PersistentIdentityManager(
            memory_seconds=30,
            reid_threshold=0.70,
            reid_ambiguity_margin=0.06,
            require_reid_for_match=True,
        )
        left, right = [20, 20, 80, 190], [220, 20, 280, 190]
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[20:190, 20:80] = (100, 80, 200)
        frame[20:190, 220:280] = (100, 80, 200)
        original = manager.update(
            frame,
            [{"track_id": 1, "bbox": left}, {"track_id": 2, "bbox": right}],
            now=1.0,
            reid_features={
                1: np.array([1.0, 0.0, 0.0]),
                2: np.array([0.999, 0.04, 0.0]),
            },
        )
        manager.update(frame, [], now=2.0)
        middle = [130, 20, 190, 190]
        appeared = manager.update(
            frame,
            [{"track_id": 99, "bbox": middle}],
            now=3.0,
            reid_features={99: np.array([1.0, 0.02, 0.0])},
        )
        self.assertNotIn(appeared[0]["track_id"], {item["track_id"] for item in original})

    def test_reid_gallery_is_bounded(self):
        manager = PersistentIdentityManager(memory_seconds=30, reid_gallery_size=3)
        bbox = [30, 20, 90, 180]
        frame = make_person_frame((20, 40, 220), bbox)
        for index, feature in enumerate(
            ([1.0, 0.0, 0.0], [0.9, 0.4, 0.0], [0.8, 0.0, 0.6], [0.7, 0.7, 0.0])
        ):
            manager.update(
                frame,
                [{"track_id": 1, "bbox": bbox, "conf": 0.9}],
                now=float(index + 1),
                reid_features={1: np.asarray(feature)},
            )
        profile = manager.profiles[manager.local_to_stable[1]]
        self.assertEqual(len(profile.reid_gallery), 3)

    def test_delayed_first_embedding_replaces_provisional_stable_id(self):
        manager = PersistentIdentityManager(
            memory_seconds=30,
            reid_threshold=0.75,
            reid_ambiguity_margin=0.0,
            require_reid_for_match=True,
        )
        zone_a_bbox = [30, 20, 90, 180]
        zone_b_bbox = [150, 40, 210, 200]
        feature = np.array([1.0, 0.1, 0.0, 0.0], dtype=np.float32)
        original = manager.update(
            make_person_frame((20, 40, 220), zone_a_bbox),
            [{"track_id": 6, "bbox": zone_a_bbox, "conf": 0.9}],
            now=1.0,
            reid_features={6: feature},
        )
        original_id = original[0]["track_id"]
        manager.update(make_person_frame((0, 0, 0)), [], now=2.0)

        provisional = manager.update(
            make_person_frame((30, 50, 190), zone_b_bbox),
            [{"track_id": 9, "bbox": zone_b_bbox, "conf": 0.5}],
            now=4.0,
        )
        provisional_id = provisional[0]["track_id"]
        self.assertNotEqual(provisional_id, original_id)

        corrected = manager.update(
            make_person_frame((30, 50, 190), zone_b_bbox),
            [{"track_id": 9, "bbox": zone_b_bbox, "conf": 0.9}],
            now=5.0,
            reid_features={9: np.array([0.99, 0.11, 0.0, 0.0])},
        )
        self.assertEqual(corrected[0]["track_id"], original_id)
        self.assertEqual(corrected[0]["identity_remapped_from"], provisional_id)
        self.assertTrue(corrected[0]["reidentified"])
        self.assertNotIn(provisional_id, manager.profiles)

    def test_two_good_rechecks_replace_a_bad_initial_embedding(self):
        manager = PersistentIdentityManager(
            memory_seconds=30,
            reid_threshold=0.75,
            reid_ambiguity_margin=0.0,
            reid_recheck_seconds=10.0,
            require_reid_for_match=True,
        )
        bbox_a = [30, 20, 90, 180]
        bbox_b = [150, 40, 210, 200]
        frame_a = make_person_frame((20, 40, 220), bbox_a)
        frame_b = make_person_frame((30, 50, 190), bbox_b)
        original_feature = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

        original = manager.update(
            frame_a, [{"track_id": 6, "bbox": bbox_a, "conf": 0.9}],
            now=1.0, reid_features={6: original_feature},
        )
        original_id = original[0]["track_id"]
        manager.update(frame_a, [], now=2.0)

        provisional = manager.update(
            frame_b, [{"track_id": 9, "bbox": bbox_b, "conf": 0.9}],
            now=4.0,
            reid_features={9: np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)},
        )
        provisional_id = provisional[0]["track_id"]
        self.assertNotEqual(provisional_id, original_id)

        first = manager.update(
            frame_b, [{"track_id": 9, "bbox": bbox_b, "conf": 0.95}],
            now=5.0,
            reid_features={9: np.array([0.99, 0.04, 0.0, 0.0], dtype=np.float32)},
        )
        self.assertEqual(first[0]["track_id"], provisional_id)

        corrected = manager.update(
            frame_b, [{"track_id": 9, "bbox": bbox_b, "conf": 0.96}],
            now=6.0,
            reid_features={9: np.array([0.995, 0.03, 0.0, 0.0], dtype=np.float32)},
        )
        self.assertEqual(corrected[0]["track_id"], original_id)
        self.assertEqual(corrected[0]["identity_remapped_from"], provisional_id)


class CounterOcclusionTests(unittest.TestCase):
    def test_counts_after_track_temporarily_disappears(self):
        counter = DualZoneCounter(
            zone_a=[[0, 0], [120, 0], [120, 100], [0, 100]],
            zone_b=[[0, 120], [120, 120], [120, 230], [0, 230]],
            min_zone_hits=2,
            state_ttl_seconds=120,
        )
        in_a = {"track_id": 5, "bbox": [20, 10, 80, 80]}
        in_b = {"track_id": 5, "bbox": [20, 130, 80, 200]}
        counter.update([in_a])
        counter.update([in_a])
        counter.update([])
        counter.update([])
        self.assertEqual(counter.update([in_b]), [])
        events = counter.update([in_b])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "IN")
        self.assertEqual(counter.total_in, 1)

    def test_one_frame_zone_jitter_is_not_counted(self):
        counter = DualZoneCounter(
            zone_a=[[0, 0], [120, 0], [120, 100], [0, 100]],
            zone_b=[[0, 120], [120, 120], [120, 230], [0, 230]],
            min_zone_hits=2,
        )
        in_a = {"track_id": 3, "bbox": [20, 10, 80, 80]}
        in_b = {"track_id": 3, "bbox": [20, 130, 80, 200]}
        counter.update([in_a])
        counter.update([in_a])
        counter.update([in_b])
        counter.update([in_a])
        self.assertEqual(counter.total_in, 0)

    def test_remap_preserves_old_journey_and_provisional_zone_hits(self):
        counter = DualZoneCounter(
            zone_a=[[0, 0], [120, 0], [120, 100], [0, 100]],
            zone_b=[[0, 120], [120, 120], [120, 230], [0, 230]],
            min_zone_hits=2,
            state_ttl_seconds=120,
        )
        in_a = {"track_id": 6, "bbox": [20, 10, 80, 80]}
        in_b_temporary = {"track_id": 9, "bbox": [20, 130, 80, 200]}
        counter.update([in_a])
        counter.update([in_a])
        counter.update([in_b_temporary])

        events = counter.update([{
            "track_id": 6,
            "identity_remapped_from": 9,
            "bbox": [20, 130, 80, 200],
        }])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "IN")
        self.assertEqual(counter.total_in, 1)


if __name__ == "__main__":
    unittest.main()
