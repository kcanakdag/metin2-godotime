import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from motion_effects import motion_effect, resolve_attachment


def event():
    return {
        "event_type": 1,
        "event_name": "Event00",
        "start_us": 250000,
        "fields": {
            "MotionEventType": ["1"],
            "StartingTime": ["0.25"],
            "AttachingEnable": ["0"],
            "AttachingBoneName": ["Bip01 Head"],
            "EffectFileName": ["D:/Ymir Work/pc/warrior/effect/test.mse"],
            "EffectPosition": ["-100", "-80", "80"],
        },
    }


class MotionEffectTests(unittest.TestCase):
    def test_all_attachment_flag_combinations(self):
        for independent in (0, 1):
            for attaching in (0, 1):
                for following in (0, 1):
                    source = event()
                    source["fields"].update(
                        {
                            "IndependentFlag": [str(independent)],
                            "AttachingEnable": [str(attaching)],
                            "FollowingEnable": [str(following)],
                        }
                    )
                    expected = (
                        "capture_root"
                        if independent
                        else (
                            ("follow_bone" if following else "capture_bone")
                            if attaching
                            else "follow_root"
                        )
                    )
                    result = motion_effect(source, 1000000)
                    self.assertEqual(result["attachment"], expected)
                    self.assertEqual(
                        result["bone"], "Bip01 Head" if expected.endswith("bone") else ""
                    )

    def test_defaults_units_and_source_preservation(self):
        source = event()
        previous = copy.deepcopy(source)
        result = motion_effect(source, 1000000)
        self.assertEqual(result["position_m"], [-1, 0.8, 0.8])
        self.assertEqual(result["start_us"], 250000)
        self.assertEqual(result["attachment"], "follow_root")
        self.assertEqual(result["effect_path"], "ymir work/pc/warrior/effect/test.mse")
        self.assertEqual(source, previous)

    def test_missing_source_bone_has_original_follow_and_capture_behavior(self):
        source = event()
        source["fields"]["AttachingEnable"] = ["1"]
        source["fields"]["FollowingEnable"] = ["1"]
        effect = motion_effect(source, 1000000)
        result = resolve_attachment(effect, set(), set())
        self.assertEqual(result["attachment"], "follow_root")
        self.assertEqual(result["requested_bone"], "Bip01 Head")
        self.assertTrue(result["enabled"])
        effect["attachment"] = "capture_bone"
        self.assertFalse(resolve_attachment(effect, set(), set())["enabled"])

    def test_conversion_loss_cannot_be_hidden_by_legacy_fallback(self):
        source = event()
        source["fields"]["AttachingEnable"] = ["1"]
        effect = motion_effect(source, 1000000)
        bones = {"Bip01 Head"}
        self.assertTrue(resolve_attachment(effect, bones, bones)["enabled"])
        for original, converted in ((bones, set()), (set(), bones)):
            with self.assertRaises(ValueError):
                resolve_attachment(effect, original, converted)

    def test_malformed_metadata_rejected(self):
        for key, value in (
            ("Unknown", ["1"]),
            ("AttachingEnable", ["2"]),
            ("StartingTime", ["nan"]),
            ("StartingTime", ["0.5"]),
            ("EffectPosition", ["0", "0"]),
            ("EffectPosition", ["0", "inf", "0"]),
            ("EffectFileName", ["ymir work/../private.mse"]),
            ("EffectFileName", ["private.mse"]),
            ("AttachingBoneName", [""]),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                source = event()
                source["fields"][key] = value
                motion_effect(source, 1000000)
        with self.assertRaises(ValueError):
            motion_effect(event(), 200000)


if __name__ == "__main__":
    unittest.main()
