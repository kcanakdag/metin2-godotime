"""Character discovery boundaries without running legacy Python or Blender."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from character_definitions import (  # noqa: E402
    initial_points,
    registered_combo_chains,
    registered_motions,
)
from content_formats import parse_msa  # noqa: E402


def registrations() -> str:
    general = "\n".join(
        f'    chrmgr.RegisterCacheMotionData(mode, chr.MOTION_{name}, "{file}.msa")'
        for name, file in [
            ("WAIT", "wait"),
            ("WALK", "walk"),
            ("RUN", "run"),
            ("DAMAGE", "damage"),
            ("DAMAGE_BACK", "back"),
            ("DEAD", "dead"),
        ]
    )
    intro = "\n".join(
        f'    chrmgr.RegisterCacheMotionData(mode, chr.MOTION_INTRO_{name}, "{name.lower()}.msa")'
        for name in ["WAIT", "SELECTED", "NOT_SELECTED"]
    )
    melee = "\n".join(
        f'    chrmgr.RegisterCacheMotionData(chr.MOTION_MODE_ONEHAND_SWORD, chr.MOTION_{name}, "{name.lower()}.msa")'
        for name in [
            "WAIT",
            "WALK",
            "RUN",
            "DAMAGE",
            "DAMAGE_BACK",
            *[f"COMBO_ATTACK_{i}" for i in range(1, 5)],
        ]
    )
    return f"""def SetGeneralMotions(mode, folder):
{general}
def SetIntroMotions(mode, folder):
{intro}
def __LoadGameWarriorEx(race, path):
    SetGeneralMotions(chr.MOTION_MODE_GENERAL, path + "general/")
    chrmgr.SetMotionRandomWeight(chr.MOTION_MODE_GENERAL, chr.MOTION_WAIT, 0, 70)
    chrmgr.RegisterCacheMotionData(chr.MOTION_MODE_GENERAL, chr.MOTION_WAIT, "wait_1.msa", 30)
    chrmgr.RegisterCacheMotionData(chr.MOTION_MODE_GENERAL, chr.MOTION_COMBO_ATTACK_1, "attack.msa")
    chrmgr.SetPathName(path + "onehand_sword/")
{melee}
    chrmgr.RegisterAttachingBoneName(chr.PART_WEAPON, "equip_right_hand")
"""


class CharacterDefinitionTests(unittest.TestCase):
    def test_combo_registrations_preserve_order_and_reject_missing_or_duplicate_steps(self):
        prefix = "chr.MOTION_MODE_ONEHAND_SWORD, COMBO_TYPE_1, "
        source = registrations() + f"    chrmgr.ReserveComboAttackNew({prefix}4)\n"
        lines = [
            f"    chrmgr.RegisterComboAttackNew({prefix}COMBO_INDEX_{i}, chr.MOTION_COMBO_ATTACK_{i})\n"
            for i in range(1, 5)
        ]
        source += "".join(lines)
        self.assertEqual(
            registered_combo_chains(source, "Warrior", "onehand"),
            [[f"combo_{i}" for i in range(1, 5)]],
        )
        for changed in [
            source.replace(lines[1], ""),
            source + lines[1],
            source.replace("COMBO_INDEX_2", "COMBO_INDEX_3"),
            source.replace("MOTION_COMBO_ATTACK_4)", "MOTION_COMBO_ATTACK_8)"),
        ]:
            with self.assertRaises(ValueError):
                registered_combo_chains(changed, "Warrior", "onehand")

    def test_source_paths_weights_fallback_and_bones_are_retained(self):
        modes, bones = registered_motions(registrations(), "Warrior")
        indexed = {mode["id"]: {row["action"]: row for row in mode["motions"]} for mode in modes}
        self.assertEqual(indexed["general"]["wait"]["weights"], [70, 30])
        self.assertEqual(
            indexed["general"]["wait"]["files"], ["general/wait.msa", "general/wait_1.msa"]
        )
        self.assertEqual(indexed["onehand"]["death"]["files"], ["general/dead.msa"])
        self.assertEqual(indexed["onehand"]["death"]["fallback_mode"], "general")
        self.assertEqual(indexed["intro"]["selected"]["files"], ["intro/selected.msa"])
        self.assertEqual(bones, {"weapon_right": "equip_right_hand"})

    def test_missing_animation_and_computed_filename_fail_closed(self):
        source = registrations()
        for changed in [
            source.replace('"run.msa"', '"missing" + suffix'),
            source.replace('"combo_attack_4.msa"', '"combo" + suffix'),
        ]:
            with self.assertRaisesRegex(ValueError, "Incomplete motions"):
                registered_motions(changed, "Warrior")

    def test_comments_and_other_functions_cannot_supply_a_missing_attachment(self):
        source = registrations().replace(
            "    chrmgr.RegisterAttachingBoneName", "# chrmgr.RegisterAttachingBoneName"
        )
        source += (
            '\ndef unrelated():\n    chrmgr.RegisterAttachingBoneName(chr.PART_WEAPON, "fake")\n'
        )
        with self.assertRaisesRegex(ValueError, "Missing original weapon"):
            registered_motions(source, "Warrior")

    def test_initial_points_require_complete_positive_records(self):
        row = "{6,4,3,3,600,200,40,20,36,44,18,22,800,5,1,3}"
        source = (
            "TJobInitialPoints JobInitialPoints[JOB_MAX_NUM] = /* { documentation } */ {"
            + ",".join([row] * 4)
            + "};"
        )
        points = initial_points(source)
        self.assertEqual(points[0]["base_hp"], 600)
        self.assertEqual(points[0]["intelligence"], 3)
        for changed in [source.replace("600", "-1"), source.replace(row, "{6}", 1)]:
            with self.assertRaises(ValueError):
                initial_points(changed)

    def test_presentation_adapter_records_post_clip_bounds_without_weakening_default(self):
        source = """ScriptType MotionData
MotionFileName "ymir work/pc/example/attack.gr2"
MotionDuration 1.000000
Group ComboInputData
{
 PreInputTime 0.3
 DirectInputTime 0.6
 InputLimitTime 1.1
 LinkTime -431602080.000000
}
"""
        with self.assertRaises(ValueError):
            parse_msa(source)
        with self.assertRaisesRegex(ValueError, "exceeds clip"):
            parse_msa(source, ignore_legacy_link_time=True)
        parsed = parse_msa(source, ignore_legacy_link_time=True, allow_post_clip_combo=True)
        self.assertIsNone(parsed["combo"]["link_us"])
        self.assertEqual(parsed["combo"]["input_limit_us"], 1_100_000)
        self.assertEqual(parsed["unsupported"][0]["kind"], "post_clip_combo")
        with self.assertRaises(ValueError):
            parse_msa(
                source.replace("0.3", "nan"),
                ignore_legacy_link_time=True,
                allow_post_clip_combo=True,
            )


if __name__ == "__main__":
    unittest.main()
