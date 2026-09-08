#!/usr/bin/env python3
"""Build and audit the authored practice actor, optionally installing runtime files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "content/profiles/training-dummy.json"


def audit(output: Path, profile: dict) -> dict:
    model = output / "training-dummy.glb"
    data = model.read_bytes()
    if len(data) < 20 or len(data) > 2_000_000:
        raise ValueError("Training model exceeds the package budget")
    magic, version, length, chunk_length, chunk_type = struct.unpack_from("<5I", data)
    if (magic, version, length, chunk_type) != (0x46546C67, 2, len(data), 0x4E4F534A):
        raise ValueError("Invalid training model GLB")
    doc = json.loads(data[20 : 20 + chunk_length])
    clips = [a["name"] for a in doc.get("animations", [])]
    if sorted(clips) != ["damage", "dead", "wait"]:
        raise ValueError("Training model must contain idle, impact and death clips")
    if any("uri" in item for key in ("images", "buffers") for item in doc.get(key, [])):
        raise ValueError("Training GLB must be self contained")
    manifest = json.loads((output / "manifest.v1.json").read_text())
    digest = hashlib.sha256(data).hexdigest()
    definition_hash = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest["definition_hash"] != definition_hash:
        raise ValueError("Training actor was built from a different profile")
    artifact = manifest["artifacts"][0]
    if artifact["sha256"] != digest or artifact["id"] != profile["id"]:
        raise ValueError("Training model and manifest differ")
    bounds = artifact["bounds_m"]
    if len(bounds) != 2 or any(
        len(point) != 3 or any(not math.isfinite(v) or abs(v) > 4 for v in point)
        for point in bounds
    ):
        raise ValueError("Training model bounds are invalid")
    if any(bounds[0][axis] >= bounds[1][axis] for axis in range(3)):
        raise ValueError("Training model bounds are empty")
    if abs(bounds[1][1] - profile["height_m"]) > 0.1 or abs(bounds[0][1]) > 0.01:
        raise ValueError("Training model must stand at the origin with configured height")
    return {
        "passed": True,
        "model_sha256": digest,
        "definition_hash": definition_hash,
        "bytes": len(data),
        "clips": clips,
        "bounds_m": bounds,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    parser.add_argument("--profile", type=Path, default=PROFILE)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/training-dummy")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "build.log").open("w") as log:
        subprocess.run(
            [
                args.blender,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "tools/blender_training_dummy.py"),
                "--",
                "--profile",
                str(args.profile.resolve()),
                "--output",
                str(output),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=True,
        )
    report = audit(output, json.loads(args.profile.read_text()))
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.install:
        destination = ROOT / "client/assets/imported/authored/training-dummy"
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("training-dummy.glb", "manifest.v1.json"):
            shutil.copy2(output / name, destination / name)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
