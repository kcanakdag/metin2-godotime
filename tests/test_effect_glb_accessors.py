import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from import_target_effects import accessor_floats
from metin_effect_mesh import EffectMeshFormatError, parse_mse
from test_metin_effect_mesh import MSE_FIXTURE


class EffectAccessorTests(unittest.TestCase):
    def sparse(self):
        return {
            "accessors": [
                {
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC3",
                    "sparse": {
                        "count": 1,
                        "indices": {"bufferView": 0, "componentType": 5121},
                        "values": {"bufferView": 1},
                    },
                }
            ],
            "bufferViews": [
                {"byteOffset": 0, "byteLength": 1},
                {"byteOffset": 4, "byteLength": 12},
            ],
        }

    def test_sparse_zero_base_and_nonzero_override(self):
        data = bytes([1, 0, 0, 0]) + struct.pack("<3f", 1, 2, 3)
        self.assertEqual(accessor_floats(self.sparse(), data, 0), (0, 0, 0, 1, 2, 3, 0, 0, 0))
        self.assertEqual(accessor_floats(self.sparse(), bytes(16), 0), (0,) * 9)

    def test_sparse_out_of_bounds_and_duplicate_indices_reject(self):
        for data in (bytes([3, 0, 0, 0]) + bytes(12), bytes(8)):
            with self.assertRaises(ValueError):
                accessor_floats(self.sparse(), data, 0)
        document = copy.deepcopy(self.sparse())
        document["accessors"][0]["sparse"]["count"] = 2
        document["bufferViews"][0]["byteLength"] = 2
        document["bufferViews"][1]["byteLength"] = 24
        with self.assertRaises(ValueError):
            accessor_floats(document, bytes(28), 0)

    def test_reviewed_blend_metadata_does_not_relax_default_renderer_subset(self):
        text = MSE_FIXTURE.replace("BlendingSrcType 5", "BlendingSrcType 3").replace(
            "BlendingDestType 6", "BlendingDestType 8"
        )
        with self.assertRaises(EffectMeshFormatError):
            parse_mse(text)
        mesh = parse_mse(text, blend_pairs={(3, 8)}).meshes[0]
        self.assertEqual(
            (mesh.elements[0].blending_source, mesh.elements[0].blending_destination), (3, 8)
        )
