import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from content_compile import (  # noqa: E402
    MOB_ACTION_ID,
    PLAYER_COMBO_ACTION_IDS,
    PLAYER_GENERAL_ACTION_ID,
    digest,
    load_profile,
    make_server_payload,
    validate_server_payload,
)


def _motion(action: str, action_id: str, *, duration_us: int, combo: dict | None) -> dict:
    return {
        "action": action,
        "action_id": action_id,
        "duration_us": duration_us,
        "events": [{"kind": "attack_window", "start_us": 10, "end_us": 20}],
        "combo": combo,
    }


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
    return {
        "content_hash": "a" * 64,
        "progression": trusted["progression"],
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
                            ["combo_1", "combo_2", "combo_4"],
                            ["combo_1", "combo_2", "combo_3"],
                        ],
                        "motions": [
                            _motion(
                                "combo_1",
                                PLAYER_COMBO_ACTION_IDS[0],
                                duration_us=100,
                                combo=combo_1,
                            ),
                            _motion(
                                "combo_2",
                                PLAYER_COMBO_ACTION_IDS[1],
                                duration_us=100,
                                combo=combo_2,
                            ),
                            _motion(
                                "combo_4",
                                "actor.player.warrior-male.onehand.combo_4",
                                duration_us=100,
                                combo={
                                    "pre_input_us": 10,
                                    "direct_input_us": 30,
                                    "input_limit_us": 20,
                                    "link_us": 1,
                                },
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
                            )
                        ],
                    }
                ],
            },
        ],
    }


def _rehash(payload: dict) -> None:
    payload["gameplay_definition_hash"] = digest(
        {key: value for key, value in payload.items() if key != "gameplay_definition_hash"}
    )


class ComboContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profile(ROOT / "content/profiles/p0-warrior-dog.json")

    def test_compiler_projects_only_the_declared_two_action_prefix(self):
        payload = make_server_payload(self.profile, _normalized_fixture())
        validate_server_payload(payload, "p0-warrior-dog")
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["base_combo_prefix"], list(PLAYER_COMBO_ACTION_IDS))
        self.assertEqual(len(payload["actions"]), 4)
        self.assertNotIn(
            "actor.player.warrior-male.onehand.combo_4",
            {action["id"] for action in payload["actions"]},
        )

    def test_compiler_rejects_malformed_declared_prefixes(self):
        cases = {
            "missing": (lambda mode: mode.update(combo_chains=[]), "requires declared"),
            "short": (lambda mode: mode.update(combo_chains=[["combo_1"]]), "at least two"),
            "disagree": (
                lambda mode: mode.update(
                    combo_chains=[["combo_1", "combo_2"], ["combo_1", "combo_3"]]
                ),
                "disagree",
            ),
            "duplicate": (
                lambda mode: mode.update(combo_chains=[["combo_1", "combo_1"]]),
                "distinct combo_1 then combo_2",
            ),
            "reversed": (
                lambda mode: mode.update(combo_chains=[["combo_2", "combo_1"]]),
                "distinct combo_1 then combo_2",
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


if __name__ == "__main__":
    unittest.main()
