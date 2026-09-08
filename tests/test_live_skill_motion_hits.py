"""Preserve ordered authored skill areas and the legacy single-window output."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_skill_catalog import motion_hits  # noqa: E402


class MotionHitTests(unittest.TestCase):
    def test_areas_retain_geometry_and_order(self):
        events = [
            {
                "kind": "attack_area",
                "start_us": start,
                "end_us": start + 20,
                "spheres": [{"position_m": [0, 1, -2], "radius_m": radius}],
            }
            for start, radius in [(10, 1.2), (40, 1.2), (70, 1.7)]
        ]
        fields = motion_hits({"duration_us": 100, "events": events}, "physical_area_v1")
        assert fields["hit_geometry"] == events
        assert fields["hit_windows_us"] == [[10, 30], [40, 60], [70, 90]]
        assert (fields["hit_start_us"], fields["hit_end_us"]) == (10, 90)
        with self.assertRaises(ValueError):
            motion_hits({"duration_us": 100, "events": events[::-1]}, "physical_area_v1")
        with self.assertRaises(ValueError):
            motion_hits({"duration_us": 50, "events": events}, "physical_area_v1")

    def test_legacy_output_remains_unchanged_and_mismatched_kind_rejects(self):
        motion = {
            "duration_us": 100,
            "events": [{"kind": "attack_window", "start_us": 10, "end_us": 90}],
        }
        assert motion_hits(motion, "physical_splash_v1") == {"hit_start_us": 10, "hit_end_us": 90}
        with self.assertRaises(ValueError):
            motion_hits(motion, "physical_area_v1")
