#!/usr/bin/env python3
"""Compile the authored quest profiles into the catalog the game runs.

Quest behaviour is authored as data in ``content/profiles/classic-quests-*.json``.
Every player-facing string is referenced by its original ``gameforge.*``
localization key instead of being copied into the profile, so the compiled
catalog ships the exact wording the original client displayed and a typo in a key
fails the build instead of silently shipping blank text.

The compiler validates the profile strictly (closed field sets, resolvable state
and quest references, bounded numbers) and emits one deterministic catalog with a
content hash. The server embeds that hash in ``WorldInfo`` so a client running a
different quest catalog is rejected before it can talk to an NPC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "mt2spacetime.static-quests"
VERSION = 1
DEFAULT_SOURCE = ROOT / ".cache/full-game-research/server/source"
TRANSLATE = Path("gamefiles/data/translate_en.lua")
MAX_QUESTS = 4096
MAX_STATES = 256
MAX_TRIGGERS = 256
MAX_OPS = 64
MAX_TEXT = 4096

# Ops that a trigger may perform. ``count`` and ``select`` nest further op lists,
# so the recursion is expressed explicitly rather than through a generic walk.
NESTED_OPS = {"on_reached", "branches"}
EVENTS = {"login", "levelup", "kill", "npc_click", "npc_chat"}
CONDITIONS = (
    "level_min",
    "level_max",
    "npc_vnum",
    "vnum",
    "objective_min",
    "objective_max",
    "item_vnum",
    "item_min",
    "item_max",
    "operator_only",
)
TEXT_FIELDS = ("title", "body", "text", "label")
LOCALIZATION = re.compile(r"^gameforge\.[A-Za-z0-9_]+\.[A-Za-z0-9_.]+$")
TRANSLATE_LINE = re.compile(r'^\s*(gameforge\.[A-Za-z0-9_.]+)\s*=\s*"((?:[^"\\]|\\.)*)"')

# The closed operation vocabulary shared by the profile schema, the validator,
# the server op executor and the client presenter. ``server/src/quest.rs``
# implements exactly these kinds; ``tests/test_quest_catalog.py`` fails when the
# server executor and this table drift apart.
OP_FIELDS: dict[str, tuple[str, ...]] = {
    "letter": ("title",),
    "say": ("title", "body"),
    "target": ("npc_vnum", "label"),
    "wait": (),
    "select": ("options", "branches"),
    "clear_letter": (),
    "set_state": ("state",),
    "set_quest_state": ("quest", "state"),
    "objective": ("label", "total", "display"),
    "count": ("total", "on_reached"),
    "say_reward": ("text",),
    "say_reward_item": ("text", "vnum", "count"),
    "say_reward_value": ("text", "amount"),
    "say_reward_counter": ("text", "source"),
    "say_item": ("text", "vnum"),
    "give_exp": ("amount",),
    "give_money": ("amount",),
    "give_item": ("vnum", "count"),
    "remove_item": ("vnum", "count"),
    "random_item": ("choices", "count"),
}


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unescape(raw: str) -> str:
    """Decode the Lua string escapes the pinned translation file actually uses."""

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("x"):
            return chr(int(token[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r"}.get(token, token)

    return re.sub(r"\\(x[0-9A-Fa-f]{2}|.)", replace, raw)


def load_translations(path: Path) -> dict[str, str]:
    strings: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = TRANSLATE_LINE.match(line)
        if match:
            strings[match.group(1)] = _unescape(match.group(2))
    if not strings:
        raise ValueError(f"No localization strings parsed from {path}")
    return strings


def _object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} has missing or unsupported fields")
    return value


def _text(value: object, label: str, minimum: int = 0, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} must be text of {minimum}..{maximum} characters")
    if any(ord(character) < 32 and character != "\n" for character in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def _key(value: object, label: str) -> str:
    text = _text(value, label, 1, 160)
    if not LOCALIZATION.match(text):
        raise ValueError(f"{label} must be a gameforge localization key")
    return text


def resolve_text(value: str, strings: dict[str, str], label: str) -> str:
    key = _key(value, label)
    if key not in strings:
        raise ValueError(f"{label} references a missing localization key: {key}")
    return _unescape(strings[key])


def compile_catalog(profile: dict, strings: dict[str, str]) -> dict:
    """Validate one authored profile and return the compiled catalog."""

    profile = _object(
        profile, {"schema", "version", "map_id", "source", "notes", "quests"}, "quest profile"
    )
    if profile["schema"] != "mt2spacetime.quest-profile":
        raise ValueError(f"Unsupported quest profile schema: {profile['schema']}")
    _integer(profile["version"], "quest profile version", VERSION, VERSION)
    map_id = _text(profile["map_id"], "quest profile map_id", 1, 64)
    source = _object(
        profile["source"], {"repository", "revision", "quests"}, "quest profile source"
    )
    _text(source["repository"], "source repository", 1, 200)
    revision = _text(source["revision"], "source revision", 40, 40)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Source revision must be a full lowercase git sha")
    source_files = source["quests"]
    if not isinstance(source_files, list) or not 1 <= len(source_files) <= 256:
        raise ValueError("Source quest list must hold 1..256 paths")
    for path in source_files:
        _text(path, "source quest path", 1, 200)
    notes = profile["notes"]
    if not isinstance(notes, list) or len(notes) > 32:
        raise ValueError("Quest profile notes must be a list of at most 32 lines")
    for note in notes:
        _text(note, "quest profile note", 1, 400)

    quests = profile["quests"]
    if not isinstance(quests, list) or not 1 <= len(quests) <= MAX_QUESTS:
        raise ValueError(f"Quest profile must hold 1..{MAX_QUESTS} quests")

    compiled: dict[str, dict] = {}
    order: list[str] = []
    for raw_quest in quests:
        # `initial_state` stays optional: only a quest that another quest
        # unlocks needs to pin the state a joining character waits in.
        allowed = {"id", "title", "states"}
        if isinstance(raw_quest, dict) and "initial_state" in raw_quest:
            allowed.add("initial_state")
        quest = _object(raw_quest, allowed, "quest")
        quest_id = _text(quest["id"], "quest id", 1, 64)
        if not re.fullmatch(r"[A-Za-z0-9_]+", quest_id):
            raise ValueError(f"Quest id must be an identifier: {quest_id}")
        if quest_id in compiled:
            raise ValueError(f"Duplicate quest id: {quest_id}")
        title_key = _key(quest["title"], f"{quest_id} title")
        states = quest["states"]
        if not isinstance(states, dict) or not 1 <= len(states) <= MAX_STATES:
            raise ValueError(f"{quest_id} must declare 1..{MAX_STATES} states")
        # A quest unlocked by another one must not auto-fire, so a profile can
        # pin the state a joining character starts in. Without the override the
        # runtime keeps preferring ``run`` for backwards compatibility.
        initial = quest.get("initial_state")
        if initial is not None:
            initial = _text(initial, f"{quest_id} initial_state", 1, 64)
            if initial not in states:
                raise ValueError(f"{quest_id} starts in an undeclared state: {initial}")
        row: dict[str, dict] = {}
        for name, raw_state in states.items():
            if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                raise ValueError(f"Quest state must be an identifier: {quest_id}.{name}")
            state = _object(raw_state, {"enter", "triggers"}, f"quest state {quest_id}.{name}")
            row[name] = {
                "enter": compile_ops(
                    state["enter"], strings, f"{quest_id}.{name}.enter", quest_id, states
                ),
                "triggers": compile_triggers(
                    state["triggers"], f"{quest_id}.{name}", quest_id, states
                ),
            }
        compiled[quest_id] = {"title_key": title_key, "states": row, "initial_state": initial}
        order.append(quest_id)

    templates = {
        "schema": SCHEMA,
        "version": VERSION,
        "map_id": map_id,
        "order": order,
        "quests": {},
    }
    for quest_id in order:
        quest = compiled[quest_id]
        entry = {
            "title": resolve_text(quest["title_key"], strings, f"{quest_id} title"),
            "title_key": quest["title_key"],
            "states": {
                name: {
                    "enter": resolve_ops(state["enter"], strings, f"{quest_id}.{name}.enter"),
                    "triggers": [
                        resolve_trigger(trigger, strings, f"{quest_id}.{name} trigger")
                        for trigger in state["triggers"]
                    ],
                }
                for name, state in quest["states"].items()
            },
        }
        if quest["initial_state"] is not None:
            entry["initial_state"] = quest["initial_state"]
        templates["quests"][quest_id] = entry

    canonical = json.dumps(templates, sort_keys=True, separators=(",", ":")).encode()
    forward: set[str] = set()
    for quest in compiled.values():
        for state in quest["states"].values():
            for op in [*state["enter"], *(op for t in state["triggers"] for op in t["ops"])]:
                collect_forward(op, set(order), forward)
    catalog = {
        "schema": SCHEMA,
        "version": VERSION,
        "map_id": map_id,
        "content_hash": hashlib.sha256(canonical).hexdigest(),
        "source": {
            "repository": source["repository"],
            "revision": revision,
            "quests": source_files,
            "translate_sha256": "",
        },
        "notes": notes,
        "order": order,
        "forward_quest_refs": sorted(forward),
        "quests": templates["quests"],
    }
    return catalog


def collect_forward(op: dict, authored: set[str], forward: set[str]) -> None:
    """Record quest ids this catalog advances before they are themselves authored."""

    if op.get("op") == "set_quest_state" and op["quest"] not in authored:
        forward.add(op["quest"])
    for field in ("on_reached", "branches"):
        for nested in op.get(field, []):
            if field == "branches":
                for branch_op in nested:
                    collect_forward(branch_op, authored, forward)
            else:
                collect_forward(nested, authored, forward)


def compile_ops(
    ops: object, strings: dict[str, str], label: str, quest_id: str, states: dict
) -> list[dict]:
    if not isinstance(ops, list) or len(ops) > MAX_OPS:
        raise ValueError(f"{label} must be a list of at most {MAX_OPS} operations")
    return [
        compile_op(op, strings, f"{label}[{index}]", quest_id, states)
        for index, op in enumerate(ops)
    ]


def compile_op(
    op: object, strings: dict[str, str], label: str, quest_id: str, states: dict
) -> dict:
    if not isinstance(op, dict) or "op" not in op:
        raise ValueError(f"{label} must be an operation object")
    kind = op["op"]
    if not isinstance(kind, str):
        raise ValueError(f"{label}.op must be text")
    compiled: dict = {"op": kind}
    for field in op:
        if field == "op":
            continue
        value = op[field]
        if field in TEXT_FIELDS:
            compiled[field] = _key(value, f"{label}.{field}")
        elif field == "state":
            name = _text(value, f"{label}.state", 1, 64)
            # ``set_quest_state`` resolves the target state against another quest
            # at runtime; only a local transition must exist in this quest.
            if kind != "set_quest_state" and name not in states:
                raise ValueError(f"{label} transitions to an undeclared state: {name}")
            compiled[field] = name
        elif field == "quest":
            compiled[field] = _text(value, f"{label}.quest", 1, 64)
        elif field == "display":
            if value != "remaining":
                raise ValueError(f"{label}.display only supports 'remaining'")
            compiled[field] = value
        elif field in NESTED_OPS:
            if field == "on_reached":
                compiled[field] = compile_ops(value, strings, f"{label}.{field}", quest_id, states)
            else:
                if not isinstance(value, list) or not 1 <= len(value) <= 8:
                    raise ValueError(f"{label}.branches must hold 1..8 option branches")
                compiled[field] = [
                    compile_ops(branch, strings, f"{label}.branches[{index}]", quest_id, states)
                    for index, branch in enumerate(value)
                ]
        elif field == "options":
            if not isinstance(value, list) or not 1 <= len(value) <= 8:
                raise ValueError(f"{label}.options must hold 1..8 entries")
            compiled[field] = [
                _key(entry, f"{label}.options[{index}]") for index, entry in enumerate(value)
            ]
        elif field == "choices":
            if not isinstance(value, list) or not 1 <= len(value) <= 32:
                raise ValueError(f"{label}.choices must hold 1..32 vnums")
            compiled[field] = [
                _integer(entry, f"{label}.choices[{index}]", 1, 2**32 - 1)
                for index, entry in enumerate(value)
            ]
        elif field == "source":
            if value != "objective":
                raise ValueError(f"{label}.source only supports 'objective'")
            compiled[field] = value
        elif field in {"vnum", "npc_vnum", "count", "amount", "total", "min", "max"}:
            compiled[field] = _integer(value, f"{label}.{field}", 0, 2**31 - 1)
        else:
            raise ValueError(f"{label}.{field} is not a supported operation field")
    validate_op(compiled, label)
    return compiled


def validate_op(op: dict, label: str) -> None:
    kind = op["op"]
    required = OP_FIELDS
    if kind not in required:
        raise ValueError(f"{label} uses an unsupported operation: {kind}")
    if kind == "select" and "branches" not in op:
        op["branches"] = []
    fields = required[kind]
    extra = set(op) - {"op"} - set(fields)
    if extra:
        raise ValueError(f"{label} has unsupported fields for {kind}: {sorted(extra)}")
    missing = [field for field in fields if field not in op]
    if missing:
        raise ValueError(f"{label} is missing required fields for {kind}: {missing}")
    if kind in {"count", "objective"}:
        _integer(op["total"], f"{label}.total", 1, 100_000)
    if kind in {"give_item", "remove_item", "say_reward_item", "say_item"}:
        _integer(op["vnum"], f"{label}.vnum", 1, 2**32 - 1)
    if kind in {"give_exp", "give_money", "say_reward_value"}:
        _integer(op["amount"], f"{label}.amount", 1, 2**31 - 1)
    if kind in {"give_item", "remove_item", "say_reward_item"}:
        _integer(op["count"], f"{label}.count", 1, 65535)
    if kind == "random_item":
        _integer(op["count"], f"{label}.count", 1, 65535)
    if kind == "select" and len(op["options"]) != len(op["branches"]):
        raise ValueError(f"{label} has a mismatched option/branch count")
    if kind == "say_reward_counter" and op["source"] != "objective":
        raise ValueError(f"{label} cannot read counter source {op['source']}")


def compile_triggers(triggers: object, label: str, quest_id: str, states: dict) -> list[dict]:
    if not isinstance(triggers, list) or len(triggers) > MAX_TRIGGERS:
        raise ValueError(f"{label}.triggers must hold at most {MAX_TRIGGERS} entries")
    compiled = []
    for index, raw in enumerate(triggers):
        if not isinstance(raw, dict):
            raise ValueError(f"{label}.triggers[{index}] must be an object")
        event = raw.get("event")
        if event not in EVENTS:
            raise ValueError(f"{label}.triggers[{index}] has an unsupported event: {event}")
        unknown = set(raw) - {"event", "ops"} - set(CONDITIONS)
        if unknown:
            raise ValueError(
                f"{label}.triggers[{index}] has unsupported conditions: {sorted(unknown)}"
            )
        row = {"event": event}
        for name in CONDITIONS:
            if name not in raw:
                continue
            value = raw[name]
            if name == "operator_only":
                if value is not True:
                    raise ValueError(f"{label}.triggers[{index}].operator_only must be true")
                row[name] = True
            else:
                row[name] = _integer(value, f"{label}.triggers[{index}].{name}", 0, 2**31 - 1)
        for minimum, maximum, name in (
            ("level_min", "level_max", "level"),
            ("objective_min", "objective_max", "objective"),
            ("item_min", "item_max", "item"),
        ):
            if minimum in row and maximum in row and row[minimum] > row[maximum]:
                raise ValueError(f"{label}.triggers[{index}] has an inverted {name} range")
        if "ops" not in raw:
            raise ValueError(f"{label}.triggers[{index}] must declare ops")
        row["ops"] = compile_ops(raw["ops"], {}, f"{label}.triggers[{index}].ops", quest_id, states)
        compiled.append(row)
    return compiled


def resolve_ops(ops: list[dict], strings: dict[str, str], label: str) -> list[dict]:
    resolved = []
    for index, op in enumerate(ops):
        row: dict = {}
        for field, value in op.items():
            if field in TEXT_FIELDS or field == "options":
                if field == "options":
                    row[field] = [
                        resolve_text(entry, strings, f"{label}[{index}].options") for entry in value
                    ]
                else:
                    row[field] = resolve_text(value, strings, f"{label}[{index}].{field}")
            elif field in NESTED_OPS:
                if field == "on_reached":
                    row[field] = resolve_ops(value, strings, f"{label}[{index}].{field}")
                else:
                    row[field] = [
                        resolve_ops(branch, strings, f"{label}[{index}].branches")
                        for branch in value
                    ]
            else:
                row[field] = value
        resolved.append(row)
    return resolved


def resolve_trigger(trigger: dict, strings: dict[str, str], label: str) -> dict:
    return {**trigger, "ops": resolve_ops(trigger["ops"], strings, label)}


def build(profile_path: Path, source: Path, map_hash: str) -> dict:
    strings = load_translations(source / TRANSLATE)
    profile = json.loads(profile_path.read_text())
    catalog = compile_catalog(profile, strings)
    catalog["source"]["translate_sha256"] = sha256_path(source / TRANSLATE)
    quest_hashes = {}
    for relative in catalog["source"]["quests"]:
        path = source / relative
        if not path.is_file():
            raise ValueError(f"Pinned quest source is missing: {relative}")
        quest_hashes[relative] = sha256_path(path)
    catalog["source"]["quest_sha256"] = quest_hashes
    catalog["map_hash"] = map_hash
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True, help="authored quest profile")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="pinned server source")
    parser.add_argument(
        "--map-hash",
        help="compiled map content hash; defaults to server/content/yongan.sha256",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--install", action="store_true", help="copy the catalog to client/assets/imported/quests"
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    map_hash = args.map_hash
    if not map_hash:
        map_hash = (ROOT / "server/content/yongan.sha256").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", map_hash):
        raise SystemExit("Map hash must be a 64 character lowercase sha256")
    catalog = build(args.profile, args.source, map_hash)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n")
    if args.install:
        target = ROOT / "client/assets/imported/quests/catalog.v1.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n")
    if not args.quiet:
        print(
            f"{len(catalog['order'])} quests, {len(catalog['quests'])} compiled, "
            f"hash {catalog['content_hash'][:12]} -> {args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
