"""Skill formulas are a restricted data format, never executable expressions."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_skill_catalog import TERMS, charge_metadata, compile_catalog, polynomial


class SkillCatalogTests(unittest.TestCase):
    def test_charge_keeps_secondary_policy_and_both_source_weapons(self):
        row = [""] * 27
        for index, value in {
            0: "5",
            2: "1",
            14: "ATTACK,USE_MELEE_DAMAGE,SPLASH,CRUSH",
            16: "MOV_SPEED",
            17: "150",
            18: "3",
        }.items():
            row[index] = value
        desc = [""] * 13
        desc[10] = "ATTACK_SKILL|NEED_TARGET|CHARGE_ATTACK|WEAPON_LIMITATION"
        desc[11] = "SWORD|TWO_HANDED"
        self.assertEqual(
            charge_metadata(row, desc),
            {
                "requires_target": True,
                "target_range_m": 1.7,
                "charge": {
                    "duration_us": 3_000_000,
                    "speed_bonus": 150,
                    "push_distance_m": 2.0,
                    "main_target_stun_us": 4_000_000,
                },
            },
        )
        for index, value in [
            (0, "1"),
            (16, "HP"),
            (17, "150*k"),
            (17, "1.5"),
            (17, "-1"),
            (18, "0"),
            (18, "0.0000001"),
            (18, "601"),
            (14, "ATTACK,USE_MELEE_DAMAGE"),
        ]:
            bad = list(row)
            bad[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                charge_metadata(bad, desc)
        bad_desc = list(desc)
        bad_desc[11] = "SWORD"
        with self.assertRaises(ValueError):
            charge_metadata(row, bad_desc)

    def test_original_damage_and_sp_compile_to_coefficients(self):
        parsed = polynomial("-(3*atk+(0.8*atk+str*5+dex*3+con)*k)")
        self.assertEqual(
            [round(-parsed.get(term, 0) * 1000) for term in TERMS],
            [0, 3000, 800, 5000, 3000, 1000],
        )
        self.assertEqual(polynomial("50+130*k"), {(): 50, ("k",): 130})

    def test_executable_or_unbounded_formulas_fail_closed(self):
        for formula in (
            "__import__('os').system('true')",
            "atk.__class__",
            "atk[0]",
            "[atk for x in k]",
            "atk**2",
            "atk/k",
            "atk*k*k",
            "10001",
            "1e309",
            "True",
            "unknown + 1",
            "1" * 257,
        ):
            with self.subTest(formula=formula), self.assertRaises(ValueError):
                polynomial(formula)

    def test_empty_or_unbounded_profiles_reject_before_reading_assets(self):
        for skills in ([], {}, [{}] * 65):
            with self.assertRaises(ValueError):
                compile_catalog({"schema_version": 1, "skills": skills}, offline=True)


if __name__ == "__main__":
    unittest.main()
