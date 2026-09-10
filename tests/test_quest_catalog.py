"""Regression tests for the compiled quest catalog and its op vocabulary.

The catalog is the contract between the authored profiles, the authoritative
Rust op executor and the client dialogue presenter. These tests pin what the
opening quest line actually ships: the state machine, the closed op vocabulary,
the reward payloads, and the documented divergence between the original
localization prose and the original operation calls.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

from tools.build_quest_catalog import (
    OP_FIELDS,
    SCHEMA,
    VERSION,
    build,
    compile_catalog,
    compile_op,
    load_translations,
    resolve_text,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "content/profiles/classic-quests-opening.json"
INSTALLED = ROOT / "client/assets/imported/quests/catalog.v1.json"
SOURCE = ROOT / ".cache/full-game-research/server/source"
MAP_HASH = ROOT / "server/content/yongan.sha256"
ITEM_PROFILE = ROOT / "content/profiles/p0-warrior-dog.json"
SERVER_QUEST = ROOT / "server/src/quest.rs"
SERVER_BUILD = ROOT / "server/build_quests.rs"
SECURITY_NOTES = ROOT / "docs/rebuild/original-security-notes.md"
TEXT_FIELDS = ("title", "body", "text", "label", "options")

# Accepted reward payloads for the opening line, transcribed from the original
# quest scripts. The prose the original client printed disagrees with several of
# these numbers; the operations win and the divergence is documented below.
ACCEPTED_REWARDS = {
    ("main_quest_lv2", "gototeacher2"): [
        {"op": "give_exp", "amount": 250},
        {"op": "give_money", "amount": 1000},
        {"op": "give_item", "vnum": 27001, "count": 15},
    ],
    ("main_quest_lv3", "gotodefend"): [
        {"op": "give_exp", "amount": 450},
        {"op": "give_money", "amount": 5000},
        {"op": "give_item", "vnum": 27004, "count": 20},
    ],
    ("find_squareguard", "find"): [{"op": "give_money", "amount": 200}],
    ("find_squareguard", "buy"): [{"op": "give_item", "vnum": 27001, "count": 5}],
    ("find_squareguard", "deliver"): [
        {"op": "remove_item", "vnum": 27001, "count": 1},
        {"op": "random_item", "choices": [14000, 16000, 17000], "count": 1},
    ],
}

REWARD_OPS = {"give_exp", "give_money", "give_item", "remove_item", "random_item"}
ITEM_OPS = {"give_item", "remove_item", "say_reward_item", "say_item"}

# Operation kinds the runtime and compiler already implement but the selected
# opening quest profile does not exercise yet. The gap stays explicit so that
# adding a quest which uses one of them (or deleting the support) fails the
# vocabulary test until this list is refreshed.
OPS_NOT_IN_OPENING_PROFILE = {"say_reward_value"}


def walk_ops(ops: list[dict]):
    """Yield every op, including the ones nested in ``count`` and ``select``."""

    for op in ops:
        yield op
        yield from walk_ops(op.get("on_reached", []))
        for branch in op.get("branches", []):
            yield from walk_ops(branch)


def state_ops(state: dict) -> list[dict]:
    ops = list(state["enter"])
    for trigger in state["triggers"]:
        ops.extend(trigger["ops"])
    return ops


def say_bodies(ops: list[dict]) -> list[str]:
    return [op["body"] for op in walk_ops(ops) if op["op"] == "say"]


def canonical_hash(catalog: dict) -> str:
    canonical = json.dumps(
        {
            "schema": catalog["schema"],
            "version": catalog["version"],
            "map_id": catalog["map_id"],
            "order": catalog["order"],
            "quests": catalog["quests"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class QuestCatalogTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        if not SOURCE.is_dir():
            raise unittest.SkipTest(f"Pinned reference source is missing: {SOURCE}")
        cls.profile = json.loads(PROFILE.read_text())
        cls.strings = load_translations(SOURCE / "gamefiles/data/translate_en.lua")
        cls.map_hash = MAP_HASH.read_text().strip()
        cls.catalog = build(PROFILE, SOURCE, cls.map_hash)
        cls.installed = json.loads(INSTALLED.read_text())

    def trigger_by(self, quest: str, state: str, **conditions) -> dict:
        for trigger in self.catalog["quests"][quest]["states"][state]["triggers"]:
            if all(trigger.get(key) == value for key, value in conditions.items()):
                return trigger
        raise AssertionError(f"{quest}.{state} has no trigger matching {conditions}")

    def test_installed_catalog_is_the_pinned_deterministic_build(self) -> None:
        self.assertEqual(self.installed, self.catalog)
        self.assertEqual(build(PROFILE, SOURCE, self.map_hash), self.catalog)
        self.assertEqual(
            INSTALLED.read_text(),
            json.dumps(self.catalog, indent=1, sort_keys=True) + "\n",
            "the installed catalog must be byte-identical to a fresh build",
        )
        self.assertEqual(self.catalog["schema"], SCHEMA)
        self.assertEqual(self.catalog["version"], VERSION)
        self.assertEqual(self.catalog["map_id"], "metin2_map_a1")
        self.assertEqual(self.catalog["map_hash"], self.map_hash)
        self.assertEqual(
            self.catalog["order"],
            ["main_quest_lv1", "main_quest_lv2", "main_quest_lv3", "find_squareguard"],
        )

    def test_content_hash_covers_behaviour_and_excludes_provenance(self) -> None:
        self.assertEqual(self.catalog["content_hash"], canonical_hash(self.catalog))
        changed = copy.deepcopy(self.catalog)
        reward = next(
            op
            for op in walk_ops(
                state_ops(changed["quests"]["main_quest_lv2"]["states"]["gototeacher2"])
            )
            if op["op"] == "give_exp"
        )
        reward["amount"] += 1
        self.assertNotEqual(canonical_hash(changed), self.catalog["content_hash"])
        changed = copy.deepcopy(self.catalog)
        changed["quests"]["find_squareguard"]["states"]["deliver"]["enter"][0]["title"] += " "
        self.assertNotEqual(canonical_hash(changed), self.catalog["content_hash"])
        for field, value in (
            ("map_hash", "0" * 64),
            ("forward_quest_refs", []),
            ("notes", []),
            ("source", {"repository": "https://example.invalid/", "revision": "0" * 40}),
            ("content_hash", "0" * 64),
        ):
            changed = copy.deepcopy(self.catalog)
            changed[field] = value
            self.assertEqual(
                canonical_hash(changed),
                self.catalog["content_hash"],
                f"{field} must stay outside the content hash",
            )

    def test_source_provenance_binds_the_reference_scripts(self) -> None:
        source = self.installed["source"]
        self.assertEqual(
            set(source), {"repository", "revision", "quests", "translate_sha256", "quest_sha256"}
        )
        self.assertEqual(source["repository"], "https://git.old-metin2.com/")
        self.assertEqual(source["revision"], "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318")
        self.assertEqual(
            source["quests"],
            [
                "gamefiles/data/quest/main_quest_lv1.quest",
                "gamefiles/data/quest/main_quest_lv2.quest",
                "gamefiles/data/quest/main_quest_lv3.quest",
                "gamefiles/data/quest/find_squareguard.quest",
            ],
        )
        for relative in source["quests"]:
            payload = (SOURCE / relative).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), source["quest_sha256"][relative])
        translate = SOURCE / "gamefiles/data/translate_en.lua"
        self.assertEqual(
            hashlib.sha256(translate.read_bytes()).hexdigest(), source["translate_sha256"]
        )

    def test_op_vocabulary_matches_the_server_executor(self) -> None:
        text = SERVER_QUEST.read_text()
        executor = text[text.index("fn run_ops_collecting(") : text.index("fn item_name(")]
        implemented = set(re.findall(r'^\s+"([a-z_]+)" =>', executor, re.MULTILINE))
        self.assertEqual(implemented, set(OP_FIELDS))
        used: set[str] = set()
        for quest_id, quest in self.catalog["quests"].items():
            for state_name, state in quest["states"].items():
                for op in walk_ops(state_ops(state)):
                    used.add(op["op"])
                    self.assertIn(op["op"], OP_FIELDS)
                    self.assertEqual(
                        set(op),
                        {"op", *OP_FIELDS[op["op"]]},
                        f"{quest_id}.{state_name} op {op['op']} carries the wrong fields",
                    )
        self.assertFalse(used - set(OP_FIELDS), "the catalog used an unknown op")
        self.assertEqual(
            set(OP_FIELDS) - used,
            OPS_NOT_IN_OPENING_PROFILE,
            "every compiled op should be exercised or listed as a documented profile gap",
        )

    def test_numbers_stay_inside_the_documented_ranges(self) -> None:
        for quest_id, quest in self.catalog["quests"].items():
            for state_name, state in quest["states"].items():
                label = f"{quest_id}.{state_name}"
                for op in walk_ops(state_ops(state)):
                    kind = op["op"]
                    if kind in ITEM_OPS:
                        self.assertTrue(1 <= op["vnum"] < 2**32, f"{label} vnum out of range")
                    if kind in {"give_item", "remove_item", "say_reward_item", "random_item"}:
                        self.assertTrue(1 <= op["count"] <= 65535, f"{label} count out of range")
                    if kind in {"give_exp", "give_money"}:
                        self.assertGreater(op["amount"], 0, f"{label} grants nothing")
                    if kind in {"count", "objective"}:
                        self.assertTrue(1 <= op["total"] <= 100_000, f"{label} total out of range")
                    if kind == "random_item":
                        self.assertTrue(op["choices"], f"{label} has no random choice")
                        self.assertEqual(len(set(op["choices"])), len(op["choices"]))
                        self.assertTrue(all(1 <= vnum < 2**32 for vnum in op["choices"]))
                    if kind == "say_reward_counter":
                        self.assertEqual(op["source"], "objective")

    def test_states_are_reachable_terminating_and_single_entry(self) -> None:
        authored = set(self.catalog["order"])
        for quest_id in self.catalog["order"]:
            states = self.catalog["quests"][quest_id]["states"]
            self.assertIn("__COMPLETE__", states, f"{quest_id} has no completion state")
            complete = states["__COMPLETE__"]
            self.assertEqual(complete["triggers"], [], f"{quest_id} completion can still react")
            self.assertEqual(complete["enter"], [], f"{quest_id} completion still runs ops")
            entry = next(name for name in ("run", "start") if name in states)
            alias = "start" if entry == "run" else "run"
            expected = set(states)
            if alias in states:
                self.assertEqual(
                    states[alias],
                    {"enter": [], "triggers": []},
                    f"{quest_id}.{alias} is a second live entry point",
                )
                expected.discard(alias)
            reachable = {entry}
            for _ in range(len(states)):
                for name in list(reachable):
                    for op in walk_ops(state_ops(states[name])):
                        if op["op"] == "set_state":
                            self.assertIn(
                                op["state"], states, f"{quest_id} -> {op['state']} undeclared"
                            )
                            reachable.add(op["state"])
                        if op["op"] == "set_quest_state":
                            self.assertTrue(
                                op["quest"] in authored
                                or op["quest"] in self.catalog["forward_quest_refs"],
                                f"{quest_id} advances unauthored quest {op['quest']}",
                            )
            self.assertEqual(
                reachable,
                expected,
                f"{quest_id} declares unreachable states: {sorted(expected - reachable)}",
            )
        self.assertEqual(self.catalog["forward_quest_refs"], ["main_quest_lv6"])

    def test_one_event_cannot_fire_two_identical_triggers(self) -> None:
        for quest_id in self.catalog["order"]:
            for state_name, state in self.catalog["quests"][quest_id]["states"].items():
                signatures = []
                for trigger in state["triggers"]:
                    conditions = tuple(
                        sorted(
                            (key, value)
                            for key, value in trigger.items()
                            if key not in {"event", "ops"}
                        )
                    )
                    signatures.append((trigger["event"], conditions))
                self.assertEqual(
                    len(signatures),
                    len(set(signatures)),
                    f"{quest_id}.{state_name} can fire two triggers for one event",
                )

    def test_selection_options_stay_paired_with_branches(self) -> None:
        found = []
        for quest_id in self.catalog["order"]:
            for state_name, state in self.catalog["quests"][quest_id]["states"].items():
                for op in walk_ops(state_ops(state)):
                    if op["op"] != "select":
                        continue
                    found.append((quest_id, state_name))
                    self.assertEqual(
                        len(op["options"]),
                        len(op["branches"]),
                        f"{quest_id}.{state_name} offers an option without a branch",
                    )
                    for option in op["options"]:
                        self.assertTrue(
                            option.strip(), f"{quest_id}.{state_name} has a blank option"
                        )
        self.assertEqual(
            found,
            [("main_quest_lv2", "killdog"), ("find_squareguard", "find")],
            "the opening line ships exactly these two choice points",
        )

    def test_give_up_branch_is_operator_only_and_optional(self) -> None:
        operator_triggers = []
        for quest_id in self.catalog["order"]:
            for state_name, state in self.catalog["quests"][quest_id]["states"].items():
                for trigger in state["triggers"]:
                    if trigger.get("operator_only"):
                        operator_triggers.append((quest_id, state_name, trigger))
        self.assertEqual(len(operator_triggers), 1)
        quest_id, state_name, trigger = operator_triggers[0]
        self.assertEqual((quest_id, state_name), ("main_quest_lv2", "killdog"))
        self.assertEqual((trigger["event"], trigger["npc_vnum"]), ("npc_chat", 20354))
        self.assertEqual(trigger["objective_max"], 8)
        select = trigger["ops"][-1]
        self.assertEqual(select["op"], "select")
        self.assertEqual(select["options"], ["Yes ", "No "])
        self.assertEqual(select["branches"][1], [], "declining must not change the quest state")
        self.assertEqual(select["branches"][0], [{"op": "set_state", "state": "gototeacher2"}])
        nag = self.trigger_by("main_quest_lv2", "killdog", event="npc_chat", objective_max=8)
        self.assertNotIn("operator_only", nag)
        self.assertNotIn("set_state", {op["op"] for op in nag["ops"]})
        self.assertEqual(
            self.trigger_by("main_quest_lv2", "killdog", event="npc_chat", objective_min=9)["ops"][
                -1
            ],
            {"op": "set_state", "state": "gototeacher2"},
        )

    def test_kill_objective_tracks_nine_wild_dogs(self) -> None:
        state = self.catalog["quests"]["main_quest_lv2"]["states"]["killdog"]
        objective = next(op for op in state["enter"] if op["op"] == "objective")
        self.assertEqual((objective["total"], objective["display"]), (9, "remaining"))
        counter = self.trigger_by("main_quest_lv2", "killdog", event="kill")
        self.assertEqual(counter["vnum"], 101)
        self.assertEqual(counter["ops"][0]["op"], "count")
        self.assertEqual(counter["ops"][0]["total"], 9)
        self.assertEqual(
            counter["ops"][0]["on_reached"][-1], {"op": "set_state", "state": "gototeacher2"}
        )

    def test_city_guard_click_keeps_its_own_lines_while_entering_a_notice(self) -> None:
        # The City Guard's click is both the conversation and the hand-off: his
        # trigger speaks, then `find_squareguard.find` says where to go next.
        # The panel must show the guard, so the runtime prefers interaction text
        # over a reached state's notice (see `presented` in server/src/quest.rs).
        trigger = self.trigger_by(
            "main_quest_lv1", "gototeacher", event="npc_click", npc_vnum=20354
        )
        guard_lines = say_bodies(trigger["ops"])
        self.assertEqual(len(guard_lines), 2, "the guard's opening is two lines")
        self.assertIn("You must be new in town!", guard_lines[0])
        self.assertIn("Now go and learn some basics", guard_lines[1])
        self.assertEqual(
            [op for op in walk_ops(trigger["ops"]) if op["op"] == "set_state"],
            [{"op": "set_state", "state": "__COMPLETE__"}],
        )
        handoff = [
            op
            for op in walk_ops(trigger["ops"])
            if op["op"] == "set_quest_state" and op["quest"] == "find_squareguard"
        ]
        self.assertEqual(
            handoff, [{"op": "set_quest_state", "quest": "find_squareguard", "state": "find"}]
        )
        notice = say_bodies(self.catalog["quests"]["find_squareguard"]["states"]["find"]["enter"])
        self.assertTrue(
            any("Go to the centre of the village" in body for body in notice),
            "the hand-off state must carry the notice that loses to the guard's speech",
        )

    def test_accepted_rewards_are_exact_and_prose_divergence_is_documented(self) -> None:
        for (quest_id, state_name), expected in ACCEPTED_REWARDS.items():
            granted = [
                op
                for op in walk_ops(
                    state_ops(self.catalog["quests"][quest_id]["states"][state_name])
                )
                if op["op"] in REWARD_OPS
            ]
            self.assertEqual(granted, expected, f"{quest_id}.{state_name} reward payload changed")
        lv2 = self.catalog["quests"]["main_quest_lv2"]["states"]
        advertised = next(
            op for op in lv2["gototeacher"]["triggers"][0]["ops"] if op["op"] == "say_reward"
        )
        self.assertIn("Experience points: 550", advertised["text"])
        self.assertIn("Yang: 1,000", advertised["text"])
        received = say_bodies(state_ops(lv2["gototeacher2"]))
        self.assertTrue(
            any("You have received 250 experience points." in body for body in received)
        )
        self.assertTrue(any("You have received 15,000 Yang." in body for body in received))
        lv3 = say_bodies(
            self.catalog["quests"]["main_quest_lv3"]["states"]["gotodefend"]["triggers"][0]["ops"]
        )
        self.assertTrue(any("You have received 850 experience points." in body for body in lv3))
        self.assertTrue(any("You have received 5,000 Yang." in body for body in lv3))
        notes = "\n".join(self.catalog["notes"])
        self.assertIn("overstate", notes)
        self.assertIn("operator-only", notes)
        security = SECURITY_NOTES.read_text().lower()
        for needle in ("quest", "give_exp", "say_reward"):
            self.assertIn(needle, security)

    def test_reward_items_are_installed_and_self_consistent(self) -> None:
        installed = {
            row["vnum"] for row in json.loads(ITEM_PROFILE.read_text())["item_catalog"]["items"]
        }
        referenced = set()
        for quest_id in self.catalog["order"]:
            for state in self.catalog["quests"][quest_id]["states"].values():
                for op in walk_ops(state_ops(state)):
                    if op["op"] in ITEM_OPS:
                        referenced.add(op["vnum"])
                    referenced.update(op.get("choices", []))
        self.assertTrue(referenced, "the opening line should reference items")
        self.assertLessEqual(referenced, installed, "quest references an uninstalled item")
        for quest_id in self.catalog["order"]:
            for state in self.catalog["quests"][quest_id]["states"].values():
                for op in walk_ops(state_ops(state)):
                    if op["op"] in {"give_item", "remove_item"}:
                        self.assertNotEqual(
                            op["vnum"], 69000, "the Bash Secret is display-only flavour text"
                        )

    def test_server_embeds_the_installed_catalog_by_default(self) -> None:
        match = re.search(
            r'MT2_QUEST_CATALOG"\)\s*\.unwrap_or_else\(\|_\| "([^"]+)"', SERVER_BUILD.read_text()
        )
        self.assertIsNotNone(match, "default quest catalog path is not discoverable")
        self.assertEqual(match.group(1).lstrip("./"), INSTALLED.relative_to(ROOT).as_posix())

    def test_localization_keys_resolve_or_fail_the_build(self) -> None:
        self.assertEqual(
            resolve_text("gameforge.main_quest_lv1._10_sendLetter", self.strings, "label").strip(),
            "Welcome to Metin2",
        )
        with self.assertRaises(ValueError):
            resolve_text("gameforge.newquest.does_not_exist", self.strings, "label")
        with self.assertRaises(ValueError):
            resolve_text("not-a-gameforge-key", self.strings, "label")
        for quest_id, quest in self.catalog["quests"].items():
            self.assertTrue(quest["title_key"].startswith("gameforge."))
            for field, value in [
                ("title", quest["title"]),
                *(
                    (field, value)
                    for state in quest["states"].values()
                    for field, value in self.state_texts(state)
                ),
            ]:
                self.assertNotIn("gameforge.", value, f"{quest_id} ships an unresolved {field}")

    def state_texts(self, state: dict):
        for op in walk_ops(state_ops(state)):
            for field in TEXT_FIELDS:
                value = op.get(field)
                if isinstance(value, str):
                    yield field, value
                elif isinstance(value, list):
                    for entry in value:
                        yield field, entry

    def test_compiler_rejects_content_that_would_break_runtime(self) -> None:
        states = {"a": {"enter": [], "triggers": []}}
        key = "gameforge.main_quest_lv1._10_sendLetter"
        for op, pattern in (
            ({"op": "give_exp", "amount": 0}, "amount"),
            ({"op": "give_item", "vnum": 27001, "count": 0}, "count"),
            ({"op": "objective", "label": key, "total": 0, "display": "remaining"}, "total"),
            ({"op": "objective", "label": key, "total": 5, "display": "progress"}, "display"),
            ({"op": "grant_admin"}, "unsupported"),
            ({"op": "set_state", "state": "missing"}, "undeclared"),
            ({"op": "give_exp", "amount": 1, "extra": 2}, "supported operation field"),
            (
                {"op": "say_reward_counter", "text": key, "source": "level"},
                "only supports 'objective'",
            ),
            ({"op": "say_item", "text": key, "vnum": 0}, "vnum"),
        ):
            with self.subTest(op=op), self.assertRaisesRegex(ValueError, pattern):
                compile_op(op, self.strings, "test", "main_quest_lv1", states)
        with self.assertRaisesRegex(ValueError, "mismatched option/branch"):
            compile_op(
                {
                    "op": "select",
                    "options": ["gameforge.main_quest_lv1._10_sendLetter"],
                    "branches": [[], []],
                },
                self.strings,
                "test",
                "main_quest_lv1",
                states,
            )
        for mutate, pattern in (
            (lambda profile: profile["quests"][0].__setitem__("id", "not an identifier"), ""),
            (lambda profile: profile["quests"][1].__setitem__("id", "main_quest_lv1"), "Duplicate"),
            (
                lambda profile: profile["quests"][0]["states"]["start"]["triggers"][0].__setitem__(
                    "operator_only", False
                ),
                "operator_only",
            ),
            (lambda profile: profile["source"].__setitem__("revision", "short"), "revision"),
            (lambda profile: profile.__setitem__("schema", "other"), "Unsupported quest profile"),
            (
                lambda profile: profile["quests"][0]["states"]["start"].__setitem__(
                    "enter", [{"op": "say", "title": "gameforge.main_quest_lv1._10_sendLetter"}]
                ),
                "missing required fields",
            ),
            (
                lambda profile: profile["quests"][0]["states"]["start"]["triggers"][0].update(
                    {"level_min": 5, "level_max": 0}
                ),
                "inverted",
            ),
            (
                lambda profile: profile["quests"][0]["states"]["start"]["triggers"][0].__setitem__(
                    "event", "logout"
                ),
                "unsupported event",
            ),
        ):
            bad = copy.deepcopy(self.profile)
            mutate(bad)
            with self.subTest(profile=pattern), self.assertRaisesRegex(ValueError, pattern):
                compile_catalog(bad, self.strings)


if __name__ == "__main__":
    unittest.main()
