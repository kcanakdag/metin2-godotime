import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from metin_root_motion import (  # noqa: E402
    EXPECTED_INPUTS,
    source_cm_to_output_actor_local_m,
    validate_raw_metadata,
)

ACTION_ID = next(iter(EXPECTED_INPUTS))


def _raw() -> dict:
    return {
        "Animations": [
            {
                "Duration": 1.0,
                "TrackGroups": [
                    {
                        "Name": "Bip01",
                        "AccumulationFlags": 3,
                        "LoopTranslation": [0.0, -131.7569580078125, 0.0],
                        "PeriodicLoop": None,
                        "RootMotion": None,
                        "InitialPlacement": {
                            "flags": 2,
                            "position": [0.0, 0.0, 0.0],
                            "orientation": [0.0, 0.0, 0.0, 1.0],
                        },
                    }
                ],
            }
        ]
    }


def _validate(raw: dict) -> dict:
    return validate_raw_metadata(
        raw,
        action_id=ACTION_ID,
        duration_us=1_000_000,
        msa_accumulation_m=[0.0, 0.0, -1.3176],
        yaw_degrees=180.0,
    )


class RootMotionMetadataTests(unittest.TestCase):
    def test_projects_the_raw_loop_translation_once_with_zero_vertical_endpoint(self):
        result = _validate(_raw())
        self.assertEqual(
            result["endpoint_output_actor_local_godot_m"],
            [0.0, 0.0, -1.317569580078125],
        )
        self.assertLess(
            math.dist(
                result["msa_accumulation_output_actor_local_godot_m"],
                result["endpoint_output_actor_local_godot_m"],
            ),
            0.00004,
        )
        self.assertEqual(
            source_cm_to_output_actor_local_m([5.0, -100.0, 10.0], 180.0),
            [-0.05, 0.1, -1.0],
        )

    def test_rejects_wrong_counts_group_flags_and_unsupported_root_records(self):
        cases = {
            "no animation": lambda raw: raw.update(Animations=[]),
            "two animations": lambda raw: raw["Animations"].append(
                copy.deepcopy(raw["Animations"][0])
            ),
            "no group": lambda raw: raw["Animations"][0].update(TrackGroups=[]),
            "wrong group": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(Name="Other"),
            "boolean flags": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(
                AccumulationFlags=True
            ),
            "wrong flags": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(
                AccumulationFlags=1
            ),
            "periodic loop": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(
                PeriodicLoop={}
            ),
            "root motion": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(RootMotion={}),
            "missing periodic loop": lambda raw: raw["Animations"][0]["TrackGroups"][0].pop(
                "PeriodicLoop"
            ),
            "missing root motion": lambda raw: raw["Animations"][0]["TrackGroups"][0].pop(
                "RootMotion"
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                raw = _raw()
                mutate(raw)
                with self.assertRaises(ValueError):
                    _validate(raw)

    def test_rejects_nonfinite_bounded_vertical_duration_and_msa_mismatches(self):
        cases = {
            "nonfinite": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(
                LoopTranslation=[math.nan, 0.0, 0.0]
            ),
            "endpoint bound": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(
                LoopTranslation=[0.0, -201.0, 0.0]
            ),
            "vertical endpoint": lambda raw: raw["Animations"][0]["TrackGroups"][0].update(
                LoopTranslation=[0.0, -131.7569580078125, 1.0]
            ),
            "duration mismatch": lambda raw: raw["Animations"][0].update(Duration=0.9),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                raw = _raw()
                mutate(raw)
                with self.assertRaises(ValueError):
                    _validate(raw)
        with self.assertRaisesRegex(ValueError, "corroborate"):
            validate_raw_metadata(
                _raw(),
                action_id=ACTION_ID,
                duration_us=1_000_000,
                msa_accumulation_m=[0.0, 0.0, -1.0],
                yaw_degrees=180.0,
            )
        with self.assertRaisesRegex(ValueError, "180-degree"):
            source_cm_to_output_actor_local_m([0.0, -1.0, 0.0], 0.0)


if __name__ == "__main__":
    unittest.main()
