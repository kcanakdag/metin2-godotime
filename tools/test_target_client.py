#!/usr/bin/env python3
"""Exercise target UI, content gating, and world picking in an isolated Godot project."""

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
CLIENT = ROOT / "client"
PROJECT = """config_version=5
[application]
config/name="MT2 Target Client Test"
[display]
window/size/viewport_width=1280
window/size/viewport_height=800
[rendering]
renderer/rendering_method="gl_compatibility"
"""
SMOKES = {
    "content_gate": ("main_content_gate_smoke.gd", "MAIN_CONTENT_GATE_SMOKE"),
    "panel": ("classic_target_smoke.gd", "CLASSIC_TARGET_SMOKE"),
    "picker": ("world_picker_smoke.gd", "WORLD_PICKER_SMOKE"),
    "probe": ("export_probe_smoke.gd", "EXPORT_PROBE_SMOKE"),
}
TEST_SUPPORT = ("export_probe.gd",)


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
        raise SystemExit(f"Godot target-client check failed; see {log}\n{result.stdout[-5000:]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--output", type=Path, default=ROOT / ".local/p2-target/client-smoke")
    options = parser.parse_args()
    options.output = options.output.resolve()
    options.output.mkdir(parents=True, exist_ok=True)
    report_path = options.output / "report.json"
    report_path.write_text(json.dumps({"passed": False, "status": "started"}, indent=2) + "\n")
    actor_profile = CLIENT / "assets/imported/content/p0-warrior-dog"
    ui_profile = CLIENT / "assets/imported/ui"
    if not (actor_profile / "manifest.v1.json").is_file():
        raise SystemExit("Missing P1 actor profile; run the content import first.")
    if not (ui_profile / "manifest.json").is_file():
        raise SystemExit("Missing original UI fixture; run make import-ui first.")
    with tempfile.TemporaryDirectory(prefix="project-", dir=options.output) as scratch:
        stage = Path(scratch)
        shutil.copytree(CLIENT / "scripts", stage / "scripts")
        shutil.copytree(CLIENT / "addons/SpacetimeDB", stage / "addons/SpacetimeDB")
        shutil.copytree(CLIENT / "spacetime_bindings", stage / "spacetime_bindings")
        shutil.copytree(actor_profile, stage / "assets/imported/content/p0-warrior-dog")
        shutil.copytree(ui_profile, stage / "assets/imported/ui")
        (stage / "tests").mkdir()
        for script, _marker in SMOKES.values():
            shutil.copy2(CLIENT / "tests" / script, stage / "tests" / script)
        for script in TEST_SUPPORT:
            shutil.copy2(CLIENT / "tests" / script, stage / "tests" / script)
        (stage / "project.godot").write_text(PROJECT)
        tested_files = {
            "main": sha256(stage / "scripts/main.gd"),
            "actor_catalog": sha256(stage / "scripts/content/actor_catalog.gd"),
            "pve_actor": sha256(stage / "scripts/actors/pve_actor.gd"),
            "game_connection": sha256(stage / "scripts/net/game_connection.gd"),
            "dev_hud": sha256(stage / "scripts/ui/dev_hud.gd"),
            "classic_target": sha256(stage / "scripts/ui/classic_target.gd"),
            "world_picker": sha256(stage / "scripts/world/world_picker.gd"),
            "actor_profile_manifest": sha256(
                stage / "assets/imported/content/p0-warrior-dog/manifest.v1.json"
            ),
            "ui_manifest": sha256(stage / "assets/imported/ui/manifest.json"),
        }
        for name, (script, _marker) in SMOKES.items():
            tested_files[name + "_smoke"] = sha256(stage / "tests" / script)
        for script in TEST_SUPPORT:
            tested_files[Path(script).stem] = sha256(stage / "tests" / script)
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
        checks: dict[str, int] = {}
        for name, (script, marker) in SMOKES.items():
            output = run(
                [
                    options.godot,
                    "--headless",
                    "--path",
                    str(stage),
                    "--script",
                    "res://tests/" + script,
                ],
                environment,
                options.output / f"{name}.log",
            )
            match = re.search(rf"{marker} PASS (\d+) checks", output)
            if not match:
                raise SystemExit(f"Godot {name} smoke did not report completion.")
            checks[name] = int(match.group(1))
        report_path.write_text(
            json.dumps({"passed": True, "checks": checks, "tested_sha256": tested_files}, indent=2)
            + "\n"
        )
        print(f"Verified isolated target client checks {checks}; evidence: {options.output}")


if __name__ == "__main__":
    main()
