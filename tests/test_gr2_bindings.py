from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


class RigidBindingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        cls.bindings = importlib.import_module("gr2_bindings")

    def graph(self):
        return {
            "skeletons": [{"bones": [{"name": "prop"}]}],
            "meshes": [
                {
                    "name": "spear",
                    "boneBindings": [{"name": "prop"}],
                    "vertex": {"position": [12, 23, 34, 56, 78, 90]},
                }
            ],
        }

    def test_rigid_mesh_preserves_positions_and_becomes_one_bone_skin(self):
        graph = self.graph()
        before = copy.deepcopy(graph["meshes"][0]["vertex"]["position"])
        report = self.bindings.normalize_rigid_bindings(graph)
        vertex = graph["meshes"][0]["vertex"]
        self.assertEqual(vertex["position"], before)
        self.assertEqual(vertex["blendWeight"], [1, 0, 0, 0] * 2)
        self.assertEqual(vertex["blendIndice"], [0] * 8)
        self.assertEqual(report, [{"mesh": "spear", "bone": "prop", "vertices": 2}])
        converted = copy.deepcopy(graph)
        self.assertEqual(self.bindings.normalize_rigid_bindings(graph), [])
        self.assertEqual(graph, converted)

    def test_ambiguous_missing_and_partial_bindings_fail(self):
        for bindings in ([], [{"name": "absent"}], [{"name": "prop"}] * 2):
            graph = self.graph()
            graph["meshes"][0]["boneBindings"] = bindings
            with self.assertRaises(ValueError):
                self.bindings.normalize_rigid_bindings(graph)
        graph = self.graph()
        graph["meshes"][0]["vertex"]["blendIndice"] = [0] * 8
        with self.assertRaises(ValueError):
            self.bindings.normalize_rigid_bindings(graph)

    def test_hair_merge_validates_every_used_bone_and_allows_unused_helpers(self):
        identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        body = {"head": identity, "ponytail": copy.deepcopy(identity)}
        hair = {**copy.deepcopy(body), "unused-export-helper": identity}
        hair["ponytail"][1][3] += 0.00002
        report = self.bindings.validate_shared_skin_bones(body, hair, {"head", "ponytail"})
        self.assertEqual(report["checked_shared_bones"], ["head", "ponytail"])
        for name in ("missing", "unused-export-helper"):
            with self.assertRaises(ValueError):
                self.bindings.validate_shared_skin_bones(body, hair, {name})
        hair["ponytail"][1][3] = 1
        with self.assertRaisesRegex(ValueError, "world rest transform"):
            self.bindings.validate_shared_skin_bones(body, hair, {"head", "ponytail"})
        hair["ponytail"][1][3] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid skin rest"):
            self.bindings.validate_shared_skin_bones(body, hair, {"head", "ponytail"})
