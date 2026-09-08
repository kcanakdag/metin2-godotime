import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fly_definitions import parse_flight

SOURCE = """InitialVelocity 3000
Range 10000
BombEffect "impact.mse"
Group AttachData
{
Type 1
FlyType 1
AttachFile "arrow.mse"
TailFlag 1
TailColor 3435973836d
TailLength 0.18
TailSize 1
TailShapeRect 0
Roll 0
Distance 0
Period 1
Amplitude 0
}
"""
PATH = "ymir work/effect/monster/arrow.msf"


class FlyDefinitionTests(unittest.TestCase):
    def test_defaults_and_relative_dependencies_match_loader(self):
        row = parse_flight(SOURCE, PATH)
        self.assertEqual(row["flight"]["HomingMaxAngle"], 0)
        self.assertFalse(row["flight"]["HitOnBackground"])
        self.assertEqual(row["flight"]["Acceleration"], [0, 0, 0])
        self.assertEqual(row["bomb_effect"], "ymir work/effect/monster/impact.mse")
        self.assertEqual(row["attachments"][0]["tail"]["argb"], 3435973836)
        self.assertEqual(row["source_issues"], [])

    def test_negative_original_trail_is_preserved_without_inventing_dimensions(self):
        row = parse_flight(SOURCE.replace("TailLength 0.18", "TailLength -107374176"), PATH)
        tail = row["attachments"][0]["tail"]
        self.assertEqual(tail["length_seconds"], -107374176)
        self.assertEqual(tail["history_policy"], "expires-immediately")
        self.assertEqual(row["source_issues"][0]["reason"], "invalid-source-trail-dimensions")

    def test_required_values_and_unknown_or_unsafe_data_reject(self):
        for source in (
            SOURCE.replace("InitialVelocity 3000", "InitialVelocity nan"),
            SOURCE.replace("Range 10000", "Range -1"),
            SOURCE.replace("3435973836d", "999999999999d"),
            SOURCE.replace("arrow.mse", "../escape.mse"),
            SOURCE + "Unknown 1\n",
            SOURCE.replace("Period 1", "Period inf"),
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_flight(source, PATH)
