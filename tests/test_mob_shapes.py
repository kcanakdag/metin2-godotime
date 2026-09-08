import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mob_shapes import apply_skin_remaps, default_shape

BASE = 'ScriptType RaceDataScript\nBaseModelFileName "d:/ymir work/monster/wolf/wolf.gr2"\n'
SHAPE = """Group ShapeData
{
PathName "d:/ymir work/monster/wolf/"
ShapeDataCount 1
Group ShapeData00
{
ShapeIndex 0
Model "wolf.gr2"
SourceSkin "wolf.dds"
TargetSkin "wolf_blue.dds"
}
}
"""


class MobShapeTests(unittest.TestCase):
    def test_default_shape_preserves_explicit_variant_texture(self):
        shape = default_shape(BASE + SHAPE)
        self.assertEqual(shape["model"], "ymir work/monster/wolf/wolf.gr2")
        self.assertEqual(
            shape["skin_remaps"],
            [
                {
                    "source": "ymir work/monster/wolf/wolf.dds",
                    "target": "ymir work/monster/wolf/wolf_blue.dds",
                }
            ],
        )
        self.assertEqual(default_shape(BASE)["skin_remaps"], [])

    def test_missing_or_unsupported_shape_details_reject(self):
        for changed in (
            SHAPE.replace("ShapeDataCount 1", "ShapeDataCount 0"),
            SHAPE.replace("ShapeIndex 0", "ShapeIndex 1"),
            SHAPE.replace('TargetSkin "wolf_blue.dds"', ""),
            SHAPE.replace('Model "wolf.gr2"', 'Model "../wolf.gr2"'),
            SHAPE.replace("ShapeIndex 0", "ShapeIndex 0\nUnimplementedEffect 1"),
        ):
            with self.assertRaises(ValueError):
                default_shape(BASE + changed)

    def test_remaps_use_full_bound_paths_and_apply_simultaneously(self):
        bindings = {"diffuse": "a/wolf.dds", "ambient": "a/wolf.dds", "second": "a/blue.dds"}
        remaps = [
            {"source": "a/wolf.dds", "target": "a/blue.dds"},
            {"source": "a/blue.dds", "target": "a/black.dds"},
        ]
        self.assertEqual(
            apply_skin_remaps(bindings, remaps),
            {"diffuse": "a/blue.dds", "ambient": "a/blue.dds", "second": "a/black.dds"},
        )
        self.assertEqual(bindings["diffuse"], "a/wolf.dds")
        for invalid in (remaps + remaps, [{"source": "b/wolf.dds", "target": "a/blue.dds"}]):
            with self.assertRaises(ValueError):
                apply_skin_remaps(bindings, invalid)
