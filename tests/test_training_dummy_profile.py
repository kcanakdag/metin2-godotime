import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from training_dummy_profile import validate_profile

ROOT = Path(__file__).resolve().parents[1]


class TrainingDummyProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "content/profiles/training-dummy.json").read_text())

    def test_authored_and_custom_profiles(self):
        validate_profile(self.profile)
        self.profile.update(health=600, height_m=2.2, sword_resistance_percent=50)
        self.profile["colors"]["target"] = [0.1, 0.2, 0.8, 1]
        validate_profile(self.profile)

    def test_malformed_dimensions_stats_and_identity(self):
        for key, value in (
            ("health", True),
            ("health", 65536),
            ("health", 10.5),
            ("height_m", float("nan")),
            ("body_radius_m", float("inf")),
            ("height_m", 0.1),
            ("id", "actor.training."),
            ("name", "bad\nname"),
            ("respawn_ms", -1),
            ("fan_resistance_percent", 101),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_profile({**self.profile, key: value})

    def test_typos_colors_and_placement_collisions(self):
        bad = copy.deepcopy(self.profile)
        bad["heatlh"] = 600
        with self.assertRaises(ValueError):
            validate_profile(bad)
        for color in ([1, 1, 1], [1, 1, float("nan"), 1], [1, 1, 2, 1], [True, 0, 0, 1]):
            bad = copy.deepcopy(self.profile)
            bad["colors"]["wood"] = color
            with self.subTest(color=color), self.assertRaises(ValueError):
                validate_profile(bad)
        for row in (
            self.profile["placements"][0],
            {"map_id": "training", "id": 900002, "home_x": float("inf"), "home_z": 0},
            {"map_id": "training", "id": 900002, "home_x": 0, "home_z": 0, "typo": 1},
        ):
            bad = copy.deepcopy(self.profile)
            bad["placements"].append(row)
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_profile(bad)


if __name__ == "__main__":
    unittest.main()
