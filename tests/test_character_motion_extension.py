import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_character_catalog import verify_motion_extension


class MotionExtensionTests(unittest.TestCase):
    def fixture(self):
        return {
            "actors": [
                {
                    "id": "warrior",
                    "forward": "-Z",
                    "attachment_bones": {"sword": "hand"},
                    "modes": [
                        {
                            "id": "general",
                            "motions": [{"action_id": "idle", "duration_us": 100, "events": []}],
                        }
                    ],
                }
            ]
        }

    def test_new_motion_preserves_existing_contract(self):
        previous = self.fixture()
        candidate = copy.deepcopy(previous)
        candidate["actors"][0]["modes"][0]["motions"].append({"action_id": "skill_1"})
        self.assertEqual(verify_motion_extension(previous, candidate), 1)

    def test_removal_and_changed_motion_or_attachment_reject(self):
        previous = self.fixture()
        for change in ("actor", "mode", "motion", "duration", "attachment", "equipment"):
            candidate = copy.deepcopy(previous)
            actor = candidate["actors"][0]
            mode = actor["modes"][0]
            if change == "actor":
                candidate["actors"] = []
            elif change == "mode":
                actor["modes"] = []
            elif change == "motion":
                mode["motions"] = []
            elif change == "duration":
                mode["motions"][0]["duration_us"] = 101
            elif change == "attachment":
                actor["attachment_bones"]["sword"] = "other_hand"
            else:
                mode["required_item_vnums"] = [10]
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_motion_extension(previous, candidate)
