"""Berserk source metadata must survive the selected live content adapter."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from live_buff_skill import (
    aura_of_the_sword_metadata,
    berserk_metadata,
    self_buff_metadata,
    strong_body_metadata,
)


class LiveBuffSkillTests(unittest.TestCase):
    def source(self):
        row = [""] * 27
        for index, value in {
            0: "3",
            2: "1",
            6: "ATT_SPEED",
            7: "50*k",
            8: "50+140*k",
            9: "60+90*k",
            11: "63+90*k",
            14: "SELFONLY",
            15: "14",
            16: "MOV_SPEED",
            17: "20*k",
            18: "60+90*k",
            19: "14",
            22: "NORMAL",
            23: "1",
            25: "0",
            26: "0",
        }.items():
            row[index] = value
        return row

    def test_secondary_and_penalty_are_preserved_with_source_rank_tables(self):
        result = berserk_metadata(self.source(), [0, 5, 6, 12, 50])
        self.assertEqual(result["rank_costs"], [50, 57, 58, 66, 120])
        self.assertEqual(
            result["rank_cooldowns_us"], [x * 1_000_000 for x in [63, 67, 68, 73, 108]]
        )
        self.assertEqual(
            [m["point"] for m in result["buff"]["modifiers"]],
            [
                "attack_speed",
                "movement_speed",
                "normal_damage_taken_percent",
            ],
        )
        self.assertEqual(result["buff"]["modifiers"][2]["power_percent_factor"], 25)
        self.assertFalse(result["requires_target"])
        self.assertEqual(result["radius_m"], 0)

    def test_unsupported_source_semantics_and_out_of_bounds_values_reject(self):
        for index, value in [
            (0, "4"),
            (14, "ATTACK"),
            (16, "NONE"),
            (22, "MAGIC"),
            (10, "1"),
            (8, "-1"),
            (9, "0"),
            (18, "90000"),
        ]:
            row = self.source()
            row[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                berserk_metadata(row, [0, 5, 50])

    def test_aura_of_the_sword_preserves_attack_grade_and_rank_tables(self):
        row = [""] * 27
        for index, value in {
            0: "4",
            2: "1",
            6: "ATT_GRADE",
            7: "(100+str+lv*3)*k",
            8: "100+200*k",
            9: "30+50*k",
            11: "33+50*k",
            14: "SELFONLY",
            15: "15",
            16: "NONE",
            19: "15",
            22: "NORMAL",
            23: "1",
            25: "0",
            26: "0",
        }.items():
            row[index] = value
        result = aura_of_the_sword_metadata(row, [0, 5, 50])
        self.assertEqual(result["rank_costs"], [100, 110, 200])
        self.assertEqual(result["rank_cooldowns_us"], [x * 1_000_000 for x in [33, 35, 58]])
        self.assertEqual(result["buff"]["modifiers"][0]["point"], "attack_grade")
        self.assertEqual(result["buff_icon"], "skill/warrior/geomgyeong_03")
        self.assertEqual(
            self_buff_metadata(row, [0, 5, 50])["buff_icon"],
            "skill/warrior/geomgyeong_03",
        )

    def test_strong_body_preserves_defense_grade_and_movement_penalty(self):
        row = [""] * 27
        for index, value in {
            0: "19",
            2: "1",
            6: "DEF_GRADE",
            7: "(200+str*0.2+con*0.5)*k",
            8: "80+220*k",
            9: "60+90*k",
            11: "63+90*k",
            14: "SELFONLY",
            15: "16",
            16: "MOV_SPEED",
            17: "-(1+9*k)",
            18: "60+90*k",
            19: "16",
            22: "NORMAL",
            23: "1",
            25: "0",
            26: "0",
        }.items():
            row[index] = value
        result = strong_body_metadata(row, [0, 5, 50])
        self.assertEqual(result["rank_costs"], [80, 91, 190])
        self.assertEqual(result["rank_cooldowns_us"], [x * 1_000_000 for x in [63, 67, 108]])
        self.assertEqual(
            [m["point"] for m in result["buff"]["modifiers"]],
            ["defense_grade", "movement_speed"],
        )
        self.assertEqual(result["buff_icon"], "skill/warrior/cheongeun_03")

    def test_new_self_buff_source_semantics_reject(self):
        for metadata, vnum, index, value in [
            (aura_of_the_sword_metadata, "4", 6, "HP"),
            (aura_of_the_sword_metadata, "4", 22, "MAGIC"),
            (strong_body_metadata, "19", 16, "NONE"),
            (strong_body_metadata, "19", 7, "unsupported"),
        ]:
            row = [""] * 27
            row[0] = vnum
            row[2] = "1"
            row[index] = value
            with self.subTest(vnum=vnum, index=index), self.assertRaises(ValueError):
                metadata(row, [0, 5, 50])
