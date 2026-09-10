#!/usr/bin/env python3
"""Compile the authored NPC dialogue profile into the interaction profile.

Clickable NPC dialogue is authored as data in
``content/profiles/yongan-npc-dialogue.json``. A row either carries literal
authored text or references the original quest corpus by
``source: {quest, line, head}`` plus a ``gameforge.*`` localization key. The
compiler resolves that key from the pinned ``translate_en.lua`` and verifies the
key is actually used inside the referenced ``when`` handler, so a fabricated or
stale attribution fails the build instead of silently shipping invented text.

The emitted ``content/worlds/yongan.interactions.json`` is consumed by
``server/build_npcs.rs``, which requires every map placement *and* every area
NPC to resolve exactly one interaction row. A new NPC therefore only needs a
profile row; the compiler fails when either is left without dialogue.

Original wandering townsfolk have no fixed coordinate in the client's
``npclist``, so the catalog describes them as an area whose point the server
samples. They are keyed by the same ``spawn.<map>.<name>-<vnum>-<n>`` id the
runtime publishes in its ``npc_spawn`` row, so one profile row covers both the
board text and the sampled placement.

``--discover ALIAS`` prints the chat handlers the corpus knows for an NPC vnum
or legend alias and the localization keys their first lines use, which is how a
new row's ``source`` block is produced.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from build_quest_catalog import TRANSLATE, load_translations, sha256_path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / ".cache/full-game-research/server/source"
SCHEMA = "mt2spacetime.npc-dialogue-profile"
VERSION = 1
MAX_BODY = 1024
MAX_TITLE = 160
MAX_ROWS = 4096
KEY = re.compile(r"^gameforge\.[A-Za-z0-9_]+\.[A-Za-z0-9_.]+$")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Statement keywords that open a block. ``when``/``state``/``quest`` open with
# ``begin``, ``if`` with ``then``, ``for``/``while`` with ``do``; ``repeat`` and
# a named ``function`` definition open unconditionally and close with ``until``
# and ``end``. Counting ``begin``/``end`` alone is not enough: an inner ``if``
# would otherwise close the enclosing handler at its first ``end``.
BLOCK_KEYWORDS = frozenset({"when", "state", "quest", "if", "for", "while"})
CLOSERS = frozenset({"end", "until"})
# Ops whose first argument is a player-facing string. ``say_title`` renders in
# the board's title bar, the rest render as body lines.
SAY_OPS = ("say", "say_reward", "say_item", "say_reward_item", "say_reward_value")
CALL = re.compile(r"\b(say_title|" + "|".join(SAY_OPS) + r")\s*\(\s*([^)]*)\)")


def _object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} has missing or unsupported fields")
    return value


def _text(value: object, label: str, minimum: int = 0, maximum: int = MAX_BODY) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} must be text of {minimum}..{maximum} characters")
    if any(ord(character) < 32 and character != "\n" for character in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _strip_block_comments(text: str) -> str:
    """Blank out Lua-style ``--[[ ... ]]`` block comments, keeping line breaks.

    ``event_mob_invasion.quest`` documents its regen files in a block comment
    whose prose contains the word ``when``; without this the comment reads as a
    handler and steals the following ``begin`` from the real one.
    """

    out = list(text)
    index = 0
    while index < len(text):
        if text.startswith("--[[", index):
            end = text.find("]]", index + 4)
            stop = len(text) if end == -1 else end + 2
            for position in range(index, stop):
                if out[position] != "\n":
                    out[position] = " "
            index = stop
            continue
        index += 1
    return "".join(out)


def _mask(line: str) -> str:
    """Blank out string literals and ``--`` comments while keeping offsets.

    The corpus names keywords inside both (``notice("... begin ...")``, commented
    out ``when`` blocks), so a raw token scan would miscount block nesting.
    """

    out = list(line)
    in_string = False
    index = 0
    while index < len(line):
        character = line[index]
        if in_string:
            out[index] = " "
            if character == "\\":
                if index + 1 < len(line):
                    out[index + 1] = " "
                index += 2
                continue
            if character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == "-" and line.startswith("--", index):
            for rest in range(index, len(line)):
                out[rest] = " "
            break
        index += 1
    return "".join(out)


def _slice(lines: list[str], start: tuple[int, int], end: tuple[int, int]) -> str:
    """Return the source text between two ``(line, column)`` positions."""

    first, column = start
    last, stop = end
    if first == last:
        return lines[first][column:stop]
    parts = [lines[first][column:]]
    parts.extend(lines[first + 1 : last])
    parts.append(lines[last][:stop])
    return "\n".join(parts)


def parse_handlers(path: Path) -> list[dict]:
    """Return every ``when ... begin`` handler in one quest file.

    Every block of the quest language ends with the same ``end`` token (``if``
    with ``then``, ``for``/``while`` with ``do``, ``repeat`` with ``until``), so
    the handler extent comes from statement-aware nesting depth rather than from
    counting ``begin``/``end`` or from indentation: the shipped corpus contains
    both nested ``if`` blocks and handlers whose closing ``end`` is indented
    deeper than its ``when``. Conditions may continue over several lines and may
    carry a trailing ``--`` comment after ``begin``.
    """

    lines = _strip_block_comments(path.read_text(encoding="latin-1", errors="replace")).splitlines()
    masked = [_mask(line) for line in lines]
    handlers: list[dict] = []
    depth = 0
    pending: str | None = None
    pending_when: tuple[int, int] | None = None
    handler: dict | None = None
    line_index = 0
    column = 0
    while line_index < len(lines):
        match = WORD.search(masked[line_index], column)
        if match is None:
            line_index += 1
            column = 0
            continue
        word = match.group(0).lower()
        after = match.end()
        if word in CLOSERS:
            depth -= 1
            if handler is not None and depth < handler["depth"]:
                handler["body"] = _slice(lines, handler["body_start"], (line_index, match.start()))
                handlers.append(handler)
                handler = None
            pending = None
        elif word == "begin":
            depth += 1
            if pending_when is not None and handler is None:
                handler = {
                    "quest": path,
                    "line": pending_when[0] + 1,
                    "condition": " ".join(
                        _slice(lines, pending_when, (line_index, match.start())).split()
                    ),
                    "body_start": (line_index, after),
                    "depth": depth,
                }
                pending_when = None
            elif pending_when is not None:
                pending_when = None
            pending = None
        elif word == "then":
            if pending == "if":
                depth += 1
            pending = None
        elif word == "do":
            if pending in ("for", "while"):
                depth += 1
            pending = None
        elif word == "function":
            following = WORD.search(masked[line_index], after)
            depth += 1 if following is not None else 0
            pending = None
        elif word == "repeat":
            depth += 1
            pending = None
        elif word == "when":
            if handler is None:
                # The condition excludes the ``when`` keyword itself.
                pending_when = (line_index, after)
            pending = "when"
        elif word in BLOCK_KEYWORDS:
            pending = word
        elif word == "elseif":
            # ``elseif ... then`` continues the open ``if``; its ``then`` must
            # not count as a second opener.
            pending = "elseif"
        # Any other token is part of the current statement, so ``pending`` has
        # to survive until the opener (``begin``/``then``/``do``) appears.
        column = after
    if pending_when is not None:
        raise ValueError(f"Unterminated when condition in {path}:{pending_when[0] + 1}")
    if handler is not None:
        raise ValueError(f"Unterminated when handler in {path}:{handler['line']}")
    for entry in handlers:
        joined = entry.pop("body")
        entry.pop("body_start")
        entry.pop("depth")
        calls = [(kind, argument.strip()) for kind, argument in CALL.findall(joined)]
        entry["head"] = entry["condition"].split()[0] if entry["condition"].split() else ""
        entry["body"] = joined
        entry["title"] = next((key for kind, key in calls if kind == "say_title"), None)
        entry["lines"] = [key for kind, key in calls if kind != "say_title"]
    return handlers


def chat_handlers(handlers: list[dict], alias: str) -> list[dict]:
    # Handlers may chain aliases (``when __TARGET__.target.click or
    # 20357.chat....``), so the alias has to be matched anywhere in the
    # condition rather than only at its start.
    pattern = re.compile(rf"(?:^|[\s(,]){re.escape(alias)}\.(chat|click)\b", re.IGNORECASE)
    return [handler for handler in handlers if pattern.search(handler["condition"])]


def _normalize(text: str, label: str) -> str:
    """Render original ``[ENTER]`` lines and trim the shipped body text."""

    rendered = text.replace("[ENTER]", "\n")
    rendered = "\n".join(part.rstrip() for part in rendered.splitlines())
    while "\n\n\n" in rendered:
        rendered = rendered.replace("\n\n\n", "\n\n")
    rendered = rendered.strip()
    if not rendered:
        raise ValueError(f"{label} resolved to empty text")
    _text(rendered, label)
    return rendered


def _preceding_title(body: str, key: str) -> str | None:
    """Return the ``say_title`` in force when ``key`` is reached.

    Handlers branch. ``skill_group.quest`` titles the wrong-class branch and
    returns before the class-specific line, so the *first* title of a handler is
    not necessarily the one shown next to the referenced line. The original
    executes top to bottom, so the last title before the line is the one that
    was displayed.

    Only literal localization keys count. ``alchemist`` builds its title as
    ``say_title(mob_name("alchemist"))``, which the call scanner sees as the
    partial argument ``mob_name(``...; such titles resolve to the NPC name on
    the server, so the last call decides: a literal key is carried into the
    profile, a dynamic one falls back to ``None`` and the board shows the NPC
    name, exactly as the original did.
    """

    index = body.find(key)
    titles = [
        match.group(2).strip()
        for match in CALL.finditer(body[:index])
        if match.group(1) == "say_title"
    ]
    if not titles:
        return None
    return titles[-1] if KEY.fullmatch(titles[-1]) else None


def _discover(alias: str, source: Path, translate: Path) -> int:
    strings = load_translations(translate)
    quest_dir = source / TRANSLATE.parent / "quest"
    found = 0
    unreadable = []
    for path in sorted(quest_dir.glob("*.quest")):
        try:
            handlers = parse_handlers(path)
        except ValueError as error:
            # The pinned revision ships one truncated quest file; discovery has
            # to report it and keep scanning the rest of the corpus.
            unreadable.append(str(error))
            continue
        for handler in chat_handlers(handlers, alias):
            found += 1
            print(f"{path.relative_to(source)}:{handler['line']}  {handler['condition']}")
            for kind, key in (("title", handler["title"]),) + tuple(
                ("line", key) for key in handler["lines"][:3]
            ):
                if key is None:
                    continue
                resolved = strings.get(key)
                shown = "<missing key>" if resolved is None else resolved.replace("[ENTER]", " / ")
                print(f"   {kind}: {key}\n         {shown[:220]}")
    for message in unreadable:
        print(f"warning: skipped unparsable quest file: {message}", file=sys.stderr)
    if not found:
        print(f"No chat handler found for alias {alias!r}", file=sys.stderr)
        return 1
    return 0


def compile_profile(profile_path: Path, source: Path) -> tuple[dict, dict]:
    strings = load_translations(source / TRANSLATE)
    profile = json.loads(profile_path.read_text())
    if not isinstance(profile, dict) or profile.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported NPC dialogue profile schema: {profile.get('schema')!r}")
    if profile.get("version") != VERSION:
        raise ValueError("Unsupported NPC dialogue profile version")
    body = _object(
        profile,
        {"schema", "version", "map_id", "source", "notes", "npcs"},
        "npc dialogue profile",
    )
    map_id = _text(body["map_id"], "npc dialogue profile map_id", 1, 64)
    origin = _object(body["source"], {"repository", "revision", "quests"}, "npc dialogue source")
    _text(origin["repository"], "npc dialogue repository", 1, 200)
    _text(origin["revision"], "npc dialogue revision", 1, 64)
    quests = origin["quests"]
    if not isinstance(quests, list) or not 1 <= len(quests) <= 64:
        raise ValueError("NPC dialogue source must list 1..64 quest paths")
    for path in quests:
        _text(path, "npc dialogue source quest", 1, 200)
    if not isinstance(body["notes"], list) or not all(
        isinstance(note, str) for note in body["notes"]
    ):
        raise ValueError("NPC dialogue notes must be a list of strings")
    rows = body["npcs"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"NPC dialogue profile must hold 1..{MAX_ROWS} rows")

    handlers: dict[Path, list[dict]] = {}
    interactions = []
    seen = set()
    for index, raw in enumerate(rows):
        label = f"npcs[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be an object")
        fields = set(raw)
        title = None
        title_key = None
        if fields == {"spawn_id", "text"}:
            text = _normalize(raw["text"], f"{label}.text")
            provenance = None
        elif fields == {"spawn_id", "source", "text"}:
            reference = _object(raw["source"], {"quest", "line", "head"}, f"{label}.source")
            relative = _text(reference["quest"], f"{label}.source.quest", 1, 200)
            if relative not in quests:
                raise ValueError(f"{label}.source.quest is not declared in the profile source")
            line = reference["line"]
            if not isinstance(line, int) or isinstance(line, bool) or line < 1:
                raise ValueError(f"{label}.source.line must be a positive integer")
            key = _text(raw["text"], f"{label}.text", 1, 200)
            if not KEY.fullmatch(key):
                raise ValueError(f"{label}.text must be a gameforge localization key")
            resolved = strings.get(key)
            if resolved is None:
                raise ValueError(f"{label}.text is missing from the pinned translations: {key}")
            path = source / relative
            if not path.is_file():
                raise ValueError(f"Pinned quest source is missing: {relative}")
            if path not in handlers:
                handlers[path] = parse_handlers(path)
            matches = [
                handler
                for handler in handlers[path]
                if handler["line"] == line and handler["head"] == reference["head"]
            ]
            if len(matches) != 1:
                raise ValueError(f"{label}.source does not name one handler at {relative}:{line}")
            if key not in matches[0]["body"]:
                raise ValueError(f"{label}.text is not used by the referenced handler")
            text = _normalize(resolved, f"{label}.text")
            title_key = _preceding_title(matches[0]["body"], key)
            if title_key is not None:
                resolved_title = strings.get(title_key)
                if resolved_title is None:
                    raise ValueError(
                        f"{label} names a title missing from the pinned translations: {title_key}"
                    )
                title = _normalize(resolved_title, f"{label} title")
                if "\n" in title or len(title) > MAX_TITLE:
                    raise ValueError(f"{label} title does not fit the dialogue board")
            provenance = (relative, line, reference["head"], key)
        else:
            raise ValueError(f"{label} has missing or unsupported fields")
        spawn_id = _text(raw["spawn_id"], f"{label}.spawn_id", 1, 128)
        if not spawn_id.startswith("spawn.") or spawn_id in seen:
            raise ValueError(f"{label}.spawn_id is invalid or duplicated")
        seen.add(spawn_id)
        interactions.append(
            {
                "spawn_id": spawn_id,
                "kind": "dialogue",
                "body": text,
                "title": title,
                "_source": provenance,
                "_title": title_key,
            }
        )

    catalog_path = ROOT / "client/assets/imported/npcs/catalog.v1.json"
    if not catalog_path.is_file():
        raise ValueError("Run make npc-install before compiling NPC dialogue")
    catalog = json.loads(catalog_path.read_text())
    if catalog.get("schema") != "mt2spacetime.static-npcs":
        raise ValueError("Unsupported static NPC catalog")
    worlds = [world for world in catalog["maps"] if world["id"] == map_id]
    if len(worlds) != 1:
        raise ValueError(f"NPC catalog has no unique map {map_id!r}")
    placements = {placement["id"] for placement in worlds[0]["placements"]}
    areas = {area["id"] for area in worlds[0].get("areas", [])}
    if placements & areas:
        raise ValueError("NPC catalog reuses a spawn id for a placement and an area")
    known = placements | areas
    missing = sorted(known - seen)
    unknown = sorted(seen - known)
    if unknown:
        raise ValueError(f"Dialogue rows have no placement or area in {map_id}: {unknown[:4]}")
    if missing:
        raise ValueError(f"Places or areas without dialogue in {map_id}: {missing[:4]}")

    interactions.sort(key=lambda row: row["spawn_id"])
    emitted = []
    for row in interactions:
        entry = {"spawn_id": row["spawn_id"], "kind": row["kind"], "body": row["body"]}
        if row["title"] is not None:
            entry["title"] = row["title"]
        emitted.append(entry)
    document = {
        "schema_version": 1,
        "map_id": map_id,
        "interactions": emitted,
    }
    receipt = {
        "rows": len(interactions),
        "sourced": sum(1 for row in interactions if row["_source"]),
        "authored": sum(1 for row in interactions if not row["_source"]),
        "titled": sum(1 for row in interactions if row["title"] is not None),
        "catalog_sha256": sha256_path(catalog_path),
        "translate_sha256": sha256_path(source / TRANSLATE),
        "quest_sha256": {relative: sha256_path(source / relative) for relative in sorted(quests)},
        "sources": [
            {
                "spawn_id": row["spawn_id"],
                "quest": row["_source"][0],
                "line": row["_source"][1],
                "head": row["_source"][2],
                "key": row["_source"][3],
                "title_key": row["_title"],
            }
            for row in interactions
            if row["_source"]
        ],
    }
    return document, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "content/profiles/yongan-npc-dialogue.json",
        help="authored NPC dialogue profile",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="pinned server source")
    parser.add_argument("--output", type=Path, help="interaction profile to write")
    parser.add_argument("--receipt", type=Path, help="optional JSON receipt of resolved sources")
    parser.add_argument(
        "--install",
        action="store_true",
        help="write content/worlds/yongan.interactions.json",
    )
    parser.add_argument("--discover", help="print corpus chat handlers for an NPC vnum or alias")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.discover:
        return _discover(args.discover, args.source, args.source / TRANSLATE)
    document, receipt = compile_profile(args.profile, args.source)
    encoded = json.dumps(document, indent=1, sort_keys=True) + "\n"
    outputs = []
    if args.output:
        outputs.append(args.output)
    if args.install:
        outputs.append(ROOT / "content/worlds/yongan.interactions.json")
    if not outputs:
        raise SystemExit("Pass --output or --install")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    if not args.quiet:
        print(
            f"{receipt['rows']} NPC dialogues "
            f"({receipt['sourced']} corpus-sourced, {receipt['authored']} authored) -> "
            + ", ".join(str(path) for path in outputs)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
