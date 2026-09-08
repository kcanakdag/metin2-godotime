import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gr2_bindings import material_slots


class MaterialGroupTests(unittest.TestCase):
    def test_group_order_is_not_material_slot_order(self):
        mesh = {
            "MaterialBindings": [{}, {}],
            "PrimaryTopology": {
                "Groups": [
                    {"MaterialIndex": 1, "TriCount": 2},
                    {"MaterialIndex": 0, "TriCount": 1},
                ]
            },
        }
        self.assertEqual(material_slots(mesh, [0, 0, 1]), [1, 1, 0])
        for indices in ([0, 1, 1], [0, 0], [0, 0, 2]):
            with self.assertRaises(ValueError):
                material_slots(mesh, indices)
        mesh["PrimaryTopology"]["Groups"][0]["MaterialIndex"] = 2
        with self.assertRaises(ValueError):
            material_slots(mesh, [0, 0, 1])
