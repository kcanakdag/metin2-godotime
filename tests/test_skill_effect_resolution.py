import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from resolve_skill_effects import joint_names, resolve_rows


class SkillEffectResolutionTests(unittest.TestCase):
    def test_only_skin_joints_count_as_attachment_bones(self):
        document = {"nodes": [{"name": "head"}, {"name": "decoration"}], "skins": [{"joints": [0]}]}
        self.assertEqual(joint_names(document), {"head"})
        document["skins"][0]["joints"] = [0, 0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            joint_names(document)
        document["skins"][0]["joints"] = [3]
        with self.assertRaisesRegex(ValueError, "index"):
            joint_names(document)

    def test_missing_original_bone_falls_back_but_conversion_loss_rejects(self):
        event = {"attachment": "follow_bone", "bone": "footsteps", "position_m": [0, 0, 0]}
        rows = [{"actor_id": "hero", "effects": [event], "rejected_effects": []}]
        result = resolve_rows(rows, {"hero": ({"head"}, {"head"})})
        self.assertEqual(result[0]["effects"][0]["attachment"], "follow_root")
        self.assertEqual(rows[0]["effects"][0]["attachment"], "follow_bone")
        with self.assertRaisesRegex(ValueError, "lost"):
            resolve_rows(rows, {"hero": ({"head", "footsteps"}, {"head"})})
        rows[0]["rejected_effects"] = [{"reason": "unsupported"}]
        with self.assertRaisesRegex(ValueError, "rejected"):
            resolve_rows(rows, {"hero": ({"head"}, {"head"})})
