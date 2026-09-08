#!/usr/bin/env python3
"""Verify and install only the selected converted ground-item models and runtime catalog."""

import argparse
import json
from pathlib import Path

from content_compile import canonical_bytes
from install_mob_content import checked_file, digest, install, read_json, relative

PREFIX = "res://assets/imported/ground_items/"


def collect(content):
    document = read_json(content / "normalized.v1.json")
    content_hash = document.pop("content_hash")
    if digest(canonical_bytes(document)) != content_hash or document.get("schema_version") != 1:
        raise ValueError("Ground-item source manifest mismatch")
    definitions = document["ground_items"]
    if not isinstance(definitions, list) or not 1 <= len(definitions) <= 256:
        raise ValueError("Invalid ground-item selection")
    report = read_json(content / "blender-report.json")
    if report.get("status") != "converted" or report.get("profile_id") != document["profile_id"]:
        raise ValueError("Ground-item conversion did not complete")
    artifacts = {entry["id"]: entry for entry in report["artifacts"]}
    models, files = {}, {}
    if len(artifacts) != len(report["artifacts"]) or len(artifacts) != len(document["items"]):
        raise ValueError("Duplicate or missing ground model")
    for item in document["items"]:
        identity = item["id"]
        if identity in models or identity not in artifacts:
            raise ValueError("Duplicate or missing ground model identity")
        artifact = artifacts[identity]
        name = relative(item["output"])
        if (
            not name.startswith("models/")
            or not name.endswith(".glb")
            or artifact["relative_path"] != name
        ):
            raise ValueError("Invalid converted ground-model path")
        data = checked_file(content / "generated", name, artifact["sha256"])
        if (
            artifact.get("type") != "item"
            or len(data) != artifact["bytes"]
            or artifact.get("textured_mesh_count", 0) < 1
        ):
            raise ValueError("Invalid converted ground-model artifact")
        if name in files:
            raise ValueError("Duplicate ground-model destination")
        files[name] = data
        models[identity] = {"path": PREFIX + name, "sha256": digest(data)}
    vnums = set()
    for row in definitions:
        vnum = row["vnum"]
        if (
            type(vnum) is not int
            or not 0 < vnum <= 0xFFFFFFFF
            or vnum in vnums
            or row["model_id"] not in models
        ):
            raise ValueError("Invalid ground-item model reference")
        vnums.add(vnum)
    catalog = {
        "schema_version": 1,
        "content_hash": content_hash,
        "models": models,
        "items": definitions,
    }
    files["catalog.v1.json"] = (json.dumps(catalog, indent=2, sort_keys=True) + "\n").encode()
    return {"ground_items": files}, content_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    args = parser.parse_args()
    packages, content_hash = collect(args.content.resolve())
    print(
        json.dumps(
            install(
                args.client.resolve(), packages, content_hash, identity_field="ground_content_hash"
            )
        )
    )


if __name__ == "__main__":
    main()
