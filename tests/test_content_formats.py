# ruff: noqa: E402, I001

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from content_compile import (
    digest,
    load_profile,
    rotate_actor_local_vector,
    validate_server_payload,
)
from content_formats import (
    parse_legacy_script,
    parse_motion_list,
    parse_msa,
    virtual_path,
)


ATTACK_MSA = r"""
ScriptType MotionData
MotionFileName "D:\Ymir Work\monster\stray_dog\20.gr2"
MotionDuration 0.933333
Group AttackingData
{
  AttackType 0
  HittingType 2
  StiffenTime 0.000000
  InvisibleTime 0.300000
  ExternalForce 0.000000
  HitLimitCount 0
  MotionType 1
  HitDataCount 1
  Group HitData00
  {
    AttackingStartTime 0.320195
    AttackingEndTime 0.492782
    AttackingBone "Bip01 HeadNub"
    WeaponLength 0.000000
    List HitPosition
    {
      0.320195 -6.0 -96.0 155.0 -6.0 -96.0 155.0
    }
  }
}
"""


class ContentFormatTests(unittest.TestCase):
    def test_real_wild_dog_attack_shape_is_typed_and_converted_to_godot_units(self):
        motion = parse_msa(ATTACK_MSA)
        self.assertEqual(motion["motion_file"], "ymir work/monster/stray_dog/20.gr2")
        self.assertEqual(motion["duration_us"], 933_333)
        event = motion["events"][0]
        self.assertEqual(event["start_us"], 320_195)
        self.assertEqual(event["end_us"], 492_782)
        self.assertEqual(
            event["source_parameters"],
            {
                "attack_type": 0,
                "hitting_type": 2,
                "stiffen_us": 0,
                "invisible_us": 300_000,
                "external_force": 0.0,
                "hit_limit_count": 0,
                "motion_type": 1,
            },
        )
        self.assertEqual(event["samples"][0]["start_m"], [-0.06, 1.55, 0.96])

    def test_motion_event_unknown_type_is_preserved_in_unsupported_report(self):
        source = """
ScriptType MotionData
MotionFileName "d:/ymir work/pc/warrior/onehand_sword/combo_04.gr2"
MotionDuration 1.266667
Group MotionEventData
{
  MotionEventDataCount 1
  Group Event00
  {
    MotionEventType 2
    StartingTime 0.630086
    DuringTime 0.200000
    Power 300
  }
}
"""
        unsupported = parse_msa(source)["unsupported"]
        self.assertEqual(
            unsupported,
            [
                {
                    "kind": "motion_event",
                    "event_name": "Event00",
                    "event_type": 2,
                    "start_us": 630_086,
                    "end_us": 830_086,
                    "fields": {
                        "DuringTime": ["0.200000"],
                        "MotionEventType": ["2"],
                        "Power": ["300"],
                        "StartingTime": ["0.630086"],
                    },
                    "reason": "MotionEventType has no implemented semantic adapter",
                }
            ],
        )

    def test_declared_attack_count_and_window_bounds_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "HitDataCount"):
            parse_msa(ATTACK_MSA.replace("HitDataCount 1", "HitDataCount 2"))
        with self.assertRaisesRegex(ValueError, "exceeds clip"):
            parse_msa(ATTACK_MSA.replace("AttackingEndTime 0.492782", "AttackingEndTime 2.0"))

    def test_tokenizer_preserves_unquoted_and_empty_quoted_values(self):
        parsed = parse_legacy_script('ScriptType MotionData\nEmpty ""\nPath "a b"\n')
        self.assertEqual(
            parsed.fields,
            {"ScriptType": ["MotionData"], "Empty": [""], "Path": ["a b"]},
        )

    def test_actor_yaw_is_applied_to_normalized_motion_vectors(self):
        converted = rotate_actor_local_vector([-0.06, 1.55, 0.96], 180.0)
        self.assertAlmostEqual(converted[0], 0.06)
        self.assertAlmostEqual(converted[1], 1.55)
        self.assertAlmostEqual(converted[2], -0.96)

    def test_motion_list_and_virtual_paths_are_strict(self):
        self.assertEqual(
            parse_motion_list("GENERAL WAIT 00.msa 65\n"),
            [{"mode": "general", "action": "wait", "path": "00.msa", "weight": 65}],
        )
        for unsafe in ("../x", "a//b", "a/./b", "/rooted"):
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(ValueError, "Unsafe"):
                virtual_path(unsafe)

    def test_profile_rejects_duplicate_modes_weights_vectors_and_damage(self):
        source = json.loads((ROOT / "content/profiles/p0-warrior-dog.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)

            def rejected(mutator, message):
                profile = copy.deepcopy(source)
                mutator(profile)
                path = temporary / (message.replace(" ", "-") + ".json")
                path.write_text(json.dumps(profile))
                with self.assertRaisesRegex(ValueError, message):
                    load_profile(path)

            rejected(
                lambda p: p["actors"][0]["modes"].append(copy.deepcopy(p["actors"][0]["modes"][0])),
                "Duplicate mode ID",
            )
            rejected(
                lambda p: p["actors"][0]["modes"][0]["motions"][0].update(weights=[99, 0]),
                "Invalid variant weights",
            )
            rejected(
                lambda p: p["items"][0]["attachment_transform"].update(scale=[1, 1]),
                "Invalid scale",
            )
            rejected(
                lambda p: p["items"][0]["attachment_transform"].update(scale=[1, 0, 1]),
                "Invalid scale",
            )
            rejected(
                lambda p: p["trusted_gameplay"]["mob"].update(attack_range_m=float("nan")),
                "Invalid gameplay value",
            )
            rejected(
                lambda p: p["trusted_gameplay"]["player"].update(base_damage=70_000),
                "positive u16",
            )

    def test_trusted_payload_hash_and_windows_are_validated(self):
        payload = json.loads((ROOT / "server/content/p0-warrior-dog/actions.v1.json").read_text())
        validate_server_payload(payload, "p0-warrior-dog")
        bad = copy.deepcopy(payload)
        bad["actions"][0]["hit_windows"][0]["end_us"] = bad["actions"][0]["duration_us"] + 1
        bad["gameplay_definition_hash"] = digest(
            {key: value for key, value in bad.items() if key != "gameplay_definition_hash"}
        )
        with self.assertRaisesRegex(ValueError, "exceeds"):
            validate_server_payload(bad, "p0-warrior-dog")

        bad_quarter = copy.deepcopy(payload)
        bad_quarter["progression"]["quarter_thresholds_by_current_level"][1]["thresholds"][0] = 0
        bad_quarter["gameplay_definition_hash"] = digest(
            {key: value for key, value in bad_quarter.items() if key != "gameplay_definition_hash"}
        )
        with self.assertRaisesRegex(ValueError, "float32"):
            validate_server_payload(bad_quarter, "p0-warrior-dog")

        bad_delta = copy.deepcopy(payload)
        bad_delta["progression"]["normal_level_delta_percent"][0] = 1001
        bad_delta["gameplay_definition_hash"] = digest(
            {key: value for key, value in bad_delta.items() if key != "gameplay_definition_hash"}
        )
        with self.assertRaisesRegex(ValueError, "level-delta"):
            validate_server_payload(bad_delta, "p0-warrior-dog")
