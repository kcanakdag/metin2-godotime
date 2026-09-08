import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from skill_tuning import apply_tuning


class SkillTuningTests(unittest.TestCase):
    def setUp(self):
        self.source = {"skills": [{"vnum": 2, "name": "Spin", "programs": {}}]}

    def test_formula_and_range_changes_leave_source_immutable(self):
        result = apply_tuning(
            self.source,
            {
                "schema_version": 1,
                "overrides": [
                    {"vnum": 2, "values": {"formula": "-(atk * (2 + k))", "splash_radius_cm": 350}}
                ],
            },
        )
        skill = result["skills"][0]
        self.assertEqual(skill["splash_radius_cm"], 350)
        self.assertTrue(skill["programs"]["formula"])
        self.assertNotIn("formula", self.source["skills"][0])
        self.assertEqual(self.source["skills"][0]["programs"], {})

    def test_invalid_overrides_cannot_change_mechanics_or_execute_code(self):
        for values in (
            {"handler": "script"},
            {"formula": "__import__('os')"},
            {"max_targets": 1000},
            {"max_targets": True},
            {"target_range_cm": -1},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                apply_tuning(
                    self.source, {"schema_version": 1, "overrides": [{"vnum": 2, "values": values}]}
                )
        row = {"vnum": 2, "values": {"name": "Tuned Spin"}}
        with self.assertRaises(ValueError):
            apply_tuning(self.source, {"schema_version": 1, "overrides": [row, row]})


if __name__ == "__main__":
    unittest.main()
