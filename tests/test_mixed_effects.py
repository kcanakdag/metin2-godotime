import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from mixed_effects import parse_mixed_effect
from test_metin_effect_mesh import MSE_FIXTURE
from test_metin_particles import PATH, fixture


def mixed():
    return fixture() + MSE_FIXTURE[MSE_FIXTURE.index("Group Mesh") :]


class MixedEffectsTests(unittest.TestCase):
    def test_all_layers_retained_in_source_order(self):
        result = parse_mixed_effect(mixed(), PATH)
        self.assertEqual(
            result["layer_order"], [{"kind": "particle", "index": 0}, {"kind": "mesh", "index": 0}]
        )
        self.assertEqual(len(result["particles"]["systems"]), 1)
        self.assertEqual(len(result["mesh_effect"]["meshes"]), 1)
        self.assertEqual(result["runtime_status"], "parsed-not-converted")

    def test_neither_half_can_hide_invalid_or_unknown_content(self):
        for text in (
            mixed() + "\nGroup Light\n{\n}\n",
            fixture(),
            MSE_FIXTURE,
            mixed().replace("MaxEmissionCount 30", "MaxEmissionCount -1"),
            mixed().replace("MeshAnimationFrameDelay 0.02", "MeshAnimationFrameDelay nan"),
        ):
            with self.subTest(text=text[-100:]), self.assertRaises(ValueError):
                parse_mixed_effect(text, PATH)


if __name__ == "__main__":
    unittest.main()
