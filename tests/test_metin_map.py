"""Format/coordinate integrity tests using synthetic inputs, without original assets."""

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from metin_archive import Archive, safe_path, virtual_path
from metin_map_data import (
    attributes,
    height_at,
    heights,
    placements,
    property_data,
    seam_errors,
    settings,
    texture_set,
    to_godot,
    water,
)


class MapFormats(unittest.TestCase):
    def test_axis_units_and_height_bias(self):
        self.assertEqual(to_godot([100, -200, 300], 50), [1, 3.5, 2])

    def test_placement_count_and_legacy_rotation(self):
        text = "AreaDataFile\nStart Object000\n100 -200 300\n42\n90\n5\nEnd Object\nObjectCount 1\n"
        record = placements(text)[0]
        self.assertEqual(record["rotation_ypr_deg"], [0, 0, 90])
        self.assertEqual(record["position"], [1, 3.0500000000000003, 2])
        for invalid in (
            text.replace("Count 1", "Count 2"),
            text.replace("100 -200", "nan -200"),
            text.replace("\n42\n", "\n-1\n"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                placements(invalid)

    def test_padded_height_origin_and_seams(self):
        # A ramp continues across two chunks; the outer halo is not a visible row.
        grids = {}
        for chunk in (0, 1):
            raw = [1000 + chunk * 128 + x - 1 for _y in range(131) for x in range(131)]
            grids[chunk, 0] = heights(struct.pack("<17161H", *raw))
        self.assertEqual(height_at(grids[0, 0], 0, 0, 0.5), 5.0)
        self.assertEqual(seam_errors(grids, 0.5), [])
        broken = list(grids[1, 0])
        broken[132] += 10
        grids[1, 0] = broken
        errors = seam_errors(grids, 0.5)
        self.assertEqual(len(errors), 1)
        self.assertAlmostEqual(errors[0]["delta_m"], 0.05)
        with self.assertRaises(ValueError):
            heights(b"\0" * 128 * 128 * 2)

    def test_attributes_preserve_flags(self):
        content = struct.pack("<3H", 2634, 256, 256) + bytes([129]) * 65536
        self.assertEqual(attributes(content)[0], 129)
        for corrupt in (content[:-1], b"xx" + content[2:]):
            with self.assertRaises(ValueError):
                attributes(corrupt)

    def test_water_variants_and_invalid_references(self):
        header = struct.pack("<3HB", 5426, 128, 128, 1)
        cells = bytes([0]) + bytes([255]) * 16383
        for packed in (struct.pack("<i", 12000), struct.pack("<H", 12000)):
            decoded, levels = water(header + cells + packed)
            self.assertEqual(decoded, cells)
            self.assertEqual(levels, [120.0])
        with self.assertRaises(ValueError):
            water(header + bytes([1]) * 16384 + struct.pack("<i", 12000))

    def test_property_paths_are_not_shell_escaped(self):
        crc, fields = property_data(
            'YPRT\n42\nbuildingfile "d:/ymir work/a.gr2"\npropertytype "Building"'
        )
        self.assertEqual(crc, "42")
        self.assertEqual(fields["buildingfile"], "d:/ymir work/a.gr2")

    def test_texture_contract(self):
        text = 'TextureSet\nTextureCount 1\nStart Texture001\n"d:\\terrain\\a.dds"\n5\n6\n0\n0\n0\n0\n0\nEnd Texture001\n'
        self.assertEqual(texture_set(text)[0]["uv"], [5, 6, 0, 0])
        with self.assertRaises(ValueError):
            texture_set(text.replace("TextureCount 1", "TextureCount 2"))

    def test_settings_reject_unsupported_cell_format(self):
        text = "ScriptType MapSetting\nCellScale 200\nHeightScale 0.5\nMapSize 4 5\nBasePosition 100 200\nTextureSet textureset/a.txt\nEnvironment a.msenv"
        self.assertEqual(settings(text)["size"], [4, 5])
        with self.assertRaises(ValueError):
            settings(text.replace("CellScale 200", "CellScale 100"))


class ArchiveIntegrity(unittest.TestCase):
    def test_path_normalization_and_escape_rejection(self):
        self.assertEqual(virtual_path("D:\\Ymir Work\\Zone\\A.GR2"), "ymir work/zone/a.gr2")
        for path in (
            "../secret",
            "/absolute",
            "a/../../secret",
            "a//b",
            "a/./b",
            "c:/file",
            "a\0b",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)

    def test_pack_precedence_and_unindexed_conflicts(self):
        archive = Archive(offline=True)
        a, b = "bin/pack/Terrain/terrain/a.dds", "bin/pack/patch1/terrain/a.dds"
        archive.entries = {a: {"sha": "a"}, b: {"sha": "b"}}
        archive.virtual = {"terrain/a.dds": [a, b]}
        with self.assertRaises(ValueError):
            archive.resolve("terrain/a.dds")
        archive.pack_order = {"patch1": 0, "terrain": 1}
        self.assertEqual(archive.resolve("terrain/a.dds"), b)
        with self.assertRaises(FileNotFoundError):
            archive.resolve("missing.dds")

    def test_offline_cache_is_hash_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Archive(offline=True)
            archive.sources = Path(temp)
            content = b"fixture"
            sha = hashlib.sha1(b"blob 7\0" + content).hexdigest()
            archive.entries = {"asset.bin": {"sha": sha}}
            target = Path(temp) / "asset.bin"
            target.write_bytes(content)
            self.assertEqual(archive.get("asset.bin"), target)
            target.write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                archive.get("asset.bin")


if __name__ == "__main__":
    unittest.main()
