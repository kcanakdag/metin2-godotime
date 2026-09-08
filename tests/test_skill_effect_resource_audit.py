import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_skill_effect_resources import inspect_effect
from test_metin_effect_mesh import MSE_FIXTURE
from test_metin_particles import PATH, fixture


class SkillEffectResourceAuditTests(unittest.TestCase):
    def test_supported_particle_mesh_and_mixed_are_not_claimed_converted(self):
        mixed = fixture() + MSE_FIXTURE[MSE_FIXTURE.index("Group Mesh") :]
        for text, kind in [(fixture(), "particles"), (MSE_FIXTURE, "meshes"), (mixed, "mixed")]:
            with self.subTest(kind=kind):
                result = inspect_effect(text, PATH)
                self.assertEqual(result["status"], "parsed-not-converted")
                self.assertEqual(result["kind"], kind)

    def test_unknown_layers_and_invalid_recipe_remain_explicit(self):
        result = inspect_effect(fixture() + "\nGroup Light\n{\n}\n", PATH)
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("Light", result["layers"])
        result = inspect_effect(
            fixture().replace("MaxEmissionCount 30", "MaxEmissionCount -1"), PATH
        )
        self.assertEqual(result["status"], "unsupported")
        self.assertTrue(result["reason"])
