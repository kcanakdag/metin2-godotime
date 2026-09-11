#!/usr/bin/env python3
"""Compile the pinned drop corpus into the catalog the server rolls loot from.

``tools/metin_drops.py`` replays the original ``ITEM_MANAGER`` table readers;
this compiler narrows that corpus to what a running module can actually use and
refuses to ship a table that references an item prototype the source never
defined. Every dropped vnum is checked against the 5,743 pinned prototypes, so a
typo in an input table fails the build instead of silently becoming a no-drop
entry at runtime.

Only mobs present in the selected mob catalog receive a rank. Common drops are
selected by that rank, so a mob the source has a group for but the module cannot
spawn is recorded as a notice rather than compiled into a table nothing can
reach. The same rule applies to items: a row whose vnum is missing from the
installed item registry (``content/profiles/p0-warrior-dog.json`` and whatever
its ``item_catalog`` includes) is dropped with a notice, because the runtime
grants loot by looking the prototype up and would otherwise roll a vnum it
cannot hand out.

Two pinned quirks are resolved here rather than at runtime. ``CreateDropItem``
creates exactly one item per common row and never reads the row's parsed
``iCount``, so the catalog stores ``count: 1`` and does not leak a placeholder
column (the pinned file reaches ``INT_MAX``) into the drop path. 29 pinned lines
are malformed in a way that makes the original's shared tab cursor read a level
band above the level cap (see ``tools/metin_drops.py``); those rows can never be
selected, so they are dropped and counted instead of shipped as dead weight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import ROOT
from item_definitions import expand_selection
from metin_drops import (
    DEFAULT_SOURCE,
    GROUP_TYPES,
    ITEM_PROTO,
    MOB_RANKS,
    PLAYER_MAX_LEVEL,
    RANKS,
    DropCorpusError,
    ItemTable,
    compile_corpus,
    load_item_table,
)
from progression_definitions import (
    ProgressionDefinitionError,
    parse_mob_level_delta_tables,
)

SCHEMA = "mt2spacetime.static-drops"
VERSION = 1
DEFAULT_MOB_CONTENT = ROOT / ".local/mobs/server-package-r2/gameplay.v1.json"
DEFAULT_PROFILE = ROOT / "content/profiles/p0-warrior-dog.json"
# ``GetDropPct`` scales every loot roll by a level-delta percentage that lives
# in the pinned constants rather than in a drop table, so the catalog carries
# the pair with the same hash discipline as the replayed corpus files.
CONSTANTS_SOURCE = Path("src/game/src/constants.cpp")
LEVEL_DELTA_COUNT = 31

# ``ReadCommonDropItemFile`` fills ranks 0..``MOB_RANK_S_KNIGHT``; ``MOB_RANK_BOSS``
# and ``MOB_RANK_KING`` are outside that range, so a boss can never roll a common
# drop and the rank lookup must not fall back to a neighbouring table. The mob
# catalog still carries those two ranks, so they are validated but never looked
# up in the common table.
COMMON_RANKS = RANKS

# Original percentages are ``strtol`` results that the engine scales down again
# by the level-delta and drop-rate modifiers, so they are not bounded by 10000:
# the pinned common table reaches 750000 (7500 after the usual 100 divisor).
PERCENT_10K_MAX = 100_000_000
PERCENT_RAW_MAX = 100
CUMULATIVE_MAX = 2**31 - 1
# ``InventoryItem::count`` and ``ItemDrop::count`` are u16, so a source count
# above the protocol maximum is clamped at compile time and reported.
COUNT_MAX = 65_535
VNUM_MAX = 2**32 - 1


class DropCatalogError(RuntimeError):
    pass


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mob_ranks(path: Path) -> dict[str, int]:
    """``{vnum: EMobRank}`` for every mob the selected package can spawn."""
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DropCatalogError(f"Cannot read the mob catalog {path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("mobs"), list):
        raise DropCatalogError(f"Mob catalog {path} has no mob list")
    ranks: dict[str, int] = {}
    for index, mob in enumerate(document["mobs"]):
        if not isinstance(mob, dict):
            raise DropCatalogError(f"Mob catalog {path} entry {index} is not an object")
        vnum = mob.get("vnum")
        if not isinstance(vnum, int) or isinstance(vnum, bool) or not 1 <= vnum <= VNUM_MAX:
            raise DropCatalogError(f"Mob catalog {path} entry {index} has an invalid vnum")
        source = mob.get("source_definition")
        rank = source.get("rank") if isinstance(source, dict) else None
        if rank not in MOB_RANKS:
            raise DropCatalogError(
                f"Mob catalog {path} vnum {vnum} has an unsupported rank: {rank!r}"
            )
        key = str(vnum)
        if key in ranks:
            raise DropCatalogError(f"Mob catalog {path} repeats vnum {vnum}")
        ranks[key] = MOB_RANKS.index(rank)
    if not ranks:
        raise DropCatalogError(f"Mob catalog {path} is empty")
    return ranks


def declared_source_sha256(profile_path: Path, relative: str) -> str | None:
    """Pinned ``sha256`` the profile declares for one source file, if any."""
    try:
        document = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DropCatalogError(f"Cannot read the profile {profile_path}: {error}") from error
    reference = (document.get("source") or {}).get("server_reference") or {}
    declared = [
        row.get("sha256") for row in reference.get("files", []) if row.get("path") == relative
    ]
    if len(declared) > 1:
        raise DropCatalogError(f"Pinned source {relative} is declared more than once")
    return declared[0] if declared else None


def load_level_delta(source_root: Path, profile_path: Path) -> dict:
    """``PERCENT_LVDELTA`` tables plus provenance, from the pinned tree.

    The percentages are constants of the original server (``constants.cpp``),
    not rows of a drop table, so they are read here and carried in the compiled
    catalog. The profile declares the pinned revision's identity for the file
    and a checkout that disagrees fails the build instead of shipping a
    different percentage table.
    """
    path = source_root / CONSTANTS_SOURCE
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise DropCatalogError(f"Cannot read the pinned {CONSTANTS_SOURCE}: {error}") from error
    digest = hashlib.sha256(payload).hexdigest()
    declared = declared_source_sha256(profile_path, CONSTANTS_SOURCE)
    if declared is not None and declared != digest:
        raise DropCatalogError(
            f"{CONSTANTS_SOURCE} does not match the pinned profile identity "
            f"({digest} != {declared})"
        )
    try:
        constants = payload.decode("utf-8")
    except UnicodeDecodeError:
        constants = payload.decode("latin-1")
    try:
        normal, boss = parse_mob_level_delta_tables(constants)
    except ProgressionDefinitionError as error:
        raise DropCatalogError(f"{CONSTANTS_SOURCE}: {error}") from error
    return {
        "source": {"path": str(CONSTANTS_SOURCE), "sha256": digest},
        "normal_percent": list(normal),
        "boss_percent": list(boss),
    }


def load_registered_vnums(profile_path: Path) -> tuple[set[int], dict]:
    """``({vnum}, identity)`` for every prototype the installed registry holds.

    The drop tables and the item registry are compiled from the same pinned
    corpus, but only the registry decides what the module can actually hand
    out: ``inventory::grant`` looks the prototype up by vnum and a row without
    one is unroutable. The selection is read through the same ``include``
    resolution the content compiler uses, so a profile that pulls in a
    generated registry (``drops/live-drops.json``) cannot drift from what the
    module ships. Every resolved document is hashed into the catalog so a
    review can bind the drop table to the exact registry that produced it.
    """
    try:
        document = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DropCatalogError(f"Cannot read the profile {profile_path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("item_catalog"), dict):
        raise DropCatalogError(f"Profile {profile_path} has no item catalog")
    try:
        merged, resolved = expand_selection(document["item_catalog"], profile_path.parent)
    except ValueError as error:
        raise DropCatalogError(f"Profile {profile_path} item catalog: {error}") from error
    vnums: set[int] = set()
    for index, row in enumerate(merged["items"]):
        if not isinstance(row, dict):
            raise DropCatalogError(f"Registry row {index} is not an object")
        vnum = row.get("vnum")
        if not isinstance(vnum, int) or isinstance(vnum, bool) or not 1 <= vnum <= VNUM_MAX:
            raise DropCatalogError(f"Registry row {index} has an invalid vnum: {vnum!r}")
        if vnum in vnums:
            raise DropCatalogError(f"Registry repeats vnum {vnum}")
        vnums.add(vnum)

    def describe(path: Path) -> str:
        # Keep the identity portable: an absolute workstation path would make
        # two checkouts of the same revision compile to different catalogs.
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    identity = {
        "profile": describe(profile_path),
        "profile_sha256": sha256_path(profile_path),
        "vnums": len(vnums),
        "includes": [{"path": describe(path), "sha256": sha256_path(path)} for path in resolved],
    }
    return vnums, identity


def _row(entry: dict, label: str, percent_key: str = "pct_10k") -> dict:
    vnum = entry["vnum"]
    if not isinstance(vnum, int) or isinstance(vnum, bool) or not 1 <= vnum <= VNUM_MAX:
        raise DropCatalogError(f"{label} has an invalid item vnum")
    count = entry["count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise DropCatalogError(f"{label} vnum {vnum} has an unsupported count: {count!r}")
    if count > COUNT_MAX:
        count = COUNT_MAX
    row = {"vnum": vnum, "count": count}
    if percent_key in entry:
        percent = entry[percent_key]
        if (
            not isinstance(percent, int)
            or isinstance(percent, bool)
            or not 0 <= percent <= PERCENT_10K_MAX
        ):
            raise DropCatalogError(f"{label} vnum {vnum} has an invalid percent: {percent!r}")
        row["pct_10k"] = percent
    if "part_pct" in entry:
        part = entry["part_pct"]
        cumulative = entry.get("cumulative_pct")
        rare = entry.get("rare_pct")
        for name, value, high in (
            ("part_pct", part, PERCENT_RAW_MAX),
            ("cumulative_pct", cumulative, CUMULATIVE_MAX),
            ("rare_pct", rare, PERCENT_RAW_MAX),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= high:
                raise DropCatalogError(f"{label} vnum {vnum} has an invalid {name}: {value!r}")
        if part <= 0:
            raise DropCatalogError(f"{label} vnum {vnum} has a non-positive part percent")
        if cumulative < part:
            raise DropCatalogError(f"{label} vnum {vnum} has a decreasing cumulative percent")
        row["part_pct"] = part
        row["cumulative_pct"] = cumulative
        row["rare_pct"] = rare
    return row


def _group(
    kind: str, vnum: str, group: dict, prototypes: ItemTable, registry: set[int]
) -> tuple[dict, list[int]]:
    label = f"{kind} group {vnum}"
    rows = group.get("items")
    if not isinstance(rows, list) or not rows:
        raise DropCatalogError(f"{label} has no rows")
    compiled = []
    unregistered: list[int] = []
    previous = 0
    for index, entry in enumerate(rows):
        if not isinstance(entry, dict):
            raise DropCatalogError(f"{label} row {index} is not an object")
        if kind == "kill" and not {"part_pct", "cumulative_pct"} <= entry.keys():
            raise DropCatalogError(f"{label} row {index} has no cumulative percent")
        row = _row(entry, label)
        if not prototypes.contains(row["vnum"]):
            raise DropCatalogError(f"{label} drops undefined item vnum {row['vnum']}")
        if row["vnum"] not in registry:
            # The original table is intact, but the module has no prototype to
            # hand out. Dropping the row keeps the remaining weights honest:
            # the kill roll still spans ``back(cumulative_pct)`` of the rows
            # that survive.
            unregistered.append(row["vnum"])
            continue
        if kind == "kill":
            # ``GetOneIndex`` rolls ``Random::get(1, m_vecProbs.back())``; the
            # reader aborts the original load on a zero part percent, so the
            # cumulative vector is always positive by the time it is rolled.
            if row["cumulative_pct"] < previous:
                raise DropCatalogError(f"{label} is not sorted by cumulative percent")
            previous = row["cumulative_pct"]
        compiled.append(row)
    return {"vnum": int(vnum), "items": compiled}, unregistered


def compile_catalog(
    corpus: dict,
    prototypes: ItemTable,
    mob_ranks: dict[str, int],
    registry: set[int],
    registry_identity: dict,
    level_delta: dict,
) -> dict:
    """Narrow the raw corpus into the runtime catalog."""
    if corpus.get("schema") != "mt2spacetime.drop-corpus" or corpus.get("schema_version") != 2:
        raise DropCatalogError("Unsupported drop corpus")
    for name in ("normal_percent", "boss_percent"):
        table = level_delta.get(name)
        if (
            not isinstance(table, list)
            or len(table) != LEVEL_DELTA_COUNT
            or any(
                not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1000
                for value in table
            )
        ):
            raise DropCatalogError(
                f"Level-delta table {name} must contain {LEVEL_DELTA_COUNT} values within 0..1000"
            )
    source = level_delta.get("source")
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("path"), str)
        or not isinstance(source.get("sha256"), str)
        or len(source["sha256"]) != 64
    ):
        raise DropCatalogError("Level-delta tables must carry their pinned source identity")
    ranks = corpus.get("ranks")
    if tuple(ranks or ()) != RANKS:
        raise DropCatalogError("Drop corpus rank order differs from EMobRank")
    common = {}
    unreachable = {rank: 0 for rank in COMMON_RANKS}
    clamped = {rank: 0 for rank in COMMON_RANKS}
    unregistered_common = {rank: 0 for rank in COMMON_RANKS}
    for rank in COMMON_RANKS:
        rows = corpus["common"].get(rank)
        if not isinstance(rows, list) or not rows:
            raise DropCatalogError(f"Common drop rank {rank} has no rows")
        entries = []
        for index, entry in enumerate(rows):
            label = f"common {rank} row {index}"
            if not isinstance(entry, dict):
                raise DropCatalogError(f"{label} is not an object")
            level_start = entry.get("level_start")
            level_end = entry.get("level_end")
            if (
                not isinstance(level_start, int)
                or isinstance(level_start, bool)
                or level_start < 0
                or not isinstance(level_end, int)
                or isinstance(level_end, bool)
                or level_end < 0
            ):
                raise DropCatalogError(f"{label} has an invalid level range")
            # ``CreateDropItem`` keeps a row only when
            # ``iLevelStart <= level <= iLevelEnd`` for a real player level, so
            # a band outside ``1..PLAYER_MAX_LEVEL`` never rolls. The corpus
            # carries the reader's own verdict; re-derive it and refuse to
            # compile when the two disagree.
            # The malformed rows read a band far above the cap, so the range
            # check only applies to the rows that can actually be selected.
            reachable = 1 <= level_start <= PLAYER_MAX_LEVEL and level_start <= level_end
            if entry.get("reachable") is not reachable:
                raise DropCatalogError(f"{label} disagrees with the corpus reachability")
            if not reachable:
                unreachable[rank] += 1
                continue
            if level_end > PLAYER_MAX_LEVEL:
                # Matching is ``level <= level_end`` and no level exceeds the
                # cap, so shortening the band cannot change an outcome.
                level_end = PLAYER_MAX_LEVEL
                clamped[rank] += 1
            vnum = entry.get("vnum")
            if not isinstance(vnum, int) or isinstance(vnum, bool) or not 1 <= vnum <= VNUM_MAX:
                raise DropCatalogError(f"{label} has an invalid item vnum")
            percent = entry.get("percent")
            if (
                not isinstance(percent, int)
                or isinstance(percent, bool)
                or not 0 <= percent <= PERCENT_10K_MAX
            ):
                raise DropCatalogError(f"{label} has an invalid percent: {percent!r}")
            if not prototypes.contains(vnum):
                raise DropCatalogError(f"{label} drops undefined item vnum {vnum}")
            if vnum not in registry:
                unregistered_common[rank] += 1
                continue
            entries.append(
                {
                    "level_start": level_start,
                    "level_end": level_end,
                    "pct_10k": percent,
                    # ``CreateItem(c_rInfo.m_dwVnum, 1, 0, true)``: the parsed
                    # ``iCount`` is stored by the reader and never used.
                    "count": 1,
                    "vnum": vnum,
                }
            )
        if not entries:
            raise DropCatalogError(f"Common drop rank {rank} has no reachable rows")
        common[rank] = entries

    groups: dict[str, list[dict]] = {}
    notices: list[dict] = []
    for kind in GROUP_TYPES:
        for vnum in sorted(corpus["groups"].get(kind, {}), key=int):
            group = corpus["groups"][kind][vnum]
            if group.get("type") != kind or str(group.get("mob_vnum")) != vnum:
                raise DropCatalogError(f"{kind} group {vnum} is inconsistent with its map")
            if vnum not in mob_ranks:
                notices.append({"mob_vnum": int(vnum), "type": kind, "reason": "mob-not-selected"})
                continue
            compiled, unregistered = _group(kind, vnum, group, prototypes, registry)
            if unregistered:
                notices.append(
                    {
                        "mob_vnum": int(vnum),
                        "type": kind,
                        "reason": "item-not-registered",
                        "item_vnums": unregistered,
                    }
                )
            if not compiled["items"]:
                # Nothing in this table survives the registry filter, so the
                # runtime must not see an empty group it would roll against.
                continue
            slot = groups.setdefault(
                vnum,
                {
                    "mob_vnum": int(vnum),
                    "rank": mob_ranks[vnum],
                    # ``CMobItemGroup::GetKillPerDrop`` weights the single
                    # kill-group roll; ``CLevelItemGroup::GetLevelLimit`` gates
                    # the limit table. Both are per-group constants the runtime
                    # would otherwise have to re-read from the corpus.
                    "kill_drop": 0,
                    "level_limit": 0,
                    **{k: [] for k in GROUP_TYPES},
                },
            )
            if slot["rank"] != mob_ranks[vnum]:
                raise DropCatalogError(f"Mob {vnum} has contradictory ranks")
            if kind == "kill":
                kill_drop = group.get("kill_drop")
                if (
                    not isinstance(kill_drop, int)
                    or isinstance(kill_drop, bool)
                    or not 1 <= kill_drop <= CUMULATIVE_MAX
                ):
                    raise DropCatalogError(f"kill group {vnum} has an invalid kill_drop")
                slot["kill_drop"] = kill_drop
            if kind == "limit":
                level_limit = group.get("level_limit")
                if (
                    not isinstance(level_limit, int)
                    or isinstance(level_limit, bool)
                    or not 0 <= level_limit <= PLAYER_MAX_LEVEL
                ):
                    raise DropCatalogError(f"limit group {vnum} has an invalid level_limit")
                slot["level_limit"] = level_limit
            slot[kind] = compiled["items"]

    catalog = {
        "schema": SCHEMA,
        "version": VERSION,
        "item_prototypes": {
            "count": corpus["item_prototypes"]["count"],
            "range_rows": corpus["item_prototypes"]["range_rows"],
            "sha256": corpus["item_prototypes"]["sha256"],
        },
        "level_delta": {
            "source": level_delta["source"],
            "normal_percent": list(level_delta["normal_percent"]),
            "boss_percent": list(level_delta["boss_percent"]),
        },
        "source": {
            "root": corpus["source"]["root"],
            "revision": corpus["source"]["revision"],
            "files": corpus["source"]["files"],
            "corpus_hash": corpus["content_hash"],
            "item_registry": registry_identity,
        },
        "common": common,
        "groups": {vnum: groups[vnum] for vnum in sorted(groups, key=int)},
        "summary": {
            "common_rows": sum(len(rows) for rows in common.values()),
            "common_by_rank": {rank: len(common[rank]) for rank in COMMON_RANKS},
            "groups": len(groups),
            "groups_by_type": {
                kind: sum(1 for slot in groups.values() if slot[kind]) for kind in GROUP_TYPES
            },
            "group_rows": sum(len(slot[kind]) for slot in groups.values() for kind in GROUP_TYPES),
            "mobs_by_rank": {
                rank: sum(1 for slot in groups.values() if slot["rank"] == index)
                for index, rank in enumerate(MOB_RANKS)
            },
            # The catalog is smaller than the corpus on purpose. Both counters
            # are part of the artifact so a review can reconcile the two
            # without re-reading the pinned source.
            "excluded_common_rows": {
                "unreachable": {rank: count for rank, count in unreachable.items() if count},
                "clamped_level_end": {rank: count for rank, count in clamped.items() if count},
                "unregistered_item": {
                    rank: count for rank, count in unregistered_common.items() if count
                },
            },
            "group_rows_dropped": sum(
                len(notice["item_vnums"])
                for notice in notices
                if notice["reason"] == "item-not-registered"
            ),
            "notices": notices,
        },
    }
    catalog["content_hash"] = catalog_hash(catalog)
    return catalog


def catalog_hash(catalog: dict) -> str:
    payload = {key: value for key, value in catalog.items() if key != "content_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def catalog_text(catalog: dict) -> str:
    return json.dumps(catalog, indent=1, sort_keys=True) + "\n"


def catalog_summary(catalog: dict) -> str:
    summary = catalog["summary"]
    source = catalog["source"]
    lines = [
        f"{catalog['schema']} v{catalog['version']} ({catalog['content_hash'][:16]})",
        f"source: {source['root']} @ {source['revision'] or 'unknown revision'} "
        f"corpus {source['corpus_hash'][:16]}",
        f"item prototypes: {catalog['item_prototypes']['count']} rows "
        f"sha256 {catalog['item_prototypes']['sha256'][:16]}",
        f"level delta: {LEVEL_DELTA_COUNT} normal + {LEVEL_DELTA_COUNT} boss percentages "
        f"from {catalog['level_delta']['source']['path']} "
        f"sha256 {catalog['level_delta']['source']['sha256'][:16]}",
        f"common drops: {summary['common_rows']} rows "
        + ", ".join(f"{rank} {count}" for rank, count in summary["common_by_rank"].items()),
        f"mob groups: {summary['groups']} mobs, {summary['group_rows']} rows "
        + ", ".join(f"{kind} {count}" for kind, count in summary["groups_by_type"].items()),
        "mobs by rank: "
        + ", ".join(f"{rank} {count}" for rank, count in summary["mobs_by_rank"].items()),
    ]
    excluded = summary["excluded_common_rows"]
    dropped = sum(excluded["unreachable"].values())
    if dropped:
        lines.append(
            f"excluded common rows: {dropped} unreachable ("
            + ", ".join(f"{rank} {count}" for rank, count in excluded["unreachable"].items())
            + ")"
        )
    clamped = sum(excluded["clamped_level_end"].values())
    if clamped:
        lines.append(
            f"clamped common rows: {clamped} level_end above the cap ("
            + ", ".join(f"{rank} {count}" for rank, count in excluded["clamped_level_end"].items())
            + ")"
        )
    unregistered = excluded.get("unregistered_item", {})
    dropped_rows = sum(unregistered.values())
    if dropped_rows:
        lines.append(
            f"excluded common rows: {dropped_rows} for items outside the registry ("
            + ", ".join(f"{rank} {count}" for rank, count in unregistered.items())
            + ")"
        )
    if summary["notices"]:
        unselected = sum(
            1 for notice in summary["notices"] if notice["reason"] == "mob-not-selected"
        )
        lines.append(
            f"notices: {len(summary['notices'])} group table(s) "
            f"({unselected} for unselected mobs, "
            f"{summary.get('group_rows_dropped', 0)} row(s) for unregistered items)"
        )
    return "\n".join(lines)


def build(source_root: Path, mob_content: Path, profile: Path) -> dict:
    corpus = compile_corpus(source_root)
    prototypes = load_item_table((source_root / ITEM_PROTO).read_bytes())
    registry, identity = load_registered_vnums(profile)
    catalog = compile_catalog(
        corpus,
        prototypes,
        load_mob_ranks(mob_content),
        registry,
        identity,
        load_level_delta(source_root, profile),
    )
    # A shipped catalog whose every group belongs to an unselected mob means the
    # mob content and the drop corpus disagree; refuse to publish the result
    # instead of silently shipping a server where nothing ever drops.
    if not catalog["groups"]:
        raise DropCatalogError("No drop group matches the selected mob catalog")
    if not catalog["summary"]["common_rows"]:
        raise DropCatalogError("No common drop row matches the installed item registry")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Pinned git.old-metin2.com server checkout",
    )
    parser.add_argument(
        "--mob-content",
        type=Path,
        default=DEFAULT_MOB_CONTENT,
        help="Compiled mob gameplay catalog whose ranks select the common table",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Profile whose item catalogue the module installs",
    )
    parser.add_argument("--output", type=Path, required=True, help="Compiled catalog path")
    parser.add_argument(
        "--install",
        action="store_true",
        help="copy the catalog to server/content/drops/catalog.v1.json",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        catalog = build(args.source.resolve(), args.mob_content.resolve(), args.profile.resolve())
    except (DropCorpusError, DropCatalogError) as error:
        raise SystemExit(str(error)) from error
    text = catalog_text(catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    if args.install:
        installed = ROOT / "server/content/drops/catalog.v1.json"
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text(text)
    if not args.quiet:
        print(catalog_summary(catalog))
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
