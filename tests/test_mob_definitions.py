import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mob_definitions import normalize, records


class MobDefinitionsTests(unittest.TestCase):
    def row(self):
        fields = """ST DX HT IQ DAMAGE_MIN DAMAGE_MAX DEF ATTACK_RANGE AGGRESSIVE_SIGHT
        AGGRESSIVE_HP_PCT REGEN_CYCLE REGEN_PERCENT EXP GOLD_MIN GOLD_MAX DROP_ITEM
        RESIST_SWORD RESIST_FAN ENCHANT_POISON SKILL_LEVEL0 SKILL_VNUM0 SP_BERSERK""".split()
        return {
            **dict.fromkeys(fields, "0"),
            "VNUM": "102",
            "TYPE": "MONSTER",
            "LEVEL": "3",
            "MAX_HP": "162",
            "ATTACK_SPEED": "100",
            "MOVE_SPEED": "100",
            "DAM_MULTIPLY": "1.5",
            "AI_FLAG": "",
            "RACE_FLAG": "ANIMAL",
            "IMMUNE_FLAG": "",
            "FOLDER": "wolf",
            "RANK": "PAWN",
            "BATTLE_TYPE": "MELEE",
            "SIZE": "SMALL",
        }

    def compile(self, row):
        return normalize(row, actor_id="actor.mob.wolf-102", name="Wolf", model_key="wolf")

    def test_preserves_original_stats_and_unimplemented_mechanics(self):
        row = self.row()
        row.update(ENCHANT_POISON="15", RESIST_FAN="50", SKILL_LEVEL0="", SKILL_VNUM0="")
        result = self.compile(row)
        self.assertEqual(result["stats"]["max_hp"], 162)
        self.assertEqual(result["stats"]["damage_multiplier"], 1.5)
        self.assertEqual(result["combat_modifiers"]["enchant_poison"], 15)
        self.assertEqual(result["combat_modifiers"]["resist_fan"], 50)
        self.assertEqual(result["flags"]["race_flag"], ["ANIMAL"])
        self.assertIsNone(result["special_mechanics"]["skill_level0"])

    def test_invalid_stats_flags_and_non_monsters_fail(self):
        for key, value in (
            ("TYPE", "NPC"),
            ("MAX_HP", "0"),
            ("LEVEL", "3.5"),
            ("DAM_MULTIPLY", "NaN"),
            ("DAM_MULTIPLY", "inf"),
            ("DAMAGE_MIN", "1"),
            ("GOLD_MIN", "1"),
            ("AI_FLAG", "AGGR,AGGR"),
            ("RESIST_FAN", "101"),
            ("SKILL_LEVEL0", "not-a-number"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.compile({**self.row(), key: value})

    def test_duplicate_identity_columns_and_malformed_table_rows_fail(self):
        self.assertEqual(records("VNUM\tTYPE\n102\tMONSTER\n")[102]["TYPE"], "MONSTER")
        for source in (
            "VNUM\tVNUM\n102\t102\n",
            "VNUM\tTYPE\n102\tMONSTER\n102\tMONSTER\n",
            "VNUM\tTYPE\n102\n",
            "VNUM\tTYPE\n102\tMONSTER\textra\n",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                records(source)


if __name__ == "__main__":
    unittest.main()
