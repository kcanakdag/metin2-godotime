import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_browser_npcs import area_population_matches, population_matches


class TownPopulationEvidenceTests(unittest.TestCase):
    def test_area_npcs_require_matching_positions_inside_original_bounds(self):
        areas = [{"spawn_id": "npc-a", "name": "Teacher", "bounds_cm": [100, 200, 300, 400]}]
        row = {
            "spawn_id": "npc-a",
            "name": "Teacher",
            "position": [1.25, 9, 2.5],
            "yaw": 1.5,
            "playing": True,
            "idle": "wait",
        }
        snapshot = {"rendered_npcs": [row]}
        self.assertTrue(area_population_matches(snapshot, snapshot, areas))
        for change in (
            {"position": [4, 9, 2.5]},
            {"position": [1.26, 9, 2.5]},
            {"position": [1.25, float("nan"), 2.5]},
            {"yaw": 1.6},
            {"playing": False},
            {"name": "Wrong"},
        ):
            other = {"rendered_npcs": [{**row, **change}]}
            with self.subTest(change=change):
                self.assertFalse(area_population_matches(snapshot, other, areas))
        self.assertFalse(area_population_matches(snapshot, {"rendered_npcs": []}, areas))

    def test_missing_stale_and_nonfinite_presentations_fail(self):
        expected = [{"spawn_id": "npc-a", "name": "Teacher", "position": [1, 2, 3], "yaw": 0}]
        actor = {**expected[0], "playing": True, "idle": "wait"}
        self.assertTrue(population_matches({"rendered_npcs": [actor]}, expected))
        self.assertFalse(population_matches({"rendered_npcs": []}, expected))
        for change in (
            {"name": "Wrong"},
            {"playing": False},
            {"idle": ""},
            {"position": [1, 2, 4]},
            {"position": [1, float("nan"), 3]},
            {"yaw": 0.5},
            {"yaw": float("nan")},
        ):
            with self.subTest(change=change):
                row = {**copy.deepcopy(actor), **change}
                self.assertFalse(population_matches({"rendered_npcs": [row]}, expected))
        with self.assertRaises(AssertionError):
            population_matches({"rendered_npcs": [actor, actor]}, expected)
