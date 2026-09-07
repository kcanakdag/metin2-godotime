# ruff: noqa: E402, I001

import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from test_browser_finisher import FRONT_KNOCKDOWN, _force_render_observation


class FinisherRenderedForceTests(unittest.TestCase):
    def setUp(self):
        self.start = {
            "id": 2,
            "life_sequence": 5,
            "attack_sequence": 67,
            "action_started_at_us": 123456789,
            "attack_action_id": FRONT_KNOCKDOWN,
            "x": 3.25,
            "y": 0.0,
            "z": 9.0,
        }
        self.snapshot = {
            "monsters": [{**self.start, "z": 7.0}],
            "rendered_monsters": [
                {
                    "row_id": 2,
                    "attack_sequence": 67,
                    "action_id": FRONT_KNOCKDOWN,
                    "position": [3.25, 0.0, 7.4],
                }
            ],
        }

    def test_smoothing_can_follow_force_without_matching_the_moving_endpoint(self):
        proof = _force_render_observation(self.snapshot, self.start)
        self.assertTrue(proof["valid"])
        self.assertAlmostEqual(proof["rendered_along_m"], 1.6)
        self.assertAlmostEqual(proof["lag_m"], 0.4)

    def test_static_off_path_ahead_and_excessively_delayed_renderers_fail(self):
        for point in (
            [3.25, 0.0, 9.0],
            [3.5, 0.0, 7.4],
            [3.25, 0.0, 6.8],
            [3.25, 0.0, 8.4],
            [math.nan, 0.0, 7.4],
        ):
            with self.subTest(position=point):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["rendered_monsters"][0]["position"] = point
                self.assertFalse(_force_render_observation(snapshot, self.start)["valid"])

    def test_stale_life_or_action_cannot_supply_motion_evidence(self):
        for key in ("life_sequence", "attack_sequence", "action_started_at_us"):
            with self.subTest(field=key):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["monsters"][0][key] += 1
                self.assertFalse(_force_render_observation(snapshot, self.start)["valid"])

    def test_wrong_rendered_action_or_sequence_is_rejected(self):
        for key, value in (("attack_sequence", 66), ("action_id", "wait")):
            with self.subTest(field=key):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["rendered_monsters"][0][key] = value
                self.assertFalse(_force_render_observation(snapshot, self.start)["valid"])

    def test_server_motion_alone_does_not_prove_rendered_motion(self):
        self.snapshot["rendered_monsters"] = []
        self.assertFalse(_force_render_observation(self.snapshot, self.start)["valid"])


if __name__ == "__main__":
    unittest.main()
