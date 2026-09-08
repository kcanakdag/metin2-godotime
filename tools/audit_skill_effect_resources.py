#!/usr/bin/env python3
"""Check converter coverage for the distinct MSEs referenced by selected skills."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import canonical_bytes, source_archive
from content_formats import parse_legacy_script
from fetch_test_assets import METIN_COMMIT
from metin_effect_mesh import parse_mse
from metin_particles import parse_particle_mse
from mixed_effects import parse_mixed_effect


def inspect_effect(text: str, virtual: str) -> dict:
    root = parse_legacy_script(text)
    kinds = [group.name for group in root.groups]
    result = {"layers": kinds, "status": "unsupported", "reason": ""}
    try:
        if set(kinds) == {"Particle"}:
            definition = parse_particle_mse(text, virtual)
            result.update(kind="particles", particle_systems=len(definition["systems"]))
        elif set(kinds) == {"Particle", "Mesh"}:
            definition = parse_mixed_effect(text, virtual)
            result.update(kind="mixed", particle_systems=len(definition["particles"]["systems"]))
        elif set(kinds) == {"Mesh"}:
            parse_mse(text, blend_pairs={(3, 2), (3, 8), (5, 2), (5, 6)})
            result.update(kind="meshes", particle_systems=0)
        else:
            raise ValueError("Unsupported or empty layer combination")
        result["status"] = "parsed-not-converted"
    except ValueError as error:
        result["reason"] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    raw = args.inventory.read_bytes()
    inventory = json.loads(raw)
    if (
        inventory.get("schema") != "mt2spacetime.skill-motion-effect-inventory"
        or inventory.get("version") != 1
        or inventory.get("source_revision") != METIN_COMMIT
    ):
        parser.error("Expected pinned skill effect inventory")
    if args.output.exists():
        parser.error("Output already exists")
    archive = source_archive(args.offline)
    effects = {}
    for virtual, links in inventory["effect_references"].items():
        row = {"references": links}
        try:
            path = archive.resolve(virtual)
            source = archive.get(path).read_bytes()
            row.update(source_path=path, source_sha256=hashlib.sha256(source).hexdigest())
            row.update(inspect_effect(source.decode(), virtual))
        except (FileNotFoundError, ValueError, UnicodeDecodeError) as error:
            row.update(status="unavailable-or-invalid", reason=str(error))
        effects[virtual] = row
    if args.inventory.read_bytes() != raw:
        raise ValueError("Inventory changed during audit")
    result = {
        "schema": "mt2spacetime.skill-effect-resource-audit",
        "version": 1,
        "source_revision": METIN_COMMIT,
        "inventory_sha256": hashlib.sha256(raw).hexdigest(),
        "effects": effects,
    }
    with args.output.open("xb") as output:
        output.write(canonical_bytes(result) + b"\n")
    counts = {}
    for effect in effects.values():
        counts[effect["status"]] = counts.get(effect["status"], 0) + 1
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
