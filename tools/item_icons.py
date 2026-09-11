#!/usr/bin/env python3
"""Resolve item icons through the pinned client's own fallback chain.

``CItemManager::LoadItemProto`` (``client/source/src/GameLib/ItemManager.cpp``,
pinned commit ``bb19e9ab``) never trusts ``icon/item/<vnum>.tga`` to exist.  For
every prototype it walks:

1. ``icon/item/<vnum>.tga`` when the loaded packs contain it;
2. otherwise the vnum of the *earlier* proto row whose ``szName`` has the same
   ``GetHashCode`` (the original keeps a name-to-first-vnum map, so only rows
   already visited can answer);
3. otherwise ``icon/item/<vnum - vnum % 10>.tga`` (the base-10 fallback);
4. otherwise the hard-coded ``EmptyBowl`` icon ``icon/item/27995.tga``.

The fallback is part of what the original shows, not an import convenience: the
pinned archive has no ``icon/item/00011.tga``, so ignoring the chain would drop
every second-row icon.  This module owns that decision once so the registry
generator, the UI importer and any future tool agree on it.

``resolve_targets`` is pure: the caller supplies the full proto row list (file
order matters for rule 2) and an ``exists(name) -> bool`` predicate over the
pinned pack contents.  ``archive_predicate`` builds that predicate from
``tools/metin_archive.py`` so the answer matches what the importer can fetch.

Usage::

    python3 tools/item_icons.py                       # report the tracked profile
    python3 tools/item_icons.py --check               # fail on an unreviewed fallback
    python3 tools/item_icons.py --json                # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from item_definitions import expand_selection
from metin_archive import Archive

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "content/profiles/p0-warrior-dog.json"

# ``const DWORD EmptyBowl = 27995;`` in the pinned loader.
EMPTY_BOWL_VNUM = 27995

EXACT = "exact"
SAME_NAME = "same-name"
BASE_TEN = "base-10"
EMPTY_BOWL = "empty-bowl"
RULES = (EXACT, SAME_NAME, BASE_TEN, EMPTY_BOWL)

# Rules the installed registry is expected to use. ``same-name`` and
# ``empty-bowl`` change which picture the player sees, so a new one has to be
# reviewed and listed here (or, better, its prototype dropped from the
# selection) instead of arriving silently with an expanded drop table.
REVIEWED_FALLBACKS = {69000: EMPTY_BOWL}


class ItemIconError(RuntimeError):
    pass


def icon_reference(vnum: int) -> str:
    """``icon/item/<vnum>`` zero-padded to five digits, as the client formats it."""
    if not isinstance(vnum, int) or isinstance(vnum, bool) or vnum < 0:
        raise ItemIconError(f"Invalid icon vnum: {vnum!r}")
    return f"icon/item/{vnum:05d}"


def proto_name_hash(name: str) -> int:
    """``GetHashCode`` from the pinned ``ItemManager.cpp``: djb2 over raw bytes.

    The pinned ``item_proto.txt`` is EUC-KR and every reader in this repository
    decodes it as latin-1, so re-encoding that way reproduces the exact bytes the
    client hashes.  A caller that hands over a decoded (non latin-1) name still
    gets a stable key, which is all rule 2 needs.
    """
    if not isinstance(name, str) or not name:
        raise ItemIconError(f"Invalid proto name: {name!r}")
    try:
        raw = name.encode("latin-1")
    except UnicodeEncodeError:
        raw = name.encode("utf-8")
    result = 5381
    for byte in raw:
        result = ((result << 5) + result + byte) & 0xFFFFFFFF
    return result


def proto_rows(proto_text: str) -> list[tuple[int, str]]:
    """``(vnum, name)`` for every proto row, in the file's own order.

    Order is the whole point of rule 2: the client's name map only holds rows it
    has already visited, so an earlier duplicate is the only acceptable answer.
    """
    rows: list[tuple[int, str]] = []
    for line in proto_text.splitlines()[1:]:
        columns = line.split("\t")
        if columns and columns[0].isdecimal() and len(columns) >= 2:
            rows.append((int(columns[0]), columns[1]))
    if not rows:
        raise ItemIconError("Proto table has no readable rows")
    return rows


def resolve_icon(vnum: int, name: str, first_of_name: dict[int, int], exists) -> tuple[str, str]:
    """The client's four-step lookup for one prototype."""
    if exists(icon_reference(vnum) + ".tga"):
        return icon_reference(vnum), EXACT
    earlier = first_of_name.get(proto_name_hash(name))
    if earlier is not None and earlier != vnum:
        candidate = icon_reference(earlier)
        if exists(candidate + ".tga"):
            return candidate, SAME_NAME
    base = icon_reference(vnum - vnum % 10)
    if exists(base + ".tga"):
        return base, BASE_TEN
    return icon_reference(EMPTY_BOWL_VNUM), EMPTY_BOWL


def resolve_targets(
    rows: list[tuple[int, str]], targets: list[int], exists
) -> tuple[dict[int, dict[str, str]], dict[str, int]]:
    """Resolve every target vnum, returning ``{vnum: {icon, rule}}`` and counts."""
    first_of_name: dict[int, int] = {}
    for vnum, name in rows:
        first_of_name.setdefault(proto_name_hash(name), vnum)
    names: dict[int, list[str]] = {}
    for vnum, name in rows:
        names.setdefault(vnum, []).append(name)
    resolved: dict[int, dict[str, str]] = {}
    counts = dict.fromkeys(RULES, 0)
    for vnum in targets:
        matches = names.get(vnum, [])
        if len(matches) != 1:
            raise ItemIconError(f"Icon target {vnum} needs exactly one proto name row")
        icon, rule = resolve_icon(vnum, matches[0], first_of_name, exists)
        resolved[vnum] = {"icon": icon, "rule": rule}
        counts[rule] += 1
    return resolved, counts


def archive_predicate(archive: Archive):
    """``exists(virtual name)`` over the pinned packs, caching each answer.

    Uses the archive's own ``resolve`` so a conflict between pack versions is a
    loud ``ValueError`` instead of a guess the importer would not repeat.
    """
    archive.inventory()
    answers: dict[str, bool] = {}

    def exists(name: str) -> bool:
        if name not in answers:
            try:
                archive.resolve(name)
            except FileNotFoundError:
                answers[name] = False
            else:
                answers[name] = True
        return answers[name]

    return exists


def profile_rows(profile_path: Path) -> tuple[list[tuple[int, str]], list[int]]:
    """The pinned proto rows and the vnums a tracked profile installs."""
    profile = json.loads(profile_path.read_text())
    try:
        selection = profile["item_catalog"]
    except (KeyError, TypeError):
        raise ItemIconError(f"Profile has no item_catalog: {profile_path}") from None
    merged, _ = expand_selection(selection, profile_path.parent)
    reference = profile["source"]["server_reference"]
    proto_path = (
        ROOT
        / "assets/source/content/server"
        / reference["revision"]
        / "gamefiles/conf/item_proto.txt"
    )
    text = proto_path.read_text(encoding="latin-1")
    targets = [row["vnum"] for row in merged["items"]]
    return proto_rows(text), targets


def unreviewed(resolved: dict[int, dict[str, str]]) -> list[tuple[int, str, str]]:
    rows = []
    for vnum, entry in sorted(resolved.items()):
        if entry["rule"] not in (EXACT, BASE_TEN) and REVIEWED_FALLBACKS.get(vnum) != entry["rule"]:
            rows.append((vnum, entry["icon"], entry["rule"]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when a row uses a fallback that is not reviewed in REVIEWED_FALLBACKS",
    )
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    args = parser.parse_args(argv)

    try:
        rows, targets = profile_rows(args.profile.resolve())
        resolved, counts = resolve_targets(rows, targets, archive_predicate(Archive()))
    except (ItemIconError, ValueError, OSError) as error:
        print(f"item icons: {error}", file=sys.stderr)
        return 1

    fallbacks = [
        {"vnum": vnum, "icon": entry["icon"], "rule": entry["rule"]}
        for vnum, entry in sorted(resolved.items())
        if entry["rule"] not in (EXACT, BASE_TEN)
    ]
    report = {
        "profile": str(args.profile),
        "rows": len(targets),
        "rules": counts,
        "fallbacks": fallbacks,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"{args.profile}: {len(targets)} rows resolved "
            + ", ".join(f"{rule} {count}" for rule, count in counts.items() if count)
        )
        for entry in fallbacks:
            print(f"  {entry['rule']:10s} {entry['vnum']:6d} -> {entry['icon']}")
    if args.check:
        bad = unreviewed(resolved)
        if bad:
            print(
                "unreviewed icon fallback(s): "
                + ", ".join(f"{vnum} ({rule})" for vnum, _, rule in bad),
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
