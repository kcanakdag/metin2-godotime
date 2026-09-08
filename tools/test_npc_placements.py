#!/usr/bin/env python3
"""Qualify original NPC area sampling on real terrain without modifying a game database."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from build_npc_catalog import converted
from content_compile import ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=32)
    args = parser.parse_args()
    if not 2 <= args.seeds <= 1000:
        parser.error("--seeds must be in 2..1000")
    manifest, _ = converted(args.content.resolve())
    areas = manifest["spawns"]
    if not areas or any(a.get("position_policy") != "server-random-area" for a in areas):
        parser.error("Select a converted area-NPC package")
    files = [
        args.content.resolve() / "normalized.v1.json",
        ROOT / "server/src/npc_placement.rs",
        ROOT / "server/src/content.rs",
        ROOT / "server/src/movement.rs",
        ROOT / "server/examples/npc_placement.rs",
        ROOT / "server/content/yongan.bin",
        ROOT / "server/content/yongan.sha256",
        ROOT / "server/Cargo.lock",
        Path(__file__).resolve(),
    ]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    command = [
        "cargo",
        "build",
        "--manifest-path",
        str(ROOT / "server/Cargo.toml"),
        "--target-dir",
        str(ROOT / "server/target"),
        "--locked",
        "--offline",
        "--features",
        "yongan",
        "--example",
        "npc_placement",
    ]
    with (output / "build.log").open("w") as log:
        subprocess.run(
            command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180
        )
    binary = ROOT / "server/target/debug/examples/npc_placement"
    hashes[str(binary)] = hashlib.sha256(binary.read_bytes()).hexdigest()
    expected = {a["id"]: a for a in areas}
    samples = []
    checks = 0
    for seed in range(args.seeds):
        result = subprocess.run(
            [str(binary)],
            input=json.dumps({"areas": areas, "preview_seed": seed}),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        (output / f"seed-{seed}.log").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"NPC placement failed for seed {seed}; see its log")
        data = json.loads(result.stdout)
        if data["purpose"] != "offline-preview-not-live-placement" or data["preview_seed"] != seed:
            raise ValueError("Unexpected placement qualification result")
        rows = data["placements"]
        if len(rows) != len(expected) or {r["id"] for r in rows} != expected.keys():
            raise ValueError("NPC placement identities differ from input")
        for row in rows:
            lo_x, lo_z, hi_x, hi_z = expected[row["id"]]["bounds_cm"]
            if (
                type(row["x_cm"]) is not int
                or not lo_x <= row["x_cm"] <= hi_x
                or type(row["z_cm"]) is not int
                or not lo_z <= row["z_cm"] <= hi_z
                or not math.isfinite(row["height_m"])
                or type(row["heading_degrees"]) is not int
                or not 0 <= row["heading_degrees"] <= 360
            ):
                raise ValueError("Sampled NPC position/heading violates original bounds")
            yaw = (math.pi + math.radians(row["heading_degrees"] % 360)) % math.tau
            delta = row["yaw"] - yaw
            if not math.isfinite(delta) or abs(math.atan2(math.sin(delta), math.cos(delta))) > 1e-6:
                raise ValueError("NPC heading differs from original-to-Godot conversion")
            checks += 1
        samples.append(data)
    for name, digest in hashes.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError("NPC placement inputs changed during qualification")
    report = {
        "passed": True,
        "purpose": "offline-sampler-qualification",
        "seeds": args.seeds,
        "areas": len(areas),
        "placements_checked": checks,
        "samples": samples,
        "sha256": hashes,
        "limitations": "No live database, persistent placement, or client subscription proof",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {checks} sampled placements on Yongan terrain; {output}")


if __name__ == "__main__":
    main()
