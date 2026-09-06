#!/usr/bin/env python3
"""Exercise the real Godot HUD in an isolated project without a server or editor bridge."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = """config_version=5
[application]
config/name="MT2 UI Test"
[display]
window/size/viewport_width=1280
window/size/viewport_height=800
[rendering]
renderer/rendering_method="gl_compatibility"
"""


def run(command: list[str], environment: dict[str, str], log: Path) -> str:
    result = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    log.write_text(result.stdout)
    if result.returncode or "SCRIPT ERROR:" in result.stdout or "\nERROR:" in result.stdout:
        raise SystemExit(f"Godot UI check failed; see {log}\n{result.stdout[-3500:]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--native", action="store_true", help="Render under Xvfb and save a PNG.")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/classic-ui")
    options = parser.parse_args()
    options.output = options.output.resolve()
    options.output.mkdir(parents=True, exist_ok=True)
    assets = ROOT / "client/assets/imported/ui"
    if not (assets / "manifest.json").is_file():
        raise SystemExit("Missing original UI fixture; run make import-ui first.")
    if options.native and not shutil.which("xvfb-run"):
        raise SystemExit("Native UI rendering requires xvfb-run.")
    with tempfile.TemporaryDirectory(prefix="project-", dir=options.output) as scratch:
        stage = Path(scratch)
        for relative in ("scripts/ui", "assets/imported/ui"):
            shutil.copytree(ROOT / "client" / relative, stage / relative)
        (stage / "scripts/world").mkdir(parents=True)
        (stage / "tests").mkdir()
        for relative in ("scripts/world/classic_minimap.gd", "tests/classic_ui_smoke.gd"):
            shutil.copy2(ROOT / "client" / relative, stage / relative)
        (stage / "project.godot").write_text(PROJECT)
        environment = {
            **os.environ,
            "XDG_DATA_HOME": str(stage / ".data"),
            "XDG_CONFIG_HOME": str(stage / ".config"),
        }
        run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--editor",
                "--import",
                "--quit",
                "--lsp-port",
                "6135",
                "--dap-port",
                "6136",
                "--debug-server",
                "tcp://127.0.0.1:6137",
            ],
            environment,
            options.output / "import.log",
        )
        command = [
            options.godot,
            "--path",
            str(stage),
            "--script",
            "res://tests/classic_ui_smoke.gd",
        ]
        if options.native:
            command = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command]
        else:
            command.insert(1, "--headless")
        output = run(command, environment, options.output / "runtime.log")
        match = re.search(r"CLASSIC_UI_SMOKE PASS (\d+) checks", output)
        if not match:
            raise SystemExit("Godot UI smoke did not report completion.")
        evidence = {"passed": True, "checks": int(match.group(1)), "native": options.native}
        if options.native:
            screenshot = stage / ".data/godot/app_userdata/MT2 UI Test/classic-ui.png"
            if not screenshot.is_file():
                raise SystemExit("Native UI smoke did not produce its screenshot.")
            shutil.copy2(screenshot, options.output / "classic-ui.png")
            evidence["screenshot"] = "classic-ui.png"
        (options.output / "report.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(f"Verified {match.group(1)} Godot UI checks; evidence: {options.output}")


if __name__ == "__main__":
    main()
