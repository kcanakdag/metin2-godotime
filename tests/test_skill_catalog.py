"""Skill formulas are a restricted data format, never executable expressions."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_skill_catalog import TERMS, compile_catalog, polynomial


class SkillCatalogTests(unittest.TestCase):
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
