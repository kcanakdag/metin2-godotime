#!/usr/bin/env python3
"""Exercise generated actor resources and presentation in an isolated Godot project."""

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
ACTOR_PROFILE = ROOT / "client/assets/imported/content/p0-warrior-dog"
TARGET_EFFECT_PROFILE = ROOT / "client/assets/imported/content/p2-target-effects"
PROJECT = """config_version=5
[application]
config/name="MT2 Actor Test"
[display]
window/size/viewport_width=1280
window/size/viewport_height=800
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
        raise SystemExit(f"Godot actor check failed; see {log}\n{result.stdout[-5000:]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--native", action="store_true", help="Render under Xvfb and save a PNG.")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/actors")
    options = parser.parse_args()
    options.output = options.output.resolve()
    options.output.mkdir(parents=True, exist_ok=True)
    report_path = options.output / "report.json"
    report_path.write_text(json.dumps({"passed": False, "status": "started"}, indent=2) + "\n")
    if not (ACTOR_PROFILE / "manifest.v1.json").is_file():
        raise SystemExit("Missing P1 actor profile; run the content import first.")
    target_effect_catalog = TARGET_EFFECT_PROFILE / "runtime-catalog.v1.json"
    if not target_effect_catalog.is_file():
        raise SystemExit(
            "Missing target-effect catalog; run import_target_effects.py --install first."
        )
    if options.native and not shutil.which("xvfb-run"):
        raise SystemExit("Native actor rendering requires xvfb-run.")
    with tempfile.TemporaryDirectory(prefix="project-", dir=options.output) as scratch:
        stage = Path(scratch)
        shutil.copytree(ROOT / "client/scripts/actors", stage / "scripts/actors")
        shutil.copytree(ROOT / "client/scripts/content", stage / "scripts/content")
        shutil.copytree(ACTOR_PROFILE, stage / "assets/imported/content/p0-warrior-dog")
        shutil.copytree(TARGET_EFFECT_PROFILE, stage / "assets/imported/content/p2-target-effects")
        (stage / "tests").mkdir()
        shutil.copy2(ROOT / "client/tests/actor_smoke.gd", stage / "tests/actor_smoke.gd")
        (stage / "project.godot").write_text(PROJECT)
        staged_target_catalog = (
            stage / "assets/imported/content/p2-target-effects/runtime-catalog.v1.json"
        )
        tested_files = {
            "actor_profile_manifest": sha256(
                stage / "assets/imported/content/p0-warrior-dog/manifest.v1.json"
            ),
            "actor_catalog": sha256(stage / "scripts/content/actor_catalog.gd"),
            "actor_node": sha256(stage / "scripts/actors/pve_actor.gd"),
            "target_effect_catalog": sha256(stage / "scripts/content/target_effect_catalog.gd"),
            "target_effect_node": sha256(stage / "scripts/actors/target_effect.gd"),
            "target_effect_runtime_catalog": sha256(staged_target_catalog),
            "smoke": sha256(stage / "tests/actor_smoke.gd"),
        }
        environment = {
            **os.environ,
            "XDG_DATA_HOME": str(stage / ".data"),
            "XDG_CONFIG_HOME": str(stage / ".config"),
            "XDG_CACHE_HOME": str(stage / ".cache"),
        }
        run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--import",
                "--quit-after",
                "2",
            ],
            environment,
            options.output / "import.log",
        )
        command = [options.godot, "--path", str(stage), "--script", "res://tests/actor_smoke.gd"]
        if options.native:
            command = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command]
        else:
            command.insert(1, "--headless")
        output = run(command, environment, options.output / "runtime.log")
        match = re.search(r"ACTOR_SMOKE PASS (\d+) checks", output)
        if not match:
            raise SystemExit("Godot actor smoke did not report completion.")
        report: dict[str, object] = {
            "passed": True,
            "checks": int(match.group(1)),
            "native": options.native,
            "profile": "p0-warrior-dog",
            "target_effect_content_hash": json.loads(staged_target_catalog.read_text())[
                "content_hash"
            ],
            "tested_sha256": tested_files,
        }
        capture_directory = stage / ".data/godot/app_userdata/MT2 Actor Test"
        if options.native:
            screenshots = sorted(capture_directory.glob("actors-*.png"))
            if len(screenshots) < 6:
                raise SystemExit("Native actor smoke did not produce its staged screenshots.")
            for screenshot in screenshots:
                shutil.copy2(screenshot, options.output / screenshot.name)
            report["screenshots"] = [screenshot.name for screenshot in screenshots]
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Verified {match.group(1)} Godot actor checks; evidence: {options.output}")


if __name__ == "__main__":
    main()
