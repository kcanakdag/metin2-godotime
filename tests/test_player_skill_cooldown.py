"""Player UseSkill truncates seconds before converting to the runtime clock."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_class_skills import player_cooldown_us
from skill_formulas import rank_value


class PlayerSkillCooldownTests(unittest.TestCase):
    def test_berserk_and_aura_fractional_ranks_follow_player_source_order(self):
        self.assertEqual(player_cooldown_us(rank_value("63+90*k", 5)), 67_000_000)
        self.assertEqual(player_cooldown_us(rank_value("33+50*k", 5)), 35_000_000)
        self.assertEqual(player_cooldown_us(rank_value("63+90*k", 50)), 108_000_000)

    def test_boundaries_and_constant_attack_cooldowns(self):
        for seconds in [0, 7, 10, 12, 15, 25, 600]:
            self.assertEqual(player_cooldown_us(seconds), seconds * 1_000_000)
        self.assertEqual(player_cooldown_us(0.999), 0)
        self.assertEqual(player_cooldown_us(1.999), 1_000_000)

    def test_invalid_values_reject_before_truncation_can_hide_them(self):
        for seconds in [-0.1, 600.1, float("inf"), float("nan"), -float("inf")]:
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                player_cooldown_us(seconds)
