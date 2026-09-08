#!/usr/bin/env python3
"""Exercise actual actor effect-event playback in an isolated headless Godot project."""

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
    parser.add_argument("--godot", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", choices=("actor", "mesh_clock"), default="actor")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    files = ["scripts/actors/actor_presentation.gd", "tests/motion_effect_playback_smoke.gd"]
    if args.scenario == "mesh_clock":
        files = ["scripts/actors/mesh_frame_clock.gd", "tests/mesh_frame_clock_smoke.gd"]
    inputs = {str(ROOT / "client" / f): digest(ROOT / "client" / f) for f in files}
    inputs[str(Path(__file__).resolve())] = digest(Path(__file__))
    (output / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Effect playback QA"\n'
    )
    for relative in files:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "client" / relative, destination)
    run = subprocess.run(
        [args.godot, "--headless", "--path", str(output), "--script", "res://" + files[1]],
        env={**os.environ, "XDG_DATA_HOME": str(output / "userdata")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    log = run.stdout + run.stderr
    (output / "run.log").write_text(log)
    rows = [json.loads(line) for line in log.splitlines() if line.startswith('{"checks":')]
    if run.returncode or "ERROR:" in log or len(rows) != 1 or rows[0]["failures"]:
        raise RuntimeError(f"Effect playback failed: {output / 'run.log'}")
    if any(digest(Path(path)) != value for path, value in inputs.items()):
        raise RuntimeError("Playback test inputs changed during execution")
    report = {
        **rows[0],
        "scenario": args.scenario,
        "inputs": inputs,
        "rendering_verified": False,
        "server_integration_verified": False,
        "engine_log_sha256": digest(output / "run.log"),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(rows[0]))


if __name__ == "__main__":
    main()
