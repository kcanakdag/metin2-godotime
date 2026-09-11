#!/usr/bin/env python3
"""Expand the installed item registry to every prototype a drop row can reach.

The drop corpus references far more vnums than the hand-written registry
carries. Loot only resolves against installed prototypes, so a drop row whose
vnum is missing is not "no drop", it is a failed grant. This tool derives the
selection that closes that gap from the pinned corpus instead of guessing:

* the candidate vnums are the ones a *compiled* drop table can actually hand
  out - reachable common rows plus the group rows of mobs the selected mob
  catalog can spawn, matching ``tools/build_drop_catalog.py``'s filters;
* each candidate is compiled through ``tools/item_definitions.py`` and kept
  only when the runtime can genuinely honour it (a sword/fan weapon, an armour
  row with a declared position, or a potion with the recovery handler);
* everything else stays out of the registry and is recorded per reason, so
  raising coverage stays a deliberate change instead of an accident;
* IDs are derived, never invented: ``item.<kind>.<name-slug>-<vnum>``. The
  trailing vnum keeps the namespace stable and unique while the slug keeps it
  readable, and the source rows behind it are pinned ``item_proto.txt``.

Icons follow the original client's own resolution (``ItemManager.cpp``,
``LoadItemProto``): the exact ``icon/item/<vnum>.tga`` when the pinned packs
have it, otherwise the earlier same-name row's icon, otherwise
``vnum - vnum % 10``, otherwise the hard-coded ``EmptyBowl`` 27995.  The chain
lives in ``tools/item_icons.py`` and is applied here, so every row records the
picture the original actually showed: 103 exact and 225 base-10 among the 328
generated rows.  A row that would need the same-name or EmptyBowl rule stops the
build until someone reviews it (the profile's one hand-written 69000 row is the
only accepted EmptyBowl case).

Usage::

    python3 tools/build_item_selection.py
    python3 tools/build_item_selection.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_drop_catalog import DEFAULT_MOB_CONTENT, DropCatalogError, load_mob_ranks
from content_compile import ROOT, _server_reference_text, _source_identity
from item_definitions import compile_catalog, validate_catalog
from item_icons import (
    BASE_TEN,
    EXACT,
    ItemIconError,
    archive_predicate,
    icon_reference,
    proto_rows,
    resolve_targets,
)
from metin_archive import Archive
from metin_drops import DEFAULT_SOURCE, GROUP_TYPES, PLAYER_MAX_LEVEL, RANKS, compile_corpus

SCHEMA_VERSION = 1
DEFAULT_PROFILE = ROOT / "content/profiles/p0-warrior-dog.json"
DEFAULT_OUTPUT = ROOT / "content/profiles/drops/live-drops.json"
# ``item_definitions`` models three kinds; a ``narrative`` row would name an
# item the server cannot grant a mechanic for, so it is not selected.
KIND_PREFIX = {"weapon": "weapon", "armor": "armor", "recovery": "consumable"}
ITEM_ID = re.compile(r"item\.[a-z0-9][a-z0-9._-]{0,119}")
SLUG_LIMIT = 72
PROBE_ID = "item.probe.candidate"


class ItemSelectionError(RuntimeError):
    pass


def candidate_vnums(corpus: dict, mob_ranks: dict[str, int]) -> list[int]:
    """Every vnum the compiled drop tables could hand out, ascending."""
    candidates: set[int] = set()
    for rank in RANKS:
        for index, entry in enumerate(corpus["common"].get(rank, [])):
            level_start, level_end = entry.get("level_start"), entry.get("level_end")
            # ``CreateDropItem`` keeps a row only for a level inside both the
            # band and 1..PLAYER_MAX_LEVEL, matching the drop compiler.
            reachable = (
                isinstance(level_start, int)
                and isinstance(level_end, int)
                and 1 <= level_start <= PLAYER_MAX_LEVEL
                and level_start <= level_end
            )
            if entry.get("reachable") is not reachable:
                raise ItemSelectionError(
                    f"common {rank} row {index} disagrees with the corpus reachability"
                )
            if reachable:
                candidates.add(entry["vnum"])
    for kind in GROUP_TYPES:
        for vnum, group in corpus["groups"].get(kind, {}).items():
            if vnum not in mob_ranks:
                continue
            candidates.update(row["vnum"] for row in group["items"])
    return sorted(candidates)


def derive_id(kind: str, name: str, vnum: int) -> str:
    base = re.sub(r"\+\d+$", "", name.strip())
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:SLUG_LIMIT].strip("-")
    if not slug:
        slug = "vnum"
    content_id = f"item.{KIND_PREFIX[kind]}.{slug}-{vnum}"
    if not ITEM_ID.fullmatch(content_id):
        raise ItemSelectionError(f"derived item ID is not namespaced: {content_id!r}")
    return content_id


def classify(error: Exception) -> str:
    """Group per-row failures into stable, vnum-free reasons."""
    return re.sub(r"\d+", "#", str(error))


def proto_types(proto_text: str) -> dict[int, str]:
    """``{vnum: TYPE/SUBTYPE}`` for the rows a compile attempt can reach.

    The compiler's own refusal for an unmodelled row is deliberately generic
    ("uses an unsupported type/subtype"), which is the wrong granularity for a
    coverage ledger. The source row names the reason, so the notice says which
    mechanic is missing.
    """
    rows: dict[int, list[tuple[str, str]]] = {}
    for line in proto_text.splitlines()[1:]:
        columns = line.split("\t")
        if len(columns) > 3 and columns[0].isdecimal():
            rows.setdefault(int(columns[0]), []).append((columns[2], columns[3]))
    return {vnum: f"{kind}/{subtype}" for vnum, seen in rows.items() for kind, subtype in seen}


def build_item_selection(profile_path: Path, source_root: Path, mob_content: Path) -> dict:
    profile = json.loads(profile_path.read_text())
    identity = _source_identity(profile, "gamefiles/conf/item_proto.txt")
    proto_text = _server_reference_text(profile, "gamefiles/conf/item_proto.txt")
    names_text = _server_reference_text(profile, "gamefiles/conf/item_names_en.txt")
    corpus = compile_corpus(source_root)
    corpus_proto = corpus["source"]["files"]["item_proto"]["sha256"]
    if corpus_proto != identity["sha256"]:
        raise ItemSelectionError(
            "the drop corpus and the pinned content profile disagree about item_proto.txt"
        )
    candidates = candidate_vnums(corpus, load_mob_ranks(mob_content))
    types = proto_types(proto_text)
    rows: list[dict] = []
    excluded: dict[str, list[int]] = {}
    for vnum in candidates:
        probe = {
            "schema_version": SCHEMA_VERSION,
            "items": [
                {
                    "id": PROBE_ID,
                    "revision": 1,
                    "vnum": vnum,
                    "icon": icon_reference(vnum),
                }
            ],
        }
        try:
            item = compile_catalog(probe, proto_text, names_text, identity)["items"][0]
        except ValueError as error:
            excluded.setdefault(types.get(vnum, classify(error)), []).append(vnum)
            continue
        if item["kind"] not in KIND_PREFIX:
            excluded.setdefault(f"Item # compiles to an unmodelled {item['kind']} row", []).append(
                vnum
            )
            continue
        rows.append(
            {
                "id": derive_id(item["kind"], item["name"], vnum),
                "revision": 1,
                "vnum": vnum,
                # Replaced below with the picture the original client resolves.
                "icon": icon_reference(vnum),
            }
        )
    # Icons are resolved for the rows that ship: ``icon`` is the picture the
    # client renders, so the registry stores the fallback the original showed
    # instead of the vnum the pinned archive happens to lack. A row that needs
    # the same-name or EmptyBowl rule changes what the player sees, so it stops
    # the build until someone reviews it.
    icons, icon_counts = resolve_targets(
        proto_rows(proto_text), [row["vnum"] for row in rows], archive_predicate(Archive())
    )
    unreviewed = [
        (vnum, entry["icon"], entry["rule"])
        for vnum, entry in sorted(icons.items())
        if entry["rule"] not in (EXACT, BASE_TEN)
    ]
    if unreviewed:
        raise ItemSelectionError(
            "unreviewed item icon fallback(s): "
            + ", ".join(f"{vnum} {rule} -> {icon}" for vnum, icon, rule in unreviewed)
            + "; confirm the picture and add the row, or drop it from the selection"
        )
    for row in rows:
        row["icon"] = icons[row["vnum"]]["icon"]
    selection = {"schema_version": SCHEMA_VERSION, "items": rows}
    catalog = compile_catalog(selection, proto_text, names_text, identity)
    validate_catalog(catalog)
    kinds: dict[str, int] = {}
    for item, row in zip(catalog["items"], rows, strict=True):
        if item["vnum"] != row["vnum"] or item["id"] != row["id"]:
            raise ItemSelectionError("compiled registry disagrees with the generated selection")
        if item["icon"] != icons[item["vnum"]]["icon"]:
            raise ItemSelectionError("compiled registry dropped the resolved item icon")
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "corpus": {
                "revision": corpus["source"]["revision"],
                "sha256": corpus["content_hash"],
            },
            "item_proto": {
                "path": identity["path"],
                "revision": identity["revision"],
                "git_sha": identity["git_sha"],
                "sha256": identity["sha256"],
            },
            "item_names": _named_identity(profile, "gamefiles/conf/item_names_en.txt"),
            "mob_content": {
                "path": str(mob_content.relative_to(ROOT))
                if mob_content.is_relative_to(ROOT)
                else str(mob_content),
                "sha256": hashlib.sha256(mob_content.read_bytes()).hexdigest(),
            },
            "id_rule": "item.<weapon|armor|consumable>.<name-slug>-<vnum>",
            "icon_rule": (
                "ItemManager.cpp LoadItemProto chain: exact icon/item/<vnum>.tga, "
                "then the earlier same-name row's icon, then <vnum> - <vnum> % 10, "
                "then the hard-coded EmptyBowl 27995"
            ),
            "icon_resolution": {
                rule: count for rule, count in sorted(icon_counts.items()) if count
            },
            "selected_by_kind": dict(sorted(kinds.items())),
            "candidates": len(candidates),
            "excluded": {label: vnums for label, vnums in sorted(excluded.items())},
        },
        "items": rows,
    }


def _named_identity(profile: dict, relative: str) -> dict:
    declared = [
        row for row in profile["source"]["server_reference"]["files"] if row.get("path") == relative
    ]
    if len(declared) != 1:
        raise ItemSelectionError(f"Pinned source {relative} must be declared exactly once")
    return {
        "path": relative,
        "revision": profile["source"]["server_reference"]["revision"],
        "git_sha": declared[0].get("git_sha"),
        "sha256": declared[0].get("sha256"),
    }


def selection_text(selection: dict) -> str:
    return json.dumps(selection, indent=2) + "\n"


def selection_summary(selection: dict) -> str:
    source = selection["source"]
    lines = [
        f"item selection v{selection['schema_version']}: {len(selection['items'])} rows from "
        f"{source['candidates']} drop-referenced vnums",
        "selected: "
        + ", ".join(f"{kind} {count}" for kind, count in source["selected_by_kind"].items()),
        f"item_proto {source['item_proto']['git_sha'][:8]} corpus {source['corpus']['sha256'][:16]}",
    ]
    excluded = sum(len(vnums) for vnums in source["excluded"].values())
    if excluded:
        lines.append(f"excluded: {excluded} vnums the runtime cannot honour")
        for label, vnums in sorted(
            source["excluded"].items(), key=lambda row: (-len(row[1]), row[0])
        ):
            lines.append(f"  {len(vnums):4d}  {label}  e.g. {vnums[:5]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Tracked content profile whose pinned server_reference supplies item_proto.txt",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Pinned git.old-metin2.com server checkout holding the drop tables",
    )
    parser.add_argument(
        "--mob-content",
        type=Path,
        default=DEFAULT_MOB_CONTENT,
        help="Compiled mob gameplay catalog whose vnums select the drop groups",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Selection path")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the tracked selection differs from the pinned corpus",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        selection = build_item_selection(
            args.profile.resolve(), args.source.resolve(), args.mob_content.resolve()
        )
    except (DropCatalogError, ItemSelectionError, ItemIconError) as error:
        raise SystemExit(str(error)) from error
    text = selection_text(selection)
    if args.check:
        current = args.output.read_text() if args.output.is_file() else ""
        if current != text:
            raise SystemExit(f"{args.output} is stale; run python3 tools/build_item_selection.py")
        if not args.quiet:
            print(f"{args.output} is current")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    if not args.quiet:
        print(selection_summary(selection))
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
