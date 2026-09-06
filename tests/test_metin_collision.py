"""Collision format and fixed server bake contract checks without original assets or Blender."""

import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from bake_yongan import validate_manifest, visible_water_cells
from metin_collision import decode


def shape(kind=0, position=(100, -200, 300), size=(20, 40), quaternion=(0, 0, 0, 1)):
    return (
        struct.pack("<I32s3f", kind, b"fixture", *position)
        + struct.pack(f"<{len(size)}f", *size)
        + struct.pack("<4f", *quaternion)
    )


def attribute(shapes=(), vertices=()):
    data = b"AttributeData\0" + struct.pack("<II", len(shapes), bool(vertices))
    data += b"".join(shapes)
    if vertices:
        data += struct.pack("<32sI", b"walk surface", len(vertices))
        data += b"".join(struct.pack("<3f", *p) for p in vertices)
    return data


class CollisionFormat(unittest.TestCase):
    def test_supported_shapes_and_authored_surface_preserve_units(self):
        vertices = [(0, 0, 10), (100, 0, 20), (0, 100, 30)]
        shapes, triangles = decode(
            attribute([shape(), shape(kind=2, size=(25,)), shape(kind=3)], vertices)
        )
        self.assertEqual([s["kind"] for s in shapes], [0, 2, 3])
        self.assertEqual(shapes[0]["position"], (100, -200, 300))
        self.assertEqual(shapes[1]["size"], (25,))
        self.assertEqual(shapes[0]["name"], "fixture")
        self.assertEqual(triangles, [vertices])
        self.assertEqual(decode(attribute()), ([], []))

    def test_every_truncation_is_a_format_error(self):
        complete = attribute([shape()], [(0, 0, 0), (100, 0, 0), (0, 100, 0)])
        for length in range(len(complete)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                decode(complete[:length])
        for corrupt in (b"bad signature!" + complete[14:], complete + b"\0"):
            with self.assertRaises(ValueError):
                decode(corrupt)

    def test_unverified_kinds_and_unreasonable_counts_fail_closed(self):
        for kind in (1, 4, 5, 0xFFFFFFFF):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                decode(attribute([shape(kind=kind)]))
        for counts in ((10001, 0), (0, 10001)):
            with self.assertRaises(ValueError):
                decode(b"AttributeData\0" + struct.pack("<II", *counts))
        for count in (1, 4, 1000002):
            with self.assertRaises(ValueError):
                decode(attribute()[:-4] + struct.pack("<I32sI", 1, b"bad", count))

    def test_nonfinite_collision_and_surface_values_are_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            for record in (
                shape(position=(bad, 0, 0)),
                shape(size=(20, bad)),
                shape(quaternion=(0, bad, 0, 1)),
            ):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    decode(attribute([record]))
            with self.assertRaises(ValueError):
                decode(attribute(vertices=[(0, 0, 0), (bad, 0, 0), (0, 1, 0)]))

    def test_degenerate_dimensions_and_plane_rotations_are_rejected(self):
        for record in (
            shape(size=(0, 40)),
            shape(kind=2, size=(-1,)),
            shape(kind=3, size=(1, -1)),
            shape(quaternion=(0, 0, 0, 0)),
            shape(quaternion=(0, 0, 0, 2)),
        ):
            with self.assertRaises(ValueError):
                decode(attribute([record]))


class BakeContract(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "map": "metin2_map_a1",
            "settings": {"size": [4, 5], "cell_m": 2, "chunk_m": 256, "height_scale": 0.5},
            "chunks": [{"grid": [x, z]} for x in range(4) for z in range(5)],
            "seam_mismatches": 0,
        }

    def test_server_height_scale_and_grid_cannot_silently_drift(self):
        validate_manifest(self.manifest)
        for key, bad in (
            ("height_scale", 1.0),
            ("height_scale", float("nan")),
            ("cell_m", 1),
            ("chunk_m", 128),
            ("size", [5, 4]),
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest["settings"][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_missing_duplicate_or_seamed_terrain_cannot_be_baked(self):
        for field, invalid in (
            ("map", "another_map"),
            ("chunks", self.manifest["chunks"][:-1]),
            ("chunks", self.manifest["chunks"][:-1] + [self.manifest["chunks"][0]]),
            ("seam_mismatches", 1),
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest[field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_buried_water_is_walkable_but_visible_water_still_blocks(self):
        samples = [35107] * (131 * 131)  # Dry ground at 175.535 m.
        cells = bytes([0]) + bytes([255]) * (128 * 128 - 1)
        # Reproduces the original map's plane at 153.05 m beneath dry farmland.
        self.assertFalse(any(visible_water_cells(samples, cells, [306.1], 0.5)))
        # A water plane at ground level is invisible; one above it is rendered and blocks.
        self.assertFalse(any(visible_water_cells(samples, cells, [351.07], 0.5)))
        wet = visible_water_cells(samples, cells, [352.0], 0.5)
        self.assertEqual(sum(wet), 1)
        self.assertTrue(wet[0])
        # A submerged corner is enough for the same partial water quad rendered by the client.
        samples[132] = 30000
        wet = visible_water_cells(samples, cells, [306.1], 0.5)
        self.assertEqual(sum(wet), 1)


if __name__ == "__main__":
    unittest.main()
