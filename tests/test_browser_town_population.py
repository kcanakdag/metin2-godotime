import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_browser_npcs import (
    area_population_matches,
    own_quest_rows_complete,
    population_matches,
    replay_stable_signature,
)


def idle_snapshot(**changes):
    """One settled idle account with its whole seeded opening catalog."""
    states = [
        {"quest_id": "main_quest_lv1", "sequence": 3, "state": "gototeacher", "title": "Welcome"},
        {"quest_id": "main_quest_lv2", "sequence": 1, "state": "run", "title": "Letter"},
        {"quest_id": "main_quest_lv3", "sequence": 1, "state": "run", "title": "News"},
        {"quest_id": "find_squareguard", "sequence": 2, "state": "find", "title": "Guardian:"},
    ]
    objectives = [
        {"quest_id": "main_quest_lv1", "label": "Find the City Guard", "letter_title": "Welcome"},
        {"quest_id": "find_squareguard", "label": "Guardian:", "letter_title": "Guardian:"},
    ]
    snapshot = {
        "connection_state": "connected",
        "world_info": {"map_id": "metin2_map_a1"},
        "quest_states": states,
        "quest_objectives": objectives,
        "rendered_npcs": [{"spawn_id": "npc-guard", "screen": [10, 20]}],
    }
    snapshot.update(changes)
    return snapshot


class TownPopulationEvidenceTests(unittest.TestCase):
    def test_area_npcs_require_matching_positions_inside_original_bounds(self):
        areas = [{"spawn_id": "npc-a", "name": "Teacher", "bounds_cm": [100, 200, 300, 400]}]
        row = {
            "spawn_id": "npc-a",
            "name": "Teacher",
            "position": [1.25, 9, 2.5],
            "yaw": 1.5,
            "playing": True,
            "idle": "wait",
        }
        snapshot = {"rendered_npcs": [row]}
        self.assertTrue(area_population_matches(snapshot, snapshot, areas))
        for change in (
            {"position": [4, 9, 2.5]},
            {"position": [1.26, 9, 2.5]},
            {"position": [1.25, float("nan"), 2.5]},
            {"yaw": 1.6},
            {"playing": False},
            {"name": "Wrong"},
        ):
            other = {"rendered_npcs": [{**row, **change}]}
            with self.subTest(change=change):
                self.assertFalse(area_population_matches(snapshot, other, areas))
        self.assertFalse(area_population_matches(snapshot, {"rendered_npcs": []}, areas))

    def test_missing_stale_and_nonfinite_presentations_fail(self):
        expected = [{"spawn_id": "npc-a", "name": "Teacher", "position": [1, 2, 3], "yaw": 0}]
        actor = {**expected[0], "playing": True, "idle": "wait"}
        self.assertTrue(population_matches({"rendered_npcs": [actor]}, expected))
        self.assertFalse(population_matches({"rendered_npcs": []}, expected))
        for change in (
            {"name": "Wrong"},
            {"playing": False},
            {"idle": ""},
            {"position": [1, 2, 4]},
            {"position": [1, float("nan"), 3]},
            {"yaw": 0.5},
            {"yaw": float("nan")},
        ):
            with self.subTest(change=change):
                row = {**copy.deepcopy(actor), **change}
                self.assertFalse(population_matches({"rendered_npcs": [row]}, expected))
        with self.assertRaises(AssertionError):
            population_matches({"rendered_npcs": [actor, actor]}, expected)


class IdleQuestProgressTests(unittest.TestCase):
    def test_replayed_login_trigger_sequence_is_not_a_quest_change(self):
        """A session refresh re-fires login triggers and advances `sequence`."""
        baseline = replay_stable_signature(idle_snapshot())
        refreshed = idle_snapshot(
            quest_states=[
                {**row, "sequence": row["sequence"] + 1} for row in idle_snapshot()["quest_states"]
            ]
        )
        self.assertEqual(replay_stable_signature(refreshed), baseline)

    def test_leaked_hand_in_overwrites_the_visible_quest_state(self):
        """Every field the browser account's hand-in rewrote is compared."""
        baseline = replay_stable_signature(idle_snapshot())
        for change in (
            {"state": "__COMPLETE__"},
            {"title": "Other"},
        ):
            states = copy.deepcopy(idle_snapshot()["quest_states"])
            states[0].update(change)
            with self.subTest(change=change):
                leaked = idle_snapshot(quest_states=states)
                self.assertNotEqual(replay_stable_signature(leaked), baseline)
        dropped = idle_snapshot(quest_objectives=[idle_snapshot()["quest_objectives"][1]])
        self.assertNotEqual(replay_stable_signature(dropped), baseline)
        cleared = copy.deepcopy(idle_snapshot()["quest_objectives"])
        cleared[0]["letter_title"] = ""
        self.assertNotEqual(
            replay_stable_signature(idle_snapshot(quest_objectives=cleared)), baseline
        )
        retargeted = copy.deepcopy(idle_snapshot()["quest_objectives"])
        retargeted[0]["target_vnum"] = 11000
        self.assertNotEqual(
            replay_stable_signature(idle_snapshot(quest_objectives=retargeted)), baseline
        )

    def test_baseline_needs_a_settled_session_with_every_seeded_quest(self):
        complete = idle_snapshot()
        self.assertTrue(own_quest_rows_complete(complete, "npc-guard"))
        for change in (
            {"connection_state": "subscribing"},
            {"world_info": {}},
            {"rendered_npcs": []},
            {"quest_states": complete["quest_states"][:1]},
            {"quest_states": complete["quest_states"][:3]},
        ):
            with self.subTest(change=change):
                self.assertFalse(own_quest_rows_complete(idle_snapshot(**change), "npc-guard"))
