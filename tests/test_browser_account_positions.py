# ruff: noqa: E402, I001

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from browser_snapshot import (
    POSITION_INVALID,
    POSITION_PENDING,
    POSITION_VALID,
    authoritative_position_distance,
    subscribed_player_position,
)


class SubscribedPlayerPositionTests(unittest.TestCase):
    def test_actual_origin_is_a_valid_position(self):
        snapshot = {"player_rows": [{"identity": "self", "online": True, "x": 0, "y": 0.0, "z": 0}]}

        self.assertEqual(
            subscribed_player_position(snapshot, "self"),
            (POSITION_VALID, [0.0, 0.0, 0.0]),
        )

    def test_subscribed_row_is_valid_while_local_rendered_actor_is_missing(self):
        snapshot = {
            "server_position": [0, 0, 0],
            "actor_presentations": [{"identity": "peer"}],
            "rendered_actors": [{"identity": "peer", "position": [1, 2, 3]}],
            "player_rows": [
                {
                    "identity": "self",
                    "online": True,
                    "x": 657.9979,
                    "y": 198.625,
                    "z": 575,
                }
            ],
        }

        self.assertEqual(
            subscribed_player_position(snapshot, "self"),
            (POSITION_VALID, [657.9979, 198.625, 575.0]),
        )

    def test_missing_or_offline_own_row_is_pending(self):
        fixtures = (
            {},
            {"player_rows": []},
            {"player_rows": [{"identity": "peer", "online": True, "x": 0, "y": 0, "z": 0}]},
            {"player_rows": [{"identity": "self", "online": False, "x": 0, "y": 0, "z": 0}]},
        )

        for snapshot in fixtures:
            with self.subTest(snapshot=snapshot):
                self.assertEqual(
                    subscribed_player_position(snapshot, "self"),
                    (POSITION_PENDING, None),
                )

    def test_invalid_coordinates_are_rejected(self):
        invalid_values = (math.nan, math.inf, -math.inf, "0", None, True)

        for axis in ("x", "y", "z"):
            for invalid in invalid_values:
                row = {"identity": "self", "online": True, "x": 0, "y": 0, "z": 0}
                row[axis] = invalid
                with self.subTest(axis=axis, invalid=invalid):
                    self.assertEqual(
                        subscribed_player_position({"player_rows": [row]}, "self"),
                        (POSITION_INVALID, None),
                    )

    def test_authoritative_drift_includes_vertical_movement(self):
        self.assertAlmostEqual(
            authoritative_position_distance([10.0, 20.0, 30.0], [10.0, 20.2, 30.0]),
            0.2,
        )


if __name__ == "__main__":
    unittest.main()
