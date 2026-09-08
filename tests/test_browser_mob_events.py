import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_browser_mobs import health_observed


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


if __name__ == "__main__":
    unittest.main()
