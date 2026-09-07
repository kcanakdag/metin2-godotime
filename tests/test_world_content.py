from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


class WorldAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        cls.world = importlib.import_module("world_content")

    def profile(self):
        return {
            "revision": 3,
            "placements": [
                {"id": 41, "definition_vnum": 101, "home_x": 3.0, "home_z": 3.0},
                {"id": 82, "definition_vnum": 101, "home_x": 10.0, "home_z": 3.0},
            ],
        }

    def test_edits_preserve_source_and_unrelated_persistent_ids(self):
        source = self.profile()
        original = copy.deepcopy(source)
        moved = self.world.edit_profile(source, "move", 41, 5.0, 6.0, None)
        self.assertEqual(source, original)
        self.assertEqual(moved["revision"], 4)
        self.assertEqual(moved["placements"][1], source["placements"][1])
        self.assertEqual(
            moved["placements"][0], {"id": 41, "definition_vnum": 101, "home_x": 5.0, "home_z": 6.0}
        )
        added = self.world.edit_profile(source, "add", 125, -8.0, 12.0, 101)
        self.assertEqual([row["id"] for row in added["placements"]], [41, 82, 125])
        removed = self.world.edit_profile(added, "remove", 82, None, None, None)
        self.assertEqual([row["id"] for row in removed["placements"]], [41, 125])
        self.assertEqual(source, original)

    def test_ambiguous_missing_and_reused_ids_do_not_modify_the_source(self):
        source = self.profile()
        original = copy.deepcopy(source)
        for command, identity, x, z, vnum in (
            ("move", 999, 4.0, 5.0, None),
            ("remove", 999, None, None, None),
            ("add", 41, 4.0, 5.0, 101),
            ("move", 41, None, 5.0, None),
            ("add", 999, 4.0, 5.0, None),
        ):
            with self.assertRaises(ValueError):
                self.world.edit_profile(source, command, identity, x, z, vnum)
            self.assertEqual(source, original)
