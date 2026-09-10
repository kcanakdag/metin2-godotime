#!/usr/bin/env python3
"""Read the pinned original quest corpus without executing any Lua.

The original server ships 284 ``.quest`` scripts authored in a Lua-like DSL. This
tool builds a read-only inventory of that corpus (quest ids, states, ``when``
triggers and the item/experience/money operations each trigger performs) so the
rewrite can track which quests are implemented, compiled and qualified instead of
guessing from memory.

Nothing here interprets the scripts. Only structure that is declared with the
DSL's own keywords is extracted; every operation is recorded verbatim so a human
can review the mapping before it is authored into a compiled quest definition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / ".cache/full-game-research/server/source"
CORPUS = Path("gamefiles/data/quest")
TRANSLATE = Path("gamefiles/data/translate_en.lua")
SCHEMA = "mt2spacetime.quest-corpus"
VERSION = 1

QUEST_HEADER = re.compile(
    r"^\s*quest\s+([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_.]+))?\s+begin\b", re.MULTILINE
)
STATE_HEADER = re.compile(r"^\s*state\s+([A-Za-z0-9_]+)\s+begin\b")
WHEN_HEADER = re.compile(r"^\s*when\s+(.*?)\s+begin\b", re.MULTILINE)

OPERATIONS = (
    ("experience", re.compile(r"pc\.give_exp2?\s*\(\s*(-?\d+)")),
    ("yang", re.compile(r"pc\.change_?money\s*\(\s*(-?\d+)")),
    ("item", re.compile(r"pc\.give_item2?\s*\(\s*\"?(\d+)\"?\s*,\s*(\d+)")),
    ("remove_item", re.compile(r"pc\.removeitem\s*\(\s*\"?(\d+)\"?\s*,\s*(\d+)")),
    (
        "quest_state",
        re.compile(r"set_quest_state\s*\(\s*\"([A-Za-z0-9_]+)\"\s*,\s*\"([A-Za-z0-9_]+)\""),
    ),
    ("state", re.compile(r"\bset_state\s*\(\s*([A-Za-z0-9_]+)\s*\)")),
    ("letter", re.compile(r"\bsend_letter\s*\(")),
    (
        "counter",
        re.compile(r"\bq\.set_counter\s*\(\s*(?:gameforge\.)?([A-Za-z0-9_.]+)\s*,\s*([^)]*)\)"),
    ),
    ("npc_chat", re.compile(r"(\d+)\.chat\.([A-Za-z0-9_.]+)")),
)

TRANSLATE_LINE = re.compile(
    r"^gameforge\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*=\s*\"((?:[^\"\\]|\\.)*)\""
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_translations(path: Path) -> dict[str, str]:
    """Return ``{group.key: raw text}`` from the pinned English translation file."""
    strings: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = TRANSLATE_LINE.match(line)
        if match:
            strings[f"{match.group(1)}.{match.group(2)}"] = match.group(3)
    if not strings:
        raise ValueError(f"No translations parsed from {path}")
    return strings


def referenced_keys(text: str) -> list[str]:
    keys = re.findall(r"gameforge\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)", text)
    return sorted({f"{group}.{key}" for group, key in keys})


def operations_of(body: str) -> list[dict]:
    found: list[dict] = []
    for kind, pattern in OPERATIONS:
        for match in pattern.finditer(body):
            groups = [value for value in match.groups() if value is not None]
            found.append(
                {"kind": kind, "values": groups, "line": body.count("\n", 0, match.start())}
            )
    found.sort(key=lambda entry: entry["line"])
    return found


def parse_states(text: str) -> list[dict]:
    """Split a quest body into ``state`` blocks at their own indentation level."""
    lines = text.splitlines()
    states: list[dict] = []
    index = 0
    while index < len(lines):
        match = STATE_HEADER.match(lines[index])
        if not match:
            index += 1
            continue
        state_id = match.group(1)
        index += 1
        body: list[str] = []
        while index < len(lines) and not STATE_HEADER.match(lines[index]):
            if lines[index].strip() == "end" and index + 1 < len(lines):
                # A state terminator is followed by another state or the quest end.
                following = lines[index + 1].strip()
                if following.startswith("state ") or following == "end":
                    index += 1
                    break
            body.append(lines[index])
            index += 1
        states.append({"id": state_id, "body": "\n".join(body)})
    return states


def parse_quest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    header = QUEST_HEADER.search(text)
    if not header:
        raise ValueError(f"{path} has no quest header")
    states = []
    for state in parse_states(text):
        triggers = []
        for match in WHEN_HEADER.finditer(state["body"]):
            start = match.end()
            depth = 1
            index = start
            while index < len(state["body"]) and depth > 0:
                token = re.match(r"\s*(begin|end)\b", state["body"][index:])
                if token:
                    depth += 1 if token.group(1) == "begin" else -1
                    index += token.end()
                    continue
                index += 1
            body = state["body"][start : index if depth == 0 else len(state["body"])]
            triggers.append(
                {
                    "condition": match.group(1).strip(),
                    "keys": referenced_keys(body),
                    "operations": operations_of(body),
                }
            )
        states.append(
            {
                "id": state["id"],
                "triggers": triggers,
                "keys": referenced_keys(state["body"]),
            }
        )
    return {
        "id": header.group(1),
        "disabled": path.name.startswith("xxx_"),
        "path": str(path.relative_to(path.parents[3])),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
        "states": states,
    }


def build_inventory(root: Path) -> dict:
    quest_dir = root / CORPUS
    translate = root / TRANSLATE
    files = sorted(quest_dir.glob("*.quest"))
    if not files:
        raise ValueError(f"No quest scripts under {quest_dir}")
    quests = [parse_quest(path) for path in files]
    ids = [quest["id"] for quest in quests]
    duplicated = sorted({value for value in ids if ids.count(value) > 1})
    strings = load_translations(translate)
    missing = sorted({key for quest in quests for key in quest_keys(quest) if key not in strings})
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "source": {
            "quest_root": str(CORPUS),
            "translate": {
                "path": str(TRANSLATE),
                "sha256": sha256_path(translate),
                "strings": len(strings),
            },
        },
        "summary": {
            "quests": len(quests),
            "unique_quests": len(set(ids)),
            "duplicate_ids": duplicated,
            "disabled_files": [quest["path"] for quest in quests if quest["disabled"]],
            "states": sum(len(quest["states"]) for quest in quests),
            "triggers": sum(
                len(state["triggers"]) for quest in quests for state in quest["states"]
            ),
            "missing_translations": missing,
        },
        "quests": quests,
    }


def quest_keys(quest: dict) -> set[str]:
    return {key for state in quest["states"] for key in state["keys"]}


def load_catalog_quest_ids(catalog: dict) -> list[str]:
    """Return the quest ids a compiled catalog implements, in authored order."""

    if catalog.get("schema") == "mt2spacetime.static-quests":
        order = catalog.get("order")
        quests = catalog.get("quests")
        if not isinstance(order, list) or not isinstance(quests, dict):
            raise ValueError("Compiled quest catalog is malformed")
        if sorted(order) != sorted(quests):
            raise ValueError("Compiled quest catalog order does not match its quests")
        return list(order)
    return [quest["id"] for quest in catalog["quests"]]


def coverage(inventory: dict, catalog: dict) -> dict:
    corpus_ids = {quest["id"] for quest in inventory["quests"]}
    catalog_ids = load_catalog_quest_ids(catalog)
    unknown = sorted(set(catalog_ids) - corpus_ids)
    if unknown:
        raise ValueError(f"Compiled quests are absent from the source corpus: {unknown}")
    implemented = sorted(set(catalog_ids))
    return {
        "schema": "mt2spacetime.quest-coverage",
        "version": 1,
        "source": inventory["source"],
        "corpus_quests": len(corpus_ids),
        "implemented_quests": len(implemented),
        "implemented": implemented,
        "remaining_quests": len(corpus_ids) - len(implemented),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_SOURCE)
    sub = parser.add_subparsers(dest="command", required=True)
    inventory_parser = sub.add_parser("inventory", help="write the read-only corpus inventory")
    inventory_parser.add_argument("--output", type=Path, required=True)
    coverage_parser = sub.add_parser("coverage", help="compare a compiled catalog to the corpus")
    coverage_parser.add_argument("--catalog", type=Path, required=True)
    coverage_parser.add_argument("--output", type=Path, required=True)
    inventory_parser.add_argument("--quiet", action="store_true")
    coverage_parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    inventory = build_inventory(args.root)
    if args.command == "inventory":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(inventory, indent=1, sort_keys=True) + "\n")
        if not args.quiet:
            summary = inventory["summary"]
            print(
                f"{summary['quests']} quests, {summary['states']} states, "
                f"{summary['triggers']} triggers -> {args.output}"
            )
        return 0

    catalog = json.loads(args.catalog.read_text())
    report = coverage(inventory, catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    if not args.quiet:
        print(
            f"{report['implemented_quests']}/{report['corpus_quests']} quests compiled "
            f"-> {args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
