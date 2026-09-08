import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mob_motions import compile_motion_groups, registered_action


class MobMotionTests(unittest.TestCase):
    def test_exact_registration_precedes_two_character_fallback(self):
        for source, expected in {
            "special": "special_1",
            "special1": "special_2",
            "special12": "special_2",
            "combo_attack2": "combo_3",
            "skill5": "skill_125",
            "wait20": "wait",
            "front_damage3": "front_damage",
            "command1": None,
            "special_attack21": None,
            "wait9999": None,
        }.items():
            with self.subTest(source=source):
                self.assertEqual(registered_action(source), expected)

    def test_ignored_rows_are_retained_and_reachable_weights_preserved(self):
        rows = [
            {"mode": "general", "action": action, "path": path, "weight": weight}
            for action, path, weight in (
                ("wait", "wait.msa", 70),
                ("wait20", "wait2.msa", 50),
                ("normal_attack", "attack.msa", 100),
                ("command1", "command.msa", 100),
            )
        ]
        before = copy.deepcopy(rows)
        groups, ignored = compile_motion_groups(rows)
        idle = next(g for g in groups if g["action"] == "wait")
        self.assertEqual(idle["weights"], [70, 30])
        self.assertEqual(ignored[0]["path"], "command.msa")
        self.assertEqual(ignored[0]["reason"], "unregistered-by-pinned-client-motion-loader")
        self.assertEqual(rows, before)

    def test_missing_idle_incomplete_weights_and_other_modes_reject(self):
        for mode, action, weight in (
            ("general", "command1", 100),
            ("general", "wait", 90),
            ("sword", "wait", 100),
        ):
            with (
                self.subTest(mode=mode, action=action, weight=weight),
                self.assertRaises(ValueError),
            ):
                compile_motion_groups(
                    [{"mode": mode, "action": action, "path": "wait.msa", "weight": weight}]
                )
