#!/usr/bin/env python3
"""Exercise installed target effects in an isolated headless Godot project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "client/assets/imported/content/p2-target-effects"
PROJECT = """config_version=5
[application]
config/name="MT2 Target Effect Test"
[rendering]
renderer/rendering_method="gl_compatibility"
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], log: Path) -> str:
    result = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    log.write_text(result.stdout)
    if result.returncode or "SCRIPT ERROR:" in result.stdout or "\nERROR:" in result.stdout:
        raise SystemExit(f"Godot target-effect check failed; see {log}\n{result.stdout[-5000:]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--output", type=Path, default=ROOT / ".local/p2-target/effects/smoke")
    options = parser.parse_args()
    options.output = options.output.resolve()
    options.output.mkdir(parents=True, exist_ok=True)
    report_path = options.output / "report.json"
    report_path.write_text(json.dumps({"passed": False, "status": "started"}, indent=2) + "\n")
    if not (PROFILE / "runtime-catalog.v1.json").is_file():
        raise SystemExit("Missing target-effect catalog; run import_target_effects.py --install.")
    with tempfile.TemporaryDirectory(prefix="project-", dir=options.output) as scratch:
        stage = Path(scratch)
        (stage / "scripts/content").mkdir(parents=True)
        (stage / "scripts/actors").mkdir(parents=True)
        (stage / "tests").mkdir()
        shutil.copy2(
            ROOT / "client/scripts/content/target_effect_catalog.gd",
            stage / "scripts/content/target_effect_catalog.gd",
        )
        shutil.copy2(
            ROOT / "client/scripts/actors/target_effect.gd",
            stage / "scripts/actors/target_effect.gd",
        )
        shutil.copy2(
            ROOT / "client/tests/target_effect_smoke.gd", stage / "tests/target_effect_smoke.gd"
        )
        shutil.copytree(PROFILE, stage / "assets/imported/content/p2-target-effects")
        (stage / "project.godot").write_text(PROJECT)
        staged_catalog = stage / "assets/imported/content/p2-target-effects/runtime-catalog.v1.json"
        tested_files = {
            "catalog": sha256(staged_catalog),
            "catalog_loader": sha256(stage / "scripts/content/target_effect_catalog.gd"),
            "effect_node": sha256(stage / "scripts/actors/target_effect.gd"),
            "smoke": sha256(stage / "tests/target_effect_smoke.gd"),
        }
        environment = {
            **os.environ,
            "XDG_DATA_HOME": str(stage / ".data"),
            "XDG_CONFIG_HOME": str(stage / ".config"),
            "XDG_CACHE_HOME": str(stage / ".cache"),
        }
        run(
            [options.godot, "--headless", "--path", str(stage), "--import", "--quit-after", "2"],
            environment,
            options.output / "import.log",
        )
        output = run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--script",
                "res://tests/target_effect_smoke.gd",
            ],
            environment,
            options.output / "runtime.log",
        )
        match = re.search(r"TARGET_EFFECT_SMOKE PASS (\d+) checks", output)
        if not match:
            raise SystemExit("Godot target-effect smoke did not report completion.")
        report = {
            "passed": True,
            "checks": int(match.group(1)),
            "catalog_content_hash": json.loads(staged_catalog.read_text())["content_hash"],
            "tested_sha256": tested_files,
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Verified {match.group(1)} Godot target-effect checks; evidence: {options.output}")


if __name__ == "__main__":
    main()
