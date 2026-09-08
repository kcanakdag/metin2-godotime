#!/usr/bin/env python3
"""Compile converted wildlife into a source-linked candidate gameplay catalog."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import ROOT
from mob_gameplay import compile_catalog, validate_actor_reports
from mob_presentation import compile_presentation
from mob_server_registry import compile_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, required=True, help="Converted wildlife directory")
    parser.add_argument("--output", type=Path, required=True, help="New candidate output directory")
    args = parser.parse_args()
    content = args.content.resolve()
    files = [
        content / "normalized.v1.json",
        content / "blender-report.json",
        content / "conversion-receipt.json",
    ]
    files.extend(
        ROOT / "tools" / name
        for name in (
            "mob_gameplay.py",
            "mob_projectiles.py",
            "mob_presentation.py",
            "mob_server_registry.py",
            "build_mob_catalog.py",
            "content_compile.py",
            "content_formats.py",
        )
    )
    frozen = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    normalized = json.loads(files[0].read_text())
    report = json.loads(files[1].read_text())
    conversion = json.loads(files[2].read_text())
    normalized_hashes = [
        h for p, h in conversion["inputs"].items() if Path(p).name == "normalized.v1.json"
    ]
    if (
        report.get("status") != "converted"
        or conversion.get("status") != "converted"
        or conversion["report_sha256"] != frozen[str(files[1])]
        or normalized_hashes != [frozen[str(files[0])]]
        or conversion["content_hash"] != normalized["content_hash"]
    ):
        raise ValueError("Wildlife assets have not been converted")
    catalog = compile_catalog(normalized)
    artifacts = report["artifacts"]
    validate_actor_reports(normalized["actors"], artifacts)
    expected = {a["output"] for a in normalized["actors"]}
    if (
        len(artifacts) != len(normalized["actors"])
        or {a["relative_path"] for a in artifacts} != expected
    ):
        raise ValueError("Conversion report does not cover exact actor models")
    for artifact in artifacts:
        path = (content / "generated" / artifact["relative_path"]).resolve()
        if not path.is_relative_to(content / "generated"):
            raise ValueError("Converted model path escapes package")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            raise ValueError("Converted model differs from Blender report")
        frozen[str(path)] = digest
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in frozen.items()):
        raise ValueError("Mob catalog inputs changed during compilation")
    registry_source = compile_registry(catalog)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    target = output / "gameplay.v1.json"
    target.write_text(json.dumps(catalog, indent=2) + "\n")
    presentation = output / "presentation.v1.json"
    presentation.write_text(
        json.dumps(compile_presentation(normalized, report, catalog["content_hash"]), indent=2)
        + "\n"
    )
    registry = output / "combat-registry.rs"
    registry.write_text(registry_source)
    receipt = {
        "combat_registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
        "status": "candidate-not-installed",
        "inputs": frozen,
        "presentation_sha256": hashlib.sha256(presentation.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "content_hash": catalog["content_hash"],
        "mob_count": len(catalog["mobs"]),
        "attack_variant_count": sum(len(m["attacks"]) for m in catalog["mobs"]),
        "unimplemented_runtime_requirements": catalog["unimplemented_runtime_requirements"],
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != "inputs"}))


if __name__ == "__main__":
    main()
