import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mob_model_sharing import expand_report, share_models, unique_actors


def actor(vnum, texture="dog.dds"):
    identity = f"actor.mob.dog-{vnum}"
    return {
        "id": identity,
        "vnum": vnum,
        "name": f"Dog {vnum}",
        "model_key": "dog",
        "kind": "mob",
        "output": f"actors/dog-{vnum}.glb",
        "source_model": "dog.gr2",
        "material_texture_bindings": {"body": texture},
        "modes": [
            {
                "id": "general",
                "motions": [
                    {
                        "action_id": identity + ".general.wait",
                        "godot_name": f"dog_{vnum}_wait",
                        "action": "wait",
                        "duration_us": 1000000,
                        "weight": 100,
                        "source_gr2": "wait.gr2",
                    }
                ],
            }
        ],
    }


def report(owners):
    return {
        "status": "converted",
        "artifacts": [
            {
                "id": a["id"],
                "relative_path": a["output"],
                "sha256": str(a["vnum"]),
                "motions": [
                    {
                        "action_id": m["action_id"],
                        "godot_name": m["godot_name"],
                        "duration_us": m["duration_us"],
                    }
                    for m in a["modes"][0]["motions"]
                ],
            }
            for a in owners
        ],
    }


class MobModelSharingTests(unittest.TestCase):
    def test_identical_inputs_share_model_but_keep_definition_and_action_ids(self):
        source = [actor(171), actor(101), actor(104, "blue.dds")]
        before = copy.deepcopy(source)
        shared = share_models(source)
        owners = unique_actors(shared)
        self.assertEqual(len(owners), 2)
        self.assertEqual(shared[0]["output"], shared[1]["output"])
        self.assertNotEqual(shared[0]["id"], shared[1]["id"])
        self.assertNotEqual(
            shared[0]["modes"][0]["motions"][0]["action_id"],
            shared[1]["modes"][0]["motions"][0]["action_id"],
        )
        expanded = expand_report(shared, report(owners))
        self.assertEqual(len(expanded["artifacts"]), 3)
        self.assertEqual(expanded["unique_model_count"], 2)
        self.assertEqual(expanded["artifacts"][0]["sha256"], expanded["artifacts"][1]["sha256"])
        self.assertEqual(source, before)
        reordered = share_models(list(reversed(source)))
        self.assertEqual({a["id"]: a for a in shared}, {a["id"]: a for a in reordered})

    def test_future_render_fields_and_motion_changes_prevent_sharing(self):
        for key in ("new_render_setting", "duration"):
            second = actor(171)
            if key == "duration":
                second["modes"][0]["motions"][0]["duration_us"] = 2000000
            else:
                second[key] = True
            self.assertEqual(len(unique_actors(share_models([actor(101), second]))), 2)

    def test_alias_and_report_tampering_rejects(self):
        for change in ("owner", "texture", "clip", "report_duration", "report_missing"):
            shared = share_models([actor(101), actor(171)])
            evidence = report(unique_actors(shared))
            if change == "owner":
                shared[1]["shared_model_actor_id"] = "missing"
            elif change == "texture":
                shared[1]["material_texture_bindings"]["body"] = "wrong.dds"
            elif change == "clip":
                shared[1]["modes"][0]["motions"][0]["godot_name"] = "wrong"
            elif change == "report_duration":
                evidence["artifacts"][0]["motions"][0]["duration_us"] += 1
            else:
                evidence["artifacts"] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                expand_report(shared, evidence)
