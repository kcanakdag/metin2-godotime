#!/usr/bin/env python3
"""Audit original map populations from a pinned local source checkout, without installing spawns."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from content_compile import ROOT, canonical_bytes
from mob_definitions import records
from mob_gameplay import SERVER_REVISION
from mob_population import compile_population


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-checkout", type=Path, default=ROOT / ".cache/full-game-research/server/source"
    )
    parser.add_argument("--map", default="metin2_map_a1")
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "content/profiles/yongan-wildlife.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compiler_paths = [
        ROOT / "tools" / name
        for name in (
            "discover_mob_population.py",
            "mob_population.py",
            "mob_definitions.py",
            "mob_gameplay.py",
            "content_formats.py",
            "content_compile.py",
        )
    ]
    frozen = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in compiler_paths}
    if not args.map or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in args.map):
        raise ValueError("Invalid source map identifier")
    checkout = args.source_checkout.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != SERVER_REVISION:
        raise ValueError("Expected reviewed server revision")
    paths = [
        f"gamefiles/data/map/{args.map}/regen.txt",
        "gamefiles/data/group.txt",
        "gamefiles/data/group_group.txt",
        "src/game/src/regen.cpp",
        "src/game/src/mob_manager.cpp",
        "src/game/src/mob_manager.h",
        "src/game/src/char_manager.cpp",
        "src/game/src/char.cpp",
        "gamefiles/conf/mob_proto.txt",
        "gamefiles/conf/mob_names_en.txt",
    ]
    sources = {
        path: subprocess.check_output(["git", "-C", str(checkout), "show", f"{revision}:{path}"])
        for path in paths
    }
    profile_bytes = args.profile.read_bytes()
    profile = json.loads(profile_bytes)
    if profile["source"]["server_reference"]["revision"] != revision:
        raise ValueError("Selected profile and population source revisions differ")
    result = compile_population(
        *(sources[p].decode("latin-1") for p in paths[:3]),
        selected_vnums={m["vnum"] for m in profile["mobs"]},
    )
    proto = records(sources["gamefiles/conf/mob_proto.txt"].decode("latin-1"))
    names = records(sources["gamefiles/conf/mob_names_en.txt"].decode("latin-1"))
    definitions = []
    for vnum in result["required_mob_vnums"]:
        if vnum not in proto or vnum not in names:
            raise ValueError(f"Population references missing original mob {vnum}")
        definitions.append(
            {
                "vnum": vnum,
                "name": names[vnum]["LOCALE_NAME"],
                "type": proto[vnum]["TYPE"],
                "source_folder": proto[vnum]["FOLDER"],
            }
        )
    result["required_definitions"] = definitions
    result.update(
        schema="mt2spacetime.original-mob-population",
        version=1,
        map=args.map,
        source_revision=revision,
        runtime_status="inventory-not-installed",
        group_weight_policy="original-loader-unit-weight",
        source_hashes={p: hashlib.sha256(data).hexdigest() for p, data in sources.items()},
        profile_sha256=hashlib.sha256(profile_bytes).hexdigest(),
        compiler_hashes={Path(p).name: digest for p, digest in frozen.items()},
    )
    if args.profile.read_bytes() != profile_bytes or any(
        hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest for p, digest in frozen.items()
    ):
        raise ValueError("Population compiler inputs changed during discovery")
    result["content_hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "population.v1.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "entries": len(result["entries"]),
                "groups": len(result["groups"]),
                "selectors": len(result["group_selectors"]),
                "required_mobs": len(result["required_mob_vnums"]),
                "covered_entries": result["covered_entries"],
                "initial_member_upper_bound": result["initial_member_upper_bound"],
                "outside_selection": result["outside_selected_vnums"],
            }
        )
    )


if __name__ == "__main__":
    main()
