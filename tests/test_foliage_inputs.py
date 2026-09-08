from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from metin_map_data import placements
from prepare_foliage import inspect_spt, tree_placement


class FoliageInputTests(unittest.TestCase):
    def test_unknown_and_truncated_envelopes_fail_without_geometry_claim(self):
        valid = struct.pack("<II", 1000, 12) + b"__IdvSpt_02_" + struct.pack("<I", 1002)
        self.assertFalse(inspect_spt(valid)["geometry_decoded"])
        for data in (b"", valid[:20], valid.replace(b"02_", b"03_"), valid[:-1] + b"\xff"):
            with self.assertRaises(ValueError):
                inspect_spt(data)

    def test_tree_uses_height_bias_but_preserves_unapplied_rotation(self):
        row = placements(
            "ObjectCount 1\nStart Object000\n100 -200 300\n42\n180\n-40\nEnd Object\n"
        )[0]
        result = tree_placement("002003", row)
        self.assertEqual(result["position_m"], [1.0, 2.6, 2.0])
        self.assertEqual(result["source_rotation_ypr_deg"], [0.0, 0.0, 180.0])
        self.assertFalse(result["apply_source_rotation"])
        self.assertEqual(result["id"], "002003:0")
