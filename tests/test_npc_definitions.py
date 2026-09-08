from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


class NpcDefinitionsTests(unittest.TestCase):
    def test_unused_empty_exporter_material_requires_topology_proof(self):
        mesh = {
            "MaterialBindings": [
                {"Material": {"Maps": []}},
                {
                    "Material": {
                        "Maps": [
                            {
                                "Usage": "Diffuse Color",
                                "Map": {
                                    "Texture": {"FromFileName": "D:/Ymir Work/npc/ceramist.dds"}
                                },
                            }
                        ]
                    }
                },
            ],
            "PrimaryTopology": {"Groups": [{"MaterialIndex": 1, "TriCount": 2}]},
        }
        self.assertEqual(
            self.npc.material_paths({"Meshes": [mesh]}), ["ymir work/npc/ceramist.dds"]
        )
        used = copy.deepcopy(mesh)
        used["PrimaryTopology"]["Groups"].append({"MaterialIndex": 0, "TriCount": 1})
        unknown = copy.deepcopy(mesh)
        del unknown["PrimaryTopology"]
        for invalid in (used, unknown):
            with self.assertRaises(ValueError):
                self.npc.material_paths({"Meshes": [invalid]})

    def test_area_spawns_preserve_centimetre_rectangle_and_original_random_heading(self):
        text = "m 687 475 1 1 0 8 1m 100 1 20002"
        row = self.npc.area_spawns(text, 20002)[0]
        self.assertEqual(row["bounds_cm"], [68600, 47400, 68800, 47600])
        self.assertEqual(row["position_step_cm"], 1)
        self.assertEqual(row["spawn_attempts"], 16)
        self.assertEqual(row["source_direction"], 8)
        self.assertEqual(row["heading_bounds_degrees"], [0, 360])
        self.assertEqual(row["heading_policy"], "random-integer-degree")
        self.assertIsNone(row["source_heading_degrees"])
        self.assertNotIn("x_m", row)
        self.assertNotIn("z_m", row)
        with self.assertRaises(ValueError):
            self.npc.point_spawns(text, 20002)

    def test_area_spawns_reject_point_substitution_and_out_of_bounds_rectangles(self):
        for geometry in ("687 475 0 0", "0 0 1 1", "21474836 0 1 0"):
            with self.subTest(geometry=geometry), self.assertRaises(ValueError):
                self.npc.area_spawns(f"m {geometry} 0 0 1m 100 1 20002", 20002)
        row = self.npc.area_spawns("m 10 20 0 1 0 0 1m 100 1 20002", 20002)[0]
        self.assertEqual(row["bounds_cm"], [1000, 1900, 1000, 2100])

    def test_explicit_registration_uses_shape_and_rejects_root_mismatch(self):
        self.assertEqual(
            self.npc.race_paths("#season1/npc/chagirap/", "season1/npc/chagirap"),
            ("season1/npc/chagirap/shape.msm", "season1/npc/chagirap/motlist.txt"),
        )
        self.assertEqual(
            self.npc.race_paths("guard_leader", "ymir work/npc/guard_leader")[0],
            "ymir work/npc/guard_leader/guard_leader.msm",
        )
        for key in ("#season1/npc/other/", "#../outside/", "../guard"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.npc.race_paths(key, "season1/npc/chagirap")

    def test_local_texture_names_resolve_beside_the_model(self):
        def raw(name):
            return {
                "Meshes": [
                    {
                        "MaterialBindings": [
                            {
                                "Material": {
                                    "Maps": [
                                        {
                                            "Usage": "Diffuse Color",
                                            "Map": {"Texture": {"FromFileName": name}},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }

        self.assertEqual(
            self.npc.material_bindings(raw("chagirap.dds"), "season1/npc/chagirap"),
            {"chagirap.dds": "season1/npc/chagirap/chagirap.dds"},
        )
        self.assertEqual(
            self.npc.material_bindings(raw("D:/Ymir Work/npc/shared.dds"), "season1/npc/chagirap"),
            {"ymir work/npc/shared.dds": "ymir work/npc/shared.dds"},
        )
        with self.assertRaises(ValueError):
            self.npc.material_bindings(raw("../outside.dds"), "season1/npc/chagirap")

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        cls.npc = importlib.import_module("npc_definitions")

    def test_material_dependencies_follow_the_model_and_reject_unsupported_maps(self):
        raw = {
            "Meshes": [
                {
                    "MaterialBindings": [
                        {
                            "Material": {
                                "Maps": [
                                    {
                                        "Usage": "Diffuse Color",
                                        "Map": {
                                            "Texture": {
                                                "FromFileName": "D:\\Ymir Work\\npc\\shared\\weapon.dds"
                                            }
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        self.assertEqual(self.npc.material_paths(raw), ["ymir work/npc/shared/weapon.dds"])
        masked = copy.deepcopy(raw)
        maps = masked["Meshes"][0]["MaterialBindings"][0]["Material"]["Maps"]
        opacity = copy.deepcopy(maps[0])
        opacity["Usage"] = "Opacity"
        maps.append(opacity)
        self.assertEqual(self.npc.material_paths(masked), self.npc.material_paths(raw))
        opacity["Map"]["Texture"]["FromFileName"] = "different.dds"
        with self.assertRaises(ValueError):
            self.npc.material_paths(masked)
        for usage in ["Normal Map", ""]:
            changed = copy.deepcopy(raw)
            changed["Meshes"][0]["MaterialBindings"][0]["Material"]["Maps"][0]["Usage"] = usage
            with self.subTest(usage=usage), self.assertRaises(ValueError):
                self.npc.material_paths(changed)

    def test_point_coordinates_are_map_metres_and_random_heading_is_preserved(self):
        result = self.npc.point_spawns("m 605 663 0 0 0 0 1m 100 1 20354", 20354)[0]
        self.assertEqual((result["x_m"], result["z_m"]), (605, 663))
        self.assertEqual(result["heading_policy"], "random-octant")
        self.assertIsNone(result["source_heading_degrees"])
        self.assertEqual(result["respawn_interval_us"], 60_000_000)
        self.assertEqual(result["height_policy"], "authoritative-terrain")

    def test_source_headings_and_occurrences_are_not_collapsed(self):
        result = self.npc.point_spawns(
            "// comment\nm 1 2 0 0 0 1 2s 100 1 7\nm 3 4 0 0 0 8 1h 100 1 7\nm 1 1 0 0 0 0 1m 100 1 8",
            7,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual([row["source_heading_degrees"] for row in result], [0, 315])
        self.assertEqual([row["source_line"] for row in result], [2, 3])

    def test_selected_unsupported_spawns_and_invalid_numbers_fail(self):
        base = "m 605 663 0 0 0 0 1m 100 1 20354".split()
        changes = [
            (0, "g"),
            (1, "nan"),
            (1, "-1"),
            (2, "1.5"),
            (3, "1"),
            (4, "1"),
            (5, "1"),
            (6, "9"),
            (7, "1"),
            (7, "0s"),
            (7, "25h"),
            (8, "99"),
            (9, "2"),
        ]
        for index, value in changes:
            row = base.copy()
            row[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                self.npc.point_spawns(" ".join(row), 20354)
        with self.assertRaises(ValueError):
            self.npc.point_spawns("m 605 663 20354", 20354)
        with self.assertRaises(ValueError):
            self.npc.point_spawns("", 20354)

    def test_idle_variants_preserve_source_weights_and_all_other_clips(self):
        rows = [
            {"mode": "general", "action": action, "path": action + ".msa", "weight": weight}
            for action, weight in [
                ("wait", 65),
                ("wait1", 35),
                ("walk", 100),
                ("run", 100),
                ("dead", 100),
            ]
        ]
        groups = self.npc.motion_groups(rows)
        idle = next(group for group in groups if group["action"] == "wait")
        self.assertEqual(idle["weights"], [65, 35])
        self.assertEqual(sum(len(group["files"]) for group in groups), 5)
        self.assertFalse(next(group for group in groups if group["action"] == "dead")["loop"])
        self.assertEqual(self.npc.motion_groups(rows + [rows[0]]), groups)
        for invalid in [
            rows[:1],
            [{**rows[0], "action": "attack"}],
            [{**rows[0], "mode": "onehand"}],
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.npc.motion_groups(invalid)
