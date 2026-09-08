import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_browser_mobs import health_observed, matching_ground_drops


class FieldCombatEvidenceTests(unittest.TestCase):
    def test_death_survives_corpse_removal_from_current_rows(self):
        snapshot = {
            "monsters": [],
            "monster_health_history": [
                {"id": 900100, "life_sequence": 3, "health": 0, "observed_at_ticks_ms": 110}
            ],
        }
        self.assertTrue(health_observed(snapshot, 900100, 3, 100, 100, dead=True))
        self.assertTrue(health_observed(snapshot, 900100, 3, 100, 100))
        self.assertFalse(health_observed(snapshot, 900101, 3, 100, 100, dead=True))
        self.assertFalse(health_observed(snapshot, 900100, 4, 100, 100, dead=True))
        self.assertFalse(health_observed(snapshot, 900100, 3, 100, 110, dead=True))
        self.assertFalse(health_observed({}, 900100, 3, 100, 100, dead=True))

    def test_nonlethal_damage_does_not_establish_death(self):
        snapshot = {
            "monster_health_history": [
                {"id": 900100, "life_sequence": 3, "health": 80, "observed_at_ticks_ms": 110}
            ]
        }
        self.assertTrue(health_observed(snapshot, 900100, 3, 100, 100))
        self.assertFalse(health_observed(snapshot, 900100, 3, 100, 100, dead=True))
        self.assertFalse(health_observed(snapshot, 900100, 3, 80, 100))


class GroundDropEvidenceTests(unittest.TestCase):
    def test_all_owned_drop_kinds_need_matching_original_models(self):
        state = {
            "identity": "player",
            "loot": [{"id": 1, "owner": "player"}],
            "item_drops": [{"id": 1, "owner": "player"}],
            "drop_presentations": [
                {
                    "row_id": 1,
                    "item": item,
                    "label": label,
                    "ground_model_path": "res://assets/imported/ground_items/models/" + model,
                }
                for item, label, model in (
                    (False, "2 Yang", "coins.glb"),
                    (True, "Red Potion (S)", "bottle.glb"),
                )
            ],
        }
        self.assertTrue(matching_ground_drops(state, state))
        peer = copy.deepcopy(state)
        peer["drop_presentations"].pop()
        self.assertFalse(matching_ground_drops(state, peer))
        peer = copy.deepcopy(state)
        peer["drop_presentations"][0]["label"] = "wrong"
        self.assertFalse(matching_ground_drops(state, peer))
        peer["drop_presentations"][0]["ground_model_path"] = "res://placeholder.glb"
        self.assertFalse(matching_ground_drops(state, peer))
        state["identity"] = "someone_else"
        self.assertFalse(matching_ground_drops(state, peer))


if __name__ == "__main__":
    unittest.main()
