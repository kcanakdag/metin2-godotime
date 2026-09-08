#!/usr/bin/env python3
"""Freeze original map foliage inputs and placement policy without executing a DLL."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from fetch_test_assets import METIN_COMMIT, ROOT
from metin_archive import Archive, write_json
from metin_map_data import placements, property_data


def inspect_spt(data: bytes) -> dict:
    """Recognize the selected source envelope only; this does not decode geometry."""
    if not 24 <= len(data) <= 16_000_000:
        raise ValueError("SPT size outside the supported inspection budget")
    token, length = struct.unpack_from("<II", data)
    if token != 1000 or length != 12 or data[8:20] != b"__IdvSpt_02_":
        raise ValueError("Unsupported SPT envelope")
    if struct.unpack_from("<I", data, 20)[0] != 1002:
        raise ValueError("Unexpected SPT header terminator")
    return {
        "signature": "__IdvSpt_02_",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "geometry_decoded": False,
    }


def tree_placement(chunk: str, row: dict) -> dict:
    # The pinned CArea tree path only passes position, height bias and CRC.
    # Building rotations and property size overrides must not leak into trees.
    return {
        "id": f"{chunk}:{row['id']}",
        "chunk": chunk,
        "property_crc": row["crc"],
        "position_m": row["position"],
        "source_position_cm": row["source_position"],
        "height_bias_cm": row["height_bias_cm"],
        "source_rotation_ypr_deg": row["rotation_ypr_deg"],
        "apply_source_rotation": False,
    }


def prepare(archive: Archive, manifest: dict) -> dict:
    if manifest.get("commit") != METIN_COMMIT or manifest.get("version") != 1:
        raise ValueError("Map manifest must use the pinned original source revision")
    name = manifest["map"]
    settings = [p for p in archive.entries if p.endswith(f"/{name}/setting.txt")]
    if len(settings) != 1:
        raise ValueError("Map must resolve to exactly one original source folder")
    folder = settings[0].rsplit("/", 1)[0]
    archive.get(settings[0])
    rows = []
    for path in sorted(archive.entries):
        if path.startswith(folder + "/") and path.endswith("/areadata.txt"):
            chunk = path.split("/")[-2]
            rows.extend((chunk, r) for r in placements(archive.get(path).read_text()))
    if not rows:
        raise ValueError("Map has no source placements")
    definitions = {}
    for crc in sorted({r["crc"] for _, r in rows}):
        # Verify each selected property against its pinned Git blob, never trust
        # a cached manifest's kind, resolved asset path or transformed placement.
        source = manifest["properties"][crc]["source"]
        actual_crc, fields = property_data(archive.get(source).read_text(encoding="cp1252"))
        if actual_crc != crc:
            raise ValueError("Property source CRC does not match its placements")
        if fields["propertytype"] != "Tree":
            continue
        tree = archive.resolve(fields["treefile"])
        definitions[crc] = {
            "property_source": source,
            "fields": fields,
            "tree_source": tree,
            "input": inspect_spt(archive.get(tree).read_bytes()),
            "compute_seed": 1,
            "size_policy": "embedded-spt",
            "conversion_status": "pending",
        }
    selected = [tree_placement(c, r) for c, r in rows if r["crc"] in definitions]
    ids = [r["id"] for r in selected]
    if len(set(ids)) != len(ids):
        raise ValueError("Repeated tree placement identity")
    return {
        "schema": "mt2spacetime.foliage-inputs",
        "version": 1,
        "source_commit": METIN_COMMIT,
        "map": name,
        "definitions": definitions,
        "placements": selected,
        "source_files": archive.used,
        "runtime_execution": False,
        "geometry_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map-manifest",
        type=Path,
        default=ROOT / ".local/map-import/metin2_map_a1/manifest.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--online", action="store_true", help="Fetch missing pinned inputs")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be new; preserve previous receipts")
    archive = Archive(offline=not args.online)
    archive.inventory()
    report = prepare(archive, json.loads(args.map_manifest.read_text()))
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "definitions": len(report["definitions"]),
                "placements": len(report["placements"]),
                "geometry_ready": False,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
