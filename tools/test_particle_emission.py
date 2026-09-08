#!/usr/bin/env python3
"""Run the actual Godot emission component in an isolated, non-rendering fixture."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--scenario", choices=("emission", "motion", "render"), default="emission")
    args = parser.parse_args()
    output = args.output.resolve()
    scene = f"tests/particle_{args.scenario}_smoke.gd"
    files = ["scripts/actors/particle_emission.gd", scene]
    if args.scenario in ("motion", "render"):
        files += ["scripts/actors/particle_motion.gd", "scripts/actors/particle_simulation.gd"]
        files += ["scripts/actors/particle_style.gd"]
    if args.scenario == "render":
        files += ["scripts/actors/particle_effect.gd"]
    inputs = [ROOT / "client" / f for f in files] + [args.catalog.resolve(), Path(__file__)]
    frozen = {str(p.resolve()): digest(p) for p in inputs}
    output.mkdir(parents=True, exist_ok=False)
    (output / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Particle emission QA"\n'
    )
    for relative in files:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "client" / relative, destination)
    shutil.copy2(args.catalog, output / "effects.v1.json")
    if args.scenario == "render":
        catalog = json.loads(args.catalog.read_text())
        for texture in catalog["textures"].values():
            relative = Path(texture["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe particle texture path")
            source = args.catalog.resolve().parent / relative
            if digest(source) != texture["sha256"]:
                raise ValueError("Particle texture does not match catalog")
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if digest(destination) != texture["sha256"]:
                raise ValueError("Particle texture changed while copying")
    env = {**os.environ, "XDG_DATA_HOME": str(output / "userdata")}
    prefix = [args.godot, "--headless"]
    if args.scenario == "render":
        prefix = ["xvfb-run", "-a", args.godot, "--rendering-method", "gl_compatibility"]
    with (output / "run.log").open("w") as log:
        result = subprocess.run(
            [
                *prefix,
                "--path",
                str(output),
                "--script",
                "res://" + scene,
                "--",
                str(output / "effects.v1.json"),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
    log = (output / "run.log").read_text()
    rows = [json.loads(line) for line in log.splitlines() if line.startswith('{"checks":')]
    if result.returncode or "ERROR:" in log or len(rows) != 1 or rows[0]["failures"]:
        raise RuntimeError(f"Particle emission QA failed; inspect {output / 'run.log'}")
    if any(digest(Path(p)) != expected for p, expected in frozen.items()):
        raise RuntimeError("Particle emission QA inputs changed during the run")
    report = {
        **rows[0],
        "scenario": args.scenario,
        "inputs": frozen,
        "engine_log_sha256": digest(output / "run.log"),
        "rendering_verified": args.scenario == "render",
        "server_integration_verified": False,
        "captures": {p.name: digest(p) for p in sorted(output.glob("effect-*.png"))},
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"checks": report["checks"], "failures": report["failures"]}))


if __name__ == "__main__":
    main()
