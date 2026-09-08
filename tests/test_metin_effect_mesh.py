"""Synthetic checks for the bounded Metin2 mesh-effect readers."""

import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from metin_effect_mesh import EffectMeshFormatError, d3dx_color_byte, parse_mde, parse_mse


def _fixed(value: str, size: int) -> bytes:
    encoded = value.encode("ascii")
    return encoded + bytes(size - len(encoded))


def mde_fixture(
    *,
    header: bytes = b"EffectData\0",
    geometry_count: int = 1,
    frame_count: int = 2,
    visibility: tuple[float, ...] = (1.0, -0.25),
    indices: tuple[int, ...] = (0, 1, 2),
    texture_indices: tuple[int, ...] = (0, 1, 2),
) -> bytes:
    result = bytearray(header)
    result.extend(struct.pack("<ii", geometry_count, frame_count))
    if geometry_count != 1 or frame_count < 0:
        return bytes(result)
    result.extend(_fixed("Triangle", 32))
    result.extend(_fixed(r"D:\Ymir Work\effect\triangle.tga", 128))
    result.extend(struct.pack("<III", 3, len(indices), 3))
    for frame in range(frame_count):
        result.extend(struct.pack("<f", visibility[frame]))
        positions = ((0.0, 0.0, frame), (1.0, 0.0, frame), (0.0, 1.0, frame))
        result.extend(struct.pack("<9f", *(value for point in positions for value in point)))
        result.extend(struct.pack(f"<{len(indices)}i", *indices))
        result.extend(struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0))
        result.extend(struct.pack(f"<{len(texture_indices)}i", *texture_indices))
    return bytes(result)


MSE_FIXTURE = """
BoundingSphereRadius 70.0
BoundingSpherePosition 0 0 40
Group Mesh
{
  StartTime 0
  List TimeEventPosition
  {
    0 MOVING_TYPE_DIRECT 0 0 41.60334
  }
  MeshFileName "click_select.mde"
  MeshAnimationLoopEnable 1
  MeshAnimationLoopCount 0
  MeshAnimationFrameDelay 0.02
  MeshElementCount 1
  Group MeshElement00
  {
    BillboardType 0
    BlendingEnable 1
    BlendingSrcType 5
    BlendingDestType 6
    TextureAnimationLoopEnable 1
    TextureAnimationFrameDelay 0.02
    TextureAnimationStartFrame 0
    ColorOperationType 4
    ColorFactor 1 0.054902 0 1
    List TimeEventAlpha
    {
    }
  }
}
"""


class MdeTests(unittest.TestCase):
    def test_reads_v001_frames_and_preserves_visibility_outside_unit_range(self):
        parsed = parse_mde(mde_fixture())
        self.assertEqual(parsed.version, 1)
        self.assertEqual(parsed.frame_count, 2)
        self.assertEqual(len(parsed.geometries), 1)
        geometry = parsed.geometries[0]
        self.assertEqual(geometry.name, "Triangle")
        self.assertEqual(geometry.frames[1].visibility, -0.25)
        self.assertEqual(geometry.frames[1].positions[2], (0.0, 1.0, 1.0))
        self.assertEqual(geometry.frames[0].position_indices, (0, 1, 2))

    def test_rejects_nonfinite_floats(self):
        corrupt = bytearray(mde_fixture())
        first_visibility = 11 + 8 + 32 + 128 + 12
        struct.pack_into("<f", corrupt, first_visibility, math.nan)
        with self.assertRaisesRegex(EffectMeshFormatError, "Non-finite"):
            parse_mde(bytes(corrupt))

    def test_rejects_counts_and_nontriangle_index_lists(self):
        with self.assertRaisesRegex(EffectMeshFormatError, "geometry count"):
            parse_mde(mde_fixture(geometry_count=0))
        with self.assertRaisesRegex(EffectMeshFormatError, "frame count"):
            parse_mde(mde_fixture(frame_count=0, visibility=()))
        with self.assertRaisesRegex(EffectMeshFormatError, "triangle list"):
            parse_mde(
                mde_fixture(
                    frame_count=1,
                    visibility=(1.0,),
                    indices=(0, 1, 2, 0),
                    texture_indices=(0, 1, 2, 0),
                )
            )

    def test_rejects_invalid_position_and_texture_indices(self):
        with self.assertRaisesRegex(EffectMeshFormatError, "position index"):
            parse_mde(mde_fixture(indices=(0, 1, 3)))
        with self.assertRaisesRegex(EffectMeshFormatError, "texture index"):
            parse_mde(mde_fixture(texture_indices=(0, -1, 2)))

    def test_rejects_truncation_trailing_data_and_unsupported_versions(self):
        source = mde_fixture()
        with self.assertRaisesRegex(EffectMeshFormatError, "Truncated"):
            parse_mde(source[:-1])
        with self.assertRaisesRegex(EffectMeshFormatError, "trailing"):
            parse_mde(source + b"x")
        with self.assertRaisesRegex(EffectMeshFormatError, "MDEData002"):
            parse_mde(mde_fixture(header=b"MDEData002\0"))

    def test_rejects_topology_changes_between_frames(self):
        source = bytearray(mde_fixture())
        frame_bytes = 4 + 3 * 12 + 3 * 4 + 3 * 8 + 3 * 4
        first_frame = 11 + 8 + 32 + 128 + 12
        second_indices = first_frame + frame_bytes + 4 + 3 * 12
        struct.pack_into("<3i", source, second_indices, 0, 2, 1)
        with self.assertRaisesRegex(EffectMeshFormatError, "topology changes"):
            parse_mde(bytes(source))

    def test_rejects_animated_texture_coordinates(self):
        source = bytearray(mde_fixture())
        frame_bytes = 4 + 3 * 12 + 3 * 4 + 3 * 8 + 3 * 4
        first_frame = 11 + 8 + 32 + 128 + 12
        second_uv = first_frame + frame_bytes + 4 + 3 * 12 + 3 * 4
        struct.pack_into("<f", source, second_uv, 0.25)
        with self.assertRaisesRegex(EffectMeshFormatError, "texture coordinates"):
            parse_mde(bytes(source))


class MseTests(unittest.TestCase):
    def test_movement_billboard_metadata_preserved(self):
        parsed = parse_mse(MSE_FIXTURE.replace("BillboardType 0", "BillboardType 3"))
        self.assertEqual(parsed.meshes[0].elements[0].billboard_type, 3)
        with self.assertRaises(ValueError):
            parse_mse(MSE_FIXTURE.replace("BillboardType 0", "BillboardType 2"))

    def test_selected_color_operations_are_preserved(self):
        for operation in (3, 4, 6):
            parsed = parse_mse(
                MSE_FIXTURE.replace("ColorOperationType 4", f"ColorOperationType {operation}")
            )
            self.assertEqual(parsed.meshes[0].elements[0].color_operation, operation)
        with self.assertRaises(ValueError):
            parse_mse(MSE_FIXTURE.replace("ColorOperationType 4", "ColorOperationType 7"))

    def test_d3dx_color_packing_clamps_and_rounds_source_visibility(self):
        self.assertEqual(d3dx_color_byte(-0.34704768657684326), 0)
        self.assertEqual(d3dx_color_byte(0.0), 0)
        self.assertEqual(d3dx_color_byte(0.054902), 14)
        self.assertEqual(d3dx_color_byte(0.5), 128)
        self.assertEqual(d3dx_color_byte(1.0087151527404785), 255)
        with self.assertRaisesRegex(EffectMeshFormatError, "non-finite"):
            d3dx_color_byte(math.inf)

    def test_reads_selected_mesh_subset(self):
        parsed = parse_mse(MSE_FIXTURE)
        self.assertEqual(parsed.bounding_sphere_radius, 70.0)
        mesh = parsed.meshes[0]
        self.assertTrue(mesh.animation_loop)
        self.assertEqual(mesh.animation_loop_count, 0)
        self.assertEqual(mesh.frame_delay, 0.02)
        self.assertEqual(mesh.position_events[0].position, (0.0, 0.0, 41.60334))
        self.assertEqual(mesh.elements[0].color_factor, (1.0, 0.054902, 0.0, 1.0))
        self.assertEqual(mesh.elements[0].alpha_events, ())

    def test_rejects_nonfinite_and_invalid_format_values(self):
        with self.assertRaisesRegex(EffectMeshFormatError, "BoundingSphereRadius"):
            parse_mse(MSE_FIXTURE.replace("70.0", "nan"))
        with self.assertRaisesRegex(EffectMeshFormatError, "MeshElementCount"):
            parse_mse(MSE_FIXTURE.replace("MeshElementCount 1", "MeshElementCount 2"))
        with self.assertRaisesRegex(EffectMeshFormatError, "blend pair"):
            parse_mse(MSE_FIXTURE.replace("BlendingSrcType 5", "BlendingSrcType 2"))

    def test_rejects_unsupported_records_instead_of_guessing(self):
        with self.assertRaisesRegex(EffectMeshFormatError, "Unsupported fields"):
            parse_mse(MSE_FIXTURE.replace("StartTime 0", "StartTime 0\n  Rotation 90"))
        with self.assertRaisesRegex(EffectMeshFormatError, "movement type"):
            parse_mse(MSE_FIXTURE.replace("MOVING_TYPE_DIRECT", "MOVING_TYPE_BEZIER_CURVE"))
        with self.assertRaisesRegex(EffectMeshFormatError, "Unsupported groups"):
            parse_mse(MSE_FIXTURE + "\nGroup Particle\n{\n Value 1\n}\n")

    def test_rejects_duplicate_numbered_elements(self):
        element_start = MSE_FIXTURE.index("  Group MeshElement00")
        mesh_close = MSE_FIXTURE.rfind("\n}")
        element = MSE_FIXTURE[element_start:mesh_close]
        duplicate = MSE_FIXTURE[:mesh_close] + "\n" + element + MSE_FIXTURE[mesh_close:]
        with self.assertRaisesRegex(EffectMeshFormatError, "MeshElementCount"):
            parse_mse(duplicate)

    def test_rejects_nested_event_groups(self):
        nested = "\n    Group Unsupported\n    {\n    }"
        with self.subTest("position"):
            malformed = MSE_FIXTURE.replace(
                "    0 MOVING_TYPE_DIRECT 0 0 41.60334",
                "    0 MOVING_TYPE_DIRECT 0 0 41.60334" + nested,
            )
            with self.assertRaisesRegex(EffectMeshFormatError, "Unsupported groups"):
                parse_mse(malformed)
        with self.subTest("alpha"):
            malformed = MSE_FIXTURE.replace(
                "    List TimeEventAlpha\n    {", "    List TimeEventAlpha\n    {" + nested
            )
            with self.assertRaisesRegex(EffectMeshFormatError, "Unsupported groups"):
                parse_mse(malformed)


if __name__ == "__main__":
    unittest.main()
