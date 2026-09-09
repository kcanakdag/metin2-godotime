"""Class skill discovery and bounded arithmetic compiler regressions."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_class_skills import skill_handler
from skill_definitions import CLASSES, classic_skill_ids, registered_skills, source_rows
from skill_formulas import compile_formula


class SkillDefinitionTests(unittest.TestCase):
    def test_dash_keeps_its_two_phase_handler(self):
        source = {
            "vnum": 5,
            "flags": ["ATTACK", "USE_MELEE_DAMAGE"],
            "secondary_point": "MOV_SPEED",
            "point": "HP",
        }
        self.assertEqual(skill_handler(source), "charge")
        self.assertEqual(skill_handler({**source, "vnum": 1}), "damage")
        with self.assertRaisesRegex(ValueError, "charge metadata"):
            skill_handler({**source, "secondary_point": "NONE"})

    def registrations(self, class_id):
        lines = [f"def __LoadGame{CLASSES[class_id]}Ex(race, path):"]
        for vnum in classic_skill_ids(class_id):
            offset = vnum - class_id * 30
            lines.append(
                f'    chrmgr.RegisterCacheMotionData(chr.MOTION_MODE_GENERAL, chr.MOTION_SKILL+(i*skill.SKILL_GRADEGAP)+{offset}, "motion_{vnum}" + END_STRING + ".msa")'
            )
        return "\n".join(lines) + "\n"

    def test_all_eight_trees_map_class_local_motion_offsets(self):
        settings = "\n".join(self.registrations(c) for c in range(4))
        found = {}
        for class_id in range(4):
            found.update(registered_skills(settings, class_id))
        self.assertEqual(len(found), 44)
        self.assertEqual(found[111], "skill/motion_111.msa")
        self.assertNotIn(6, found)
        self.assertNotIn(36, found)

    def test_missing_duplicate_or_dynamic_motion_fails_closed(self):
        source = self.registrations(0)
        for modified in (
            source.replace('"motion_1"', "get_motion()"),
            source + source.splitlines()[1] + "\n",
            source.replace('+2, "motion_2"', '+99, "motion_2"'),
        ):
            with self.assertRaises(ValueError):
                registered_skills(modified, 0)
        with self.assertRaises(ValueError):
            classic_skill_ids(True)
        with self.assertRaises(ValueError):
            source_rows("1\ta\n1\tb")

    def test_skill_arithmetic_supports_source_math_without_general_execution(self):
        program = compile_formula("-(atk + number(iq*5, iq*15))*ar*k + floor(2+k*6)")
        self.assertIn({"op": "number"}, program)
        self.assertIn({"op": "floor"}, program)
        self.assertEqual(compile_formula(""), [{"op": "constant", "value": 0.0}])
        for formula in (
            "eval('1')",
            "open('secret')",
            "number.__call__(1, 2)",
            "iq[0]",
            "number(1, 2, 3)",
            "floor(x=1)",
            "2**32",
            "True",
            "1e309",
            "a",
            "atk; print(1)",
            "+" * 30 + "1",
            "1+" * 200 + "1",
        ):
            with self.subTest(formula=formula), self.assertRaises(ValueError):
                compile_formula(formula)


if __name__ == "__main__":
    unittest.main()
