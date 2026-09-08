#!/usr/bin/env python3
"""Discover selected original mob definitions without installing unsupported gameplay."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import ROOT, canonical_bytes, fetch_server_references, source_archive
from content_formats import parse_motion_list, parse_race_script
from fetch_test_assets import METIN_COMMIT
from mob_definitions import normalize, records
from mob_shapes import default_shape


def compile_profile(path, *, offline):
    profile = json.loads(path.read_text())
    if (
        type(profile.get("schema_version")) is not int
        or profile["schema_version"] != 1
        or profile["source"]["client_revision"] != METIN_COMMIT
    ):
        raise ValueError("Expected pinned monster profile")
    selected = profile["mobs"]
    if not 1 <= len(selected) <= 128:
        raise ValueError("Select 1–128 explicit monster definitions")
    references = fetch_server_references(profile, offline=offline)
    base = ROOT / "assets/source/content/server" / profile["source"]["server_reference"]["revision"]
    rows = records((base / "gamefiles/conf/mob_proto.txt").read_text(encoding="latin-1"))
    names = dict(
        line.split("\t", 1)
        for line in (base / "gamefiles/conf/mob_names_en.txt")
        .read_text(encoding="latin-1")
        .splitlines()
        if "\t" in line
    )
    archive = source_archive(offline)
    registrations = archive.get("bin/pack/root/npclist.txt")
    mapping = [line.split() for line in registrations.read_text(errors="replace").splitlines()]
    result, ids, vnums = [], set(), set()
    for selection in selected:
        actor, vnum = selection["id"], selection["vnum"]
        if type(vnum) is not int or vnum in vnums or actor in ids or vnum not in rows:
            raise ValueError("Unknown or duplicate selected monster identity")
        ids.add(actor)
        vnums.add(vnum)
        matches = [row for row in mapping if row and row[0] == str(vnum)]
        if len(matches) != 1 or len(matches[0]) != 2:
            raise ValueError("Monster must have exactly one client registration")
        definition = normalize(
            rows[vnum], actor_id=actor, name=names[str(vnum)], model_key=matches[0][1]
        )
        definition["source_row_sha256"] = hashlib.sha256(canonical_bytes(rows[vnum])).hexdigest()
        root = selection["source_root"]
        shape = archive.resolve(root + "/" + definition["model_key"] + ".msm")
        motions = archive.resolve(root + "/motlist.txt")
        race_text = archive.get(shape).read_text()
        race = parse_race_script(race_text)
        selected_shape = default_shape(race_text)
        definition["assets"] = {
            "race_script": shape,
            "model": archive.resolve(selected_shape["model"]),
            "default_shape": {
                "index": 0,
                "skin_remaps": [
                    {key: archive.resolve(value) for key, value in pair.items()}
                    for pair in selected_shape["skin_remaps"]
                ],
            },
            "motion_list": motions,
            "motions": parse_motion_list(archive.get(motions).read_text()),
            "source_collision": race["collision"],
        }
        result.append(definition)
    return {
        "schema": "mt2spacetime.mob-source-inventory",
        "version": 1,
        "profile_id": profile["profile_id"],
        "client_revision": METIN_COMMIT,
        "server_revision": profile["source"]["server_reference"]["revision"],
        "source_references": references,
        "client_sources": [
            {"path": name, **record} for name, record in sorted(archive.used.items())
        ],
        "registration_sha256": hashlib.sha256(registrations.read_bytes()).hexdigest(),
        "mobs": result,
        "runtime_status": "source-definitions-only; assets and shared gameplay integration required",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "content/profiles/yongan-wildlife.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    inputs = (
        args.profile.resolve(),
        Path(__file__).resolve(),
        ROOT / "tools/mob_definitions.py",
        ROOT / "tools/mob_shapes.py",
        ROOT / "tools/content_formats.py",
    )
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    document = compile_profile(args.profile, offline=args.offline)
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != hashes[str(p)] for p in inputs):
        raise ValueError("Mob discovery inputs changed during compilation")
    args.output.mkdir(parents=True, exist_ok=False)
    data = canonical_bytes(document)
    (args.output / "inventory.json").write_bytes(data)
    receipt = {
        "inventory_sha256": hashlib.sha256(data).hexdigest(),
        "mobs": len(document["mobs"]),
        "sources": hashes,
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"mobs": receipt["mobs"], "inventory_sha256": receipt["inventory_sha256"]}))


if __name__ == "__main__":
    main()
