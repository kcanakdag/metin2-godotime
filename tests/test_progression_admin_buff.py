"""Focused self-buff capture tests for the live progression harness."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from progression_operator import OperatorError
from skill_formulas import VARIABLES
from test_progression_admin import buff_expectation


def _constant(value: float) -> list[dict[str, object]]:
    return [{"op": "constant", "value": float(value)}]


def _variable(name: str) -> list[dict[str, object]]:
    return [{"op": "variable", "index": VARIABLES.index(name)}]


def _multiply(left: list[dict[str, object]], right: list[dict[str, object]]):
    return [*left, *right, {"op": "mul"}]


class ProgressionAdminBuffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.characters = self.root / "characters.json"
        self.characters.write_text(
            json.dumps(
                {
                    "classes": [
                        {
                            "class_id": 0,
                            "initial_points": {
                                "strength": 6,
                                "dexterity": 3,
                                "vitality": 4,
                                "intelligence": 3,
                            },
                        }
                    ]
                }
            )
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _catalog(
        self,
        *,
        power_percent: list[int],
        rank_costs: list[int],
        rank_cooldowns_us: list[int],
        cost: list[dict[str, object]],
        duration: list[dict[str, object]],
        value_factor: int = 50,
    ) -> Path:
        catalog = {
            "schema": "mt2spacetime.skills",
            "rank_power_percent": power_percent,
            "skills": [
                {
                    "vnum": 3,
                    "class_id": 0,
                    "name": "Berserk",
                    "motion": "skill_3",
                    "handler": "self_buff_v1",
                    "rank_costs": rank_costs,
                    "rank_cooldowns_us": rank_cooldowns_us,
                    "buff": {
                        "sp_cost": cost,
                        "cooldown": _constant(108),
                        "modifiers": [
                            {
                                "point": "attack_speed",
                                "power_percent_factor": value_factor,
                                "duration": duration,
                            }
                        ],
                    },
                }
            ],
        }
        path = self.root / "skills.json"
        path.write_text(json.dumps(catalog))
        return path

    def test_level_and_rank_drive_the_capture(self):
        catalog = self._catalog(
            power_percent=[0, 5] + [0] * 18 + [50],
            rank_costs=[0, 5] + [0] * 18 + [50],
            rank_cooldowns_us=[0, 108_000_000] + [0] * 18 + [108_000_000],
            cost=_multiply(_variable("k"), _constant(100)),
            duration=_multiply(_variable("lv"), _constant(5)),
        )

        rank_one = buff_expectation(catalog, 3, 5, 1, self.characters)
        self.assertEqual(rank_one["level"], 5)
        self.assertEqual(rank_one["rank"], 1)
        self.assertEqual(rank_one["cost"], 5)
        self.assertEqual(rank_one["duration_ticks"], 25)
        self.assertEqual(rank_one["effects"], {"attack_speed": 2})

        rank_twenty = buff_expectation(catalog, 3, 20, 20, self.characters)
        self.assertEqual(rank_twenty["level"], 20)
        self.assertEqual(rank_twenty["rank"], 20)
        self.assertEqual(rank_twenty["cost"], 50)
        self.assertEqual(rank_twenty["duration_ticks"], 100)
        self.assertEqual(rank_twenty["effects"], {"attack_speed": 25})

    def test_rank_power_uses_binary32_before_formula_evaluation(self):
        # 0.29f * 100 is 28.999999..., so truncation yields 28. A binary64
        # evaluation would yield 29 and fail the compiled rank-cost agreement.
        catalog = self._catalog(
            power_percent=[0] * 20 + [29],
            rank_costs=[0] * 20 + [28],
            rank_cooldowns_us=[0] * 20 + [108_000_000],
            cost=_multiply(_variable("k"), _constant(100)),
            duration=_constant(10),
            value_factor=100,
        )

        capture = buff_expectation(catalog, 3, 20, 20, self.characters)
        self.assertEqual(capture["cost"], 28)
        self.assertEqual(capture["effects"], {"attack_speed": 29})

    def test_out_of_bounds_level_or_rank_rejects(self):
        catalog = self._catalog(
            power_percent=[0, 5] + [0] * 19,
            rank_costs=[0, 5] + [0] * 19,
            rank_cooldowns_us=[0, 108_000_000] + [0] * 19,
            cost=_constant(5),
            duration=_constant(10),
        )

        for level, rank in ((0, 1), (100, 1), (20, 0), (20, 21)):
            with self.subTest(level=level, rank=rank), self.assertRaises(OperatorError):
                buff_expectation(catalog, 3, level, rank, self.characters)


if __name__ == "__main__":
    unittest.main()
