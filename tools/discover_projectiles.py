#!/usr/bin/env python3
"""Discover the bounded flight-definition set linked by a candidate mob catalog."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import ROOT, canonical_bytes, source_archive
from fetch_test_assets import METIN_COMMIT
from fly_definitions import parse_flight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    inputs = [
        args.catalog,
        *(
            ROOT / "tools" / n
            for n in (
                "discover_projectiles.py",
                "fly_definitions.py",
                "content_formats.py",
                "metin_archive.py",
                "content_compile.py",
            )
        ),
    ]
    frozen = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    catalog = json.loads(args.catalog.read_text())
    payload = {k: v for k, v in catalog.items() if k != "content_hash"}
    if (
        catalog.get("schema") != "mt2spacetime.mob-gameplay-candidate"
        or catalog.get("version") != 1
        or hashlib.sha256(canonical_bytes(payload)).hexdigest() != catalog.get("content_hash")
    ):
        raise ValueError("Expected an intact candidate mob catalog")
    paths = sorted(
        {
            launch["fly_definition"]
            for mob in catalog["mobs"]
            for attack in mob["attacks"]
            for launch in attack["projectile_launches"]
        }
    )
    if not 1 <= len(paths) <= 128:
        raise ValueError("Select a bounded nonempty set of flight definitions")
    archive = source_archive(args.offline)
    records = []
    for path in paths:
        resolved = archive.resolve(path)
        source = archive.get(resolved)
        record = parse_flight(source.read_text(), path)
        record["source_path"] = resolved
        record["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record["resolved_effect_dependencies"] = {
            p: archive.resolve(p) for p in record["effect_dependencies"]
        }
        records.append(record)
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in frozen.items()):
        raise ValueError("Projectile discovery inputs changed")
    result = {
        "schema": "mt2spacetime.projectile-source-inventory",
        "version": 1,
        "source_revision": METIN_COMMIT,
        "source_rule_references": [
            "src/GameLib/FlyingData.cpp:CFlyingData::LoadScriptFile",
            "src/GameLib/FlyTrace.cpp:CFlyTrace::UpdateNewPosition",
        ],
        "mob_catalog_hash": catalog["content_hash"],
        "inputs": frozen,
        "flight_definitions": records,
        "runtime_status": "inventory-not-installed",
    }
    result["content_hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "inventory.v1.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "definitions": len(records),
                "attachments": sum(len(r["attachments"]) for r in records),
                "effects": len({p for r in records for p in r["effect_dependencies"]}),
                "source_issues": sum(len(r["source_issues"]) for r in records),
            }
        )
    )


if __name__ == "__main__":
    main()
