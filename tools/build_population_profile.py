#!/usr/bin/env python3
"""Derive a bounded mob asset-selection profile from an audited original population."""

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from content_compile import ROOT, canonical_bytes


def build_profile(population, base):
    unhashed = {k: v for k, v in population.items() if k != "content_hash"}
    if (
        population.get("schema") != "mt2spacetime.original-mob-population"
        or population.get("version") != 1
        or hashlib.sha256(canonical_bytes(unhashed)).hexdigest() != population.get("content_hash")
        or population["source_revision"] != base["source"]["server_reference"]["revision"]
    ):
        raise ValueError("Expected matching hash-verified population and base profile")
    rows = population["required_definitions"]
    expected = population["required_mob_vnums"]
    if (
        not 1 <= len(rows) <= 128
        or len(set(expected)) != len(rows)
        or sorted(r["vnum"] for r in rows) != sorted(expected)
    ):
        raise ValueError("Population definition closure is incomplete or duplicated")
    selected = {m["vnum"]: m for m in base["mobs"]}
    if len(selected) != len(base["mobs"]):
        raise ValueError("Base profile contains duplicate definitions")
    mobs = []
    for row in sorted(rows, key=lambda r: r["vnum"]):
        vnum, folder = row["vnum"], row["source_folder"]
        if (
            type(vnum) is not int
            or vnum <= 0
            or row["type"] != "MONSTER"
            or not re.fullmatch(r"[a-z0-9_]+", folder)
        ):
            raise ValueError("Unsupported required monster identity or folder")
        if vnum in selected:
            mobs.append(copy.deepcopy(selected[vnum]))
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", row["name"].lower()).strip("-")
        if not slug:
            raise ValueError("Required monster has no usable source name")
        mobs.append(
            {
                "id": f"actor.mob.{slug}-{vnum}",
                "vnum": vnum,
                "source_root": f"ymir work/monster/{folder}",
            }
        )
    if len({m["id"] for m in mobs}) != len(mobs):
        raise ValueError("Derived profile has conflicting actor identities")
    return {
        "schema_version": 1,
        "profile_id": population["map"] + "-population",
        "source": copy.deepcopy(base["source"]),
        "population_source": {"map": population["map"], "content_hash": population["content_hash"]},
        "mobs": mobs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument(
        "--base-profile", type=Path, default=ROOT / "content/profiles/yongan-wildlife.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_profile(
        json.loads(args.population.read_text()), json.loads(args.base_profile.read_text())
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(f"Selected {len(result['mobs'])} required mob definitions; no assets installed")


if __name__ == "__main__":
    main()
