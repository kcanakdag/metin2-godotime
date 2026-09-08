import copy
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from content_compile import (  # noqa: E402
    MOB_ACTION_ID,
    PLAYER_COMBO_ACTION_IDS,
    PLAYER_GENERAL_ACTION_ID,
    _client_motion,
    digest,
    load_profile,
    make_server_payload,
    validate_server_payload,
)
from metin_root_motion import (  # noqa: E402
    CARBON_READER_SHA256,
    EXPECTED_INPUTS,
)

ROOT_FIXTURES = {
    PLAYER_COMBO_ACTION_IDS[0]: (1.0, -131.7569580078125, -1.3176, 2),
    PLAYER_COMBO_ACTION_IDS[1]: (0.9333333969116211, -85.2515640258789, -0.8525, 1),
    PLAYER_COMBO_ACTION_IDS[2]: (1.0666667222976685, -143.01394653320312, -1.4301, 3),
    PLAYER_COMBO_ACTION_IDS[3]: (1.2666667699813843, -119.64712524414062, -1.0552, 1),
}


def _root_source(action_id: str, duration_us: int) -> dict:
    raw_duration, source_y, msa_z, placement_flags = ROOT_FIXTURES[action_id]
    endpoint = [0.0, 0.0, source_y / 100.0]
    msa = [0.1289, 0.0, msa_z] if action_id == PLAYER_COMBO_ACTION_IDS[3] else [0.0, 0.0, msa_z]
    discrepancy = [msa[index] - endpoint[index] for index in range(3)]

    def decimals(values: list[float]) -> list[str]:
        return [format(value, ".17g") for value in values]

    pin = EXPECTED_INPUTS[action_id]
    return {
        "action_id": action_id,
        "source_gr2": {
            "path": pin["gr2_path"],
            "sha256": pin["gr2"],
            "bytes": pin["gr2_bytes"],
        },
        "source_msa": {
            "path": pin["msa_path"],
            "sha256": pin["msa"],
            "bytes": pin["msa_bytes"],
        },
        "carbon_reader": {
            "commit": "8cba23114bf1d30c9da597c1ecf49271e00b939d",
            "sha256": CARBON_READER_SHA256,
        },
        "animation_count": 1,
        "animation_duration_s_raw_decimal": format(raw_duration, ".17g"),
        "animation_duration_us_rounded": duration_us,
        "track_group_count": 1,
        "track_group_name": "Bip01",
        "accumulation_flags": 3,
        "loop_translation_source_cm_decimal": decimals([0.0, source_y, 0.0]),
        "endpoint_output_actor_local_godot_m_decimal": decimals(endpoint),
        "periodic_loop": None,
        "root_motion": None,
        "initial_placement": {
            "flags": placement_flags,
            "position_source_cm_decimal": decimals([0.0, 0.0, 0.0]),
            "orientation_xyzw_decimal": decimals([0.0, 0.0, 0.0, 1.0]),
        },
        "msa_accumulation_output_actor_local_godot_m_decimal": decimals(msa),
        "msa_discrepancy_output_actor_local_godot_m_decimal": decimals(discrepancy),
        "msa_validation": (
            "pinned-combo4-discrepancy-exception"
            if action_id == PLAYER_COMBO_ACTION_IDS[3]
            else "strict-rounded-corroboration"
        ),
    }


def _motion(
    action: str,
    action_id: str,
    *,
    duration_us: int,
    combo: dict | None,
    root_source: dict | None = None,
) -> dict:
    result = {
        "action": action,
        "action_id": action_id,
        "duration_us": duration_us,
        "events": [
            {
                "kind": "attack_window",
                "start_us": 10,
                "end_us": 20,
                "source_parameters": {
                    "invisible_us": {
                        PLAYER_GENERAL_ACTION_ID: 500_000,
                        PLAYER_COMBO_ACTION_IDS[0]: 100_000,
                        PLAYER_COMBO_ACTION_IDS[1]: 100_000,
                        PLAYER_COMBO_ACTION_IDS[2]: 200_000,
                        PLAYER_COMBO_ACTION_IDS[3]: 100_000,
                        MOB_ACTION_ID: 300_000,
                    }.get(action_id, 0)
                },
            }
        ],
        "combo": combo,
    }
    if action == "combo_4":
        result["events"] = [
            {
                "kind": "attack_window",
                "start_us": 0,
                "end_us": 0,
                "sample_count": 0,
                "source_parameters": {"invisible_us": 100_000},
            },
            {
                "kind": "attack_area",
                "start_us": 659_316,
                "end_us": 859_316,
                "attack_type": 0,
                "hitting_type": 1,
                "stiffen_us": 0,
                "invisible_us": 300_000,
                "external_force": 17.0,
                "collision_type": 0,
                "spheres": [{"position_m": [0.0, 0.0, -1.2], "radius_m": 1.0}],
            },
        ]
    if root_source is not None:
        result["root_motion_source"] = root_source
    return result


def _normalized_fixture() -> dict:
    trusted = json.loads((ROOT / "server/content/p0-warrior-dog/actions.v1.json").read_text())
    combo_1 = {
        "pre_input_us": 1,
        "direct_input_us": 2,
        "input_limit_us": 3,
        "link_us": 4,
    }
    combo_2 = {
        "pre_input_us": 5,
        "direct_input_us": 6,
        "input_limit_us": 7,
        "link_us": 8,
    }
    combo_3 = {
        "pre_input_us": 9,
        "direct_input_us": 10,
        "input_limit_us": 11,
        "link_us": 12,
    }
    combo_4 = {
        "pre_input_us": 1_057_692,
        "direct_input_us": 1_057_692,
        "input_limit_us": 730_769,
        "link_us": 0,
    }
    return {
        "content_hash": "a" * 64,
        "progression": trusted["progression"],
        "item_catalog": trusted["item_catalog"],
        "actors": [
            {
                "id": "actor.player.warrior-male",
                "kind": "player",
                "race_id": 0,
                "model_key": "warrior_m",
                "modes": [
                    {
                        "id": "general",
                        "required_item_vnums": [],
                        "combo_chains": [],
                        "motions": [
                            _motion(
                                "normal_attack",
                                PLAYER_GENERAL_ACTION_ID,
                                duration_us=100,
                                combo=None,
                            )
                        ],
                    },
                    {
                        "id": "onehand",
                        "required_item_vnums": [10],
                        "combo_chains": [
                            ["combo_1", "combo_2", "combo_3", "combo_4"],
                            ["combo_1", "combo_2", "combo_3", "combo_4"],
                        ],
                        "motions": [
                            _motion(
                                "combo_1",
                                PLAYER_COMBO_ACTION_IDS[0],
                                duration_us=1_000_000,
                                combo=combo_1,
                                root_source=_root_source(PLAYER_COMBO_ACTION_IDS[0], 1_000_000),
                            ),
                            _motion(
                                "combo_2",
                                PLAYER_COMBO_ACTION_IDS[1],
                                duration_us=933_333,
                                combo=combo_2,
                                root_source=_root_source(PLAYER_COMBO_ACTION_IDS[1], 933_333),
                            ),
                            _motion(
                                "combo_3",
                                PLAYER_COMBO_ACTION_IDS[2],
                                duration_us=1_066_667,
                                combo=combo_3,
                                root_source=_root_source(PLAYER_COMBO_ACTION_IDS[2], 1_066_667),
                            ),
                            _motion(
                                "combo_4",
                                PLAYER_COMBO_ACTION_IDS[3],
                                duration_us=1_266_667,
                                combo=combo_4,
                                root_source=_root_source(PLAYER_COMBO_ACTION_IDS[3], 1_266_667),
                            ),
                        ],
                    },
                ],
            },
            {
                "id": "actor.mob.wild-dog-101",
                "kind": "mob",
                "vnum": 101,
                "model_key": "wild_dog_101",
                "modes": [
                    {
                        "id": "general",
                        "required_item_vnums": [],
                        "combo_chains": [],
                        "motions": [
                            _motion(
                                "normal_attack",
                                MOB_ACTION_ID,
                                duration_us=100,
                                combo=None,
                            ),
                            _motion(
                                "front_knockdown",
                                "actor.mob.wild-dog-101.general.front_knockdown",
                                duration_us=1_166_667,
                                combo=None,
                            ),
                            _motion(
                                "front_standup",
                                "actor.mob.wild-dog-101.general.front_standup",
                                duration_us=1_000_000,
                                combo=None,
                            ),
                            _motion(
                                "back_knockdown",
                                "actor.mob.wild-dog-101.general.back_knockdown",
                                duration_us=1_166_667,
                                combo=None,
                            ),
                        ],
                    }
                ],
            },
        ],
        "catalog_validation": {
            "race_collision": {
                "actor.mob.wild-dog-101": [
                    {
                        "bone": "Bip01",
                        "collision_type": 3,
                        "spheres": [{"position_m": [0.0, 0.8, 0.1], "radius_m": 0.9}],
                    }
                ]
            }
        },
        "adapted_motion_events": [
            {
                "actor_id": "actor.player.warrior-male",
                "action_id": PLAYER_COMBO_ACTION_IDS[3],
                "source": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_04.msa",
                "kind": "motion_event",
                "event_name": "Event00",
                "event_type": 2,
                "start_us": 630_086,
                "end_us": 830_086,
                "fields": {
                    "AffectingRange": ["200"],
                    "DuringTime": ["0.200000"],
                    "MotionEventType": ["2"],
                    "Power": ["300"],
                    "StartingTime": ["0.630086"],
                },
                "reason": "MotionEventType has no implemented semantic adapter",
                "adapter": "screen-wave-schema5",
            }
        ],
        "unsupported": [],
    }


def _rehash(payload: dict) -> None:
    payload["gameplay_definition_hash"] = digest(
        {key: value for key, value in payload.items() if key != "gameplay_definition_hash"}
    )


class ComboContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profile(ROOT / "content/profiles/p0-warrior-dog.json")

    def test_compiler_projects_only_the_declared_four_action_prefix(self):
        payload = make_server_payload(self.profile, _normalized_fixture())
        validate_server_payload(payload, "p0-warrior-dog")
        self.assertEqual(payload["schema_version"], 8)
        self.assertEqual(payload["base_combo_prefix"], list(PLAYER_COMBO_ACTION_IDS))
        self.assertEqual(len(payload["actions"]), 6)
        terminal = next(
            action for action in payload["actions"] if action["id"] == PLAYER_COMBO_ACTION_IDS[3]
        )
        self.assertEqual(terminal["hit_windows"], [])
        self.assertNotIn("combo_input", terminal)

    def test_compiler_rejects_malformed_declared_prefixes(self):
        cases = {
            "missing": (lambda mode: mode.update(combo_chains=[]), "requires declared"),
            "short": (lambda mode: mode.update(combo_chains=[["combo_1"]]), "at least three"),
            "disagree": (
                lambda mode: mode.update(
                    combo_chains=[
                        ["combo_1", "combo_2", "combo_3", "combo_4"],
                        ["combo_1", "combo_2", "combo_5", "combo_4"],
                    ]
                ),
                "disagree",
            ),
            "duplicate": (
                lambda mode: mode.update(
                    combo_chains=[["combo_1", "combo_2", "combo_2", "combo_4"]]
                ),
                "distinct combo_1 through terminal combo_4",
            ),
            "reversed": (
                lambda mode: mode.update(
                    combo_chains=[["combo_2", "combo_1", "combo_3", "combo_4"]]
                ),
                "distinct combo_1 through terminal combo_4",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name=name):
                normalized = _normalized_fixture()
                mutate(normalized["actors"][0]["modes"][1])
                with self.assertRaisesRegex(ValueError, message):
                    make_server_payload(self.profile, normalized)

    def test_compiler_rejects_missing_duplicate_and_inverted_selected_motions(self):
        for name, mutate, message in (
            (
                "missing",
                lambda motions: motions.pop(1),
                "exactly one selected combo motion",
            ),
            (
                "duplicate",
                lambda motions: motions.append(copy.deepcopy(motions[0])),
                "exactly one selected combo motion",
            ),
            (
                "inverted",
                lambda motions: motions[0]["combo"].update(input_limit_us=2),
                "strictly ordered",
            ),
        ):
            with self.subTest(name=name):
                normalized = _normalized_fixture()
                mutate(normalized["actors"][0]["modes"][1]["motions"])
                with self.assertRaisesRegex(ValueError, message):
                    make_server_payload(self.profile, normalized)

    def test_compiler_requires_raw_root_metadata_for_each_selected_motion(self):
        for action_id in PLAYER_COMBO_ACTION_IDS:
            with self.subTest(action_id=action_id):
                normalized = _normalized_fixture()
                motion = next(
                    motion
                    for motion in normalized["actors"][0]["modes"][1]["motions"]
                    if motion["action_id"] == action_id
                )
                motion.pop("root_motion_source")
                with self.assertRaisesRegex(ValueError, "no raw root-motion metadata"):
                    make_server_payload(self.profile, normalized)

    def test_serialized_validator_rejects_duplicate_prefix_and_timing_shapes(self):
        valid = make_server_payload(self.profile, _normalized_fixture())
        combo_index = next(
            index
            for index, action in enumerate(valid["actions"])
            if action["id"] == PLAYER_COMBO_ACTION_IDS[0]
        )
        cases = {
            "typed action id": (
                lambda payload: payload["actions"][0].update(id={"bad": "id"}),
                "nonempty strings",
            ),
            "typed actor row": (
                lambda payload: payload["actors"].__setitem__(0, ["bad"]),
                "require actors",
            ),
            "duplicate action": (
                lambda payload: payload["actions"].__setitem__(
                    0, copy.deepcopy(payload["actions"][1])
                ),
                "unique",
            ),
            "reversed prefix": (
                lambda payload: payload.update(
                    base_combo_prefix=list(reversed(PLAYER_COMBO_ACTION_IDS))
                ),
                "prefix",
            ),
            "missing timing": (
                lambda payload: payload["actions"][combo_index].pop("combo_input"),
                "exactly four",
            ),
            "extra timing": (
                lambda payload: payload["actions"][combo_index]["combo_input"].update(extra=1),
                "exactly four",
            ),
            "boolean timing": (
                lambda payload: payload["actions"][combo_index]["combo_input"].update(
                    pre_input_us=False
                ),
                "exact integers",
            ),
            "inverted timing": (
                lambda payload: payload["actions"][combo_index]["combo_input"].update(
                    direct_input_us=3
                ),
                "strictly ordered",
            ),
            "overbound link": (
                lambda payload: payload["actions"][combo_index]["combo_input"].update(
                    link_us=60_000_001
                ),
                "outside the supported bound",
            ),
            "overbound duration": (
                lambda payload: payload["actions"][combo_index].update(duration_us=60_000_001),
                "1..=60000000",
            ),
            "nonprefix timing": (
                lambda payload: payload["actions"][0].update(
                    combo_input={
                        "pre_input_us": 1,
                        "direct_input_us": 2,
                        "input_limit_us": 3,
                        "link_us": 4,
                    }
                ),
                "must omit",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name=name):
                payload = copy.deepcopy(valid)
                mutate(payload)
                _rehash(payload)
                with self.assertRaisesRegex(ValueError, message):
                    validate_server_payload(payload, "p0-warrior-dog")

    def test_serialized_validator_rejects_malformed_root_motion_and_provenance(self):
        valid = make_server_payload(self.profile, _normalized_fixture())
        combo_index = next(
            index
            for index, action in enumerate(valid["actions"])
            if action["id"] == PLAYER_COMBO_ACTION_IDS[0]
        )
        cases = {
            "policy": (
                lambda payload: payload["root_motion_policy"].update(id="linear"),
                "policy",
            ),
            "reordered sources": (
                lambda payload: payload["root_motion_sources"].reverse(),
                "reordered",
            ),
            "missing root": (
                lambda payload: payload["actions"][combo_index].pop("root_motion"),
                "exactly x, z, and duration",
            ),
            "extra root field": (
                lambda payload: payload["actions"][combo_index]["root_motion"].update(extra=1),
                "exactly x, z, and duration",
            ),
            "nonfinite endpoint": (
                lambda payload: payload["actions"][combo_index]["root_motion"].update(
                    endpoint_x_m=math.nan
                ),
                "finite",
            ),
            "endpoint bound": (
                lambda payload: payload["actions"][combo_index]["root_motion"].update(
                    endpoint_z_m=-2.01
                ),
                "supported bound",
            ),
            "root duration": (
                lambda payload: payload["actions"][combo_index]["root_motion"].update(
                    duration_us=1_600_001
                ),
                "duration",
            ),
            "raw hash": (
                lambda payload: payload["root_motion_sources"][0]["source_gr2"].update(
                    sha256="0" * 64
                ),
                "provenance",
            ),
            "wrong flags": (
                lambda payload: payload["root_motion_sources"][0].update(accumulation_flags=1),
                "unsupported",
            ),
            "non-null root field": (
                lambda payload: payload["root_motion_sources"][0].update(root_motion={}),
                "unsupported",
            ),
            "vertical endpoint": (
                lambda payload: payload["root_motion_sources"][0].update(
                    loop_translation_source_cm_decimal=["0", "-131.7569580078125", "1"]
                ),
                "coordinate conversion",
            ),
            "MSA mismatch": (
                lambda payload: payload["root_motion_sources"][0].update(
                    msa_accumulation_output_actor_local_godot_m_decimal=["0", "0", "-1"]
                ),
                "discrepancy evidence",
            ),
            "nonprefix root": (
                lambda payload: payload["actions"][0].update(
                    root_motion={"endpoint_x_m": 0.0, "endpoint_z_m": 0.0, "duration_us": 100}
                ),
                "must omit",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name=name):
                payload = copy.deepcopy(valid)
                mutate(payload)
                _rehash(payload)
                with self.assertRaisesRegex(ValueError, message):
                    validate_server_payload(payload, "p0-warrior-dog")

    def test_schema5_finisher_metadata_and_client_wave_projection_are_strict(self):
        valid = make_server_payload(self.profile, _normalized_fixture())
        terminal = next(
            action for action in valid["actions"] if action["id"] == PLAYER_COMBO_ACTION_IDS[3]
        )
        self.assertEqual(
            _client_motion(
                {
                    "action_id": terminal["id"],
                    "action": "combo_4",
                    "variant": 1,
                    "weight": 100,
                    "godot_name": "combo4",
                    "duration_us": 1_266_667,
                    "loop": False,
                    "accumulation_m": [],
                    "events": [],
                    "combo": {},
                    "fallback_mode": None,
                },
                terminal,
            )["screen_wave"],
            {"activation_offset_us": 633_334, "duration_us": 200_000, "viewer_range_m": 2.0},
        )
        cases = (
            lambda payload: next(
                action
                for action in payload["actions"]
                if action["id"] == PLAYER_COMBO_ACTION_IDS[3]
            )["special_area"].update(activation_offset_us=659_316),
            lambda payload: next(
                action
                for action in payload["actions"]
                if action["id"] == PLAYER_COMBO_ACTION_IDS[3]
            )["special_area"].update(max_targets=16.0),
            lambda payload: next(
                action
                for action in payload["actions"]
                if action["id"] == PLAYER_COMBO_ACTION_IDS[3]
            )["screen_wave"].update(legacy_dispatch_frame=38),
            lambda payload: next(
                action
                for action in payload["actions"]
                if action["id"] == PLAYER_COMBO_ACTION_IDS[1]
            ).update(ordinary_hit_invulnerability_us=300_000),
            lambda payload: next(
                actor for actor in payload["actors"] if actor["id"] == "actor.mob.wild-dog-101"
            )["defending_sphere"].update(radius_m=0.8),
            lambda payload: next(
                actor for actor in payload["actors"] if actor["id"] == "actor.mob.wild-dog-101"
            )["great_hit_reactions"][0].update(duration_us=1),
            lambda payload: payload["root_motion_sources"][3].update(
                msa_validation="strict-rounded-corroboration"
            ),
        )
        for mutate in cases:
            payload = copy.deepcopy(valid)
            mutate(payload)
            _rehash(payload)
            with self.assertRaises(ValueError):
                validate_server_payload(payload, "p0-warrior-dog")


if __name__ == "__main__":
    unittest.main()
