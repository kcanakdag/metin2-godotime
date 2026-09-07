#!/usr/bin/env python3
"""Reconcile a private item snapshot against its complete quantity audit history."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def integer(row: dict, key: str, minimum: int = 0, maximum: int = 2**64 - 1) -> int:
    value = row.get(key)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"invalid {key}")
    return value


def reconcile(snapshot: dict, definitions: dict) -> dict:
    """Fail closed on a partial history, reused ID, double pickup or unexplained stock."""
    rules = {item["vnum"]: item for item in definitions["item_catalog"]["items"]}
    history: dict[tuple[str, int], dict] = {}
    pickup_credits: Counter = Counter()
    pickup_debits: Counter = Counter()
    minted: Counter = Counter()
    burned: Counter = Counter()
    previous_event = 0
    for event in snapshot["audit"]:
        event_id = integer(event, "id", 1)
        if event_id <= previous_event:
            raise ValueError("audit IDs must be unique and strictly ordered")
        previous_event = event_id
        item_id = integer(event, "item_id")
        drop_id = integer(event, "drop_id")
        location = "inventory" if item_id else "drops"
        entity_id = item_id or drop_id
        if not entity_id:
            raise ValueError("audit record has no entity ID")
        key = (location, entity_id)
        vnum = integer(event, "vnum", 1, 2**32 - 1)
        if vnum not in rules:
            raise ValueError("audit references an unknown item definition")
        limit = rules[vnum]["stack_limit"]
        before = integer(event, "previous_count", 0, limit)
        after = integer(event, "count", 0, limit)
        revision = integer(event, "revision", 1 if item_id else 0, 2**32 - 1)
        prior = history.get(key)
        if prior is None:
            if before or not after or (item_id and revision != 1):
                raise ValueError("item history must start with creation")
        elif (
            prior["count"] == 0
            or before != prior["count"]
            or any(event[field] != prior[field] for field in ("vnum", "owner", "account"))
            or (item_id and revision <= prior["revision"])
        ):
            raise ValueError("item history has a gap, identity change or reused ID")
        delta = after - before
        cause = event["cause"]
        if cause in ("starter", "progression", "monster"):
            if (
                delta <= 0
                or (cause == "monster" and item_id)
                or (cause == "starter" and not item_id)
            ):
                raise ValueError("invalid mint event")
            minted[vnum] += delta
        elif cause == "consume":
            if not item_id or delta != -1 or drop_id:
                raise ValueError("invalid consume event")
            burned[vnum] += 1
        elif cause == "expiry":
            if item_id or after or not before:
                raise ValueError("invalid expiry event")
            burned[vnum] += before
        elif cause == "pickup":
            if item_id:
                source = history.get(("drops", drop_id))
                if delta <= 0 or not source or source["count"] == 0 or source["vnum"] != vnum:
                    raise ValueError("pickup credits a missing, retired or different drop")
                pickup_credits[drop_id] += delta
            else:
                if after or not before:
                    raise ValueError("invalid pickup retirement")
                pickup_debits[drop_id] += before
        else:
            raise ValueError("unknown audit cause")
        if cause != "pickup" and item_id and drop_id:
            raise ValueError("unexpected drop reference")
        history[key] = event
    if pickup_credits != pickup_debits:
        raise ValueError("pickup credits and retired drop quantities differ")

    live: Counter = Counter()
    seen = set()
    occupied = set()
    weapons = set()
    for location in ("inventory", "drops"):
        for row in snapshot[location]:
            key = (location, integer(row, "id", 1))
            if key in seen:
                raise ValueError("duplicate live item ID")
            seen.add(key)
            prior = history.get(key)
            if prior is None or prior["count"] == 0:
                raise ValueError("live item has no active audited origin")
            for field in ("count", "vnum", "owner"):
                if row[field] != prior[field]:
                    raise ValueError("live quantity, definition or owner differs from history")
            if location == "inventory":
                if (
                    row["account"] != prior["account"]
                    or integer(row, "revision", 1, 2**32 - 1) < prior["revision"]
                ):
                    raise ValueError("live account or revision differs from history")
                rule = rules[row["vnum"]]
                cell = integer(row, "cell", 0, 255)
                if type(row["equipped"]) is not bool:
                    raise ValueError("invalid equipment flag")
                if row["equipped"]:
                    if (
                        cell != 255
                        or rule["kind"] != "weapon"
                        or row["count"] != 1
                        or row["owner"] in weapons
                    ):
                        raise ValueError("invalid or duplicate equipped weapon")
                    weapons.add(row["owner"])
                else:
                    if cell >= 90 or cell % 45 // 5 + rule["height"] > 9:
                        raise ValueError("item crosses an inventory page boundary")
                    for offset in range(rule["height"]):
                        position = (row["owner"], cell + offset * 5)
                        if position in occupied:
                            raise ValueError("inventory items overlap")
                        occupied.add(position)
            live[row["vnum"]] += row["count"]
    if seen != {key for key, event in history.items() if event["count"] > 0}:
        raise ValueError("audited stock is missing from the live snapshot")
    if minted != live + burned:
        raise ValueError("minted, held and destroyed quantities do not balance")
    return {
        "passed": True,
        "events": len(snapshot["audit"]),
        "live_stacks": len(seen),
        "pickups": len(pickup_debits),
        "minted": dict(minted),
        "burned": dict(burned),
        "held": dict(live),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "snapshot",
        type=Path,
        help="One consistent snapshot: inventory, drops, audit arrays (audit ordered by id).",
    )
    parser.add_argument(
        "--definitions", type=Path, default=Path("server/content/p0-warrior-dog/actions.v1.json")
    )
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    result = reconcile(
        json.loads(options.snapshot.read_text()), json.loads(options.definitions.read_text())
    )
    output = json.dumps(result, indent=2) + "\n"
    if options.report:
        options.report.write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
