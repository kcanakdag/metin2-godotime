#!/usr/bin/env python3
"""Exercise the real Godot HUD in an isolated project without a server or editor bridge."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
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


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--native", action="store_true", help="Render under Xvfb and save a PNG.")
    parser.add_argument("--suite", choices=["ui", "map", "chat", "intro", "status"], default="ui")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/classic-ui")
    options = parser.parse_args()
    script = f"classic_{options.suite}_smoke.gd"
    image_name = f"classic-{options.suite}.png"
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
        shutil.copytree(ROOT / "client/scripts/content", stage / "scripts/content")
        item_manifest = Path("assets/imported/content/p0-warrior-dog/manifest.v1.json")
        (stage / item_manifest).parent.mkdir(parents=True)
        shutil.copy2(ROOT / "client" / item_manifest, stage / item_manifest)
        if options.suite == "intro":
            shutil.copytree(
                ROOT / "client/assets/imported/characters", stage / "assets/imported/characters"
            )
            content = ROOT / "client/assets/imported/content/p0-warrior-dog"
            if not (content / "manifest.v1.json").is_file():
                raise SystemExit("Missing P1 actor profile; run the content import first.")
            shutil.copytree(
                content, stage / "assets/imported/content/p0-warrior-dog", dirs_exist_ok=True
            )
            shutil.copytree(ROOT / "client/scripts/actors", stage / "scripts/actors")
        (stage / "scripts/world").mkdir(parents=True)
        (stage / "tests").mkdir()
        for relative in ("scripts/world/classic_minimap.gd", "tests/" + script):
            shutil.copy2(ROOT / "client" / relative, stage / relative)
        (stage / "project.godot").write_text(PROJECT)
        environment = {
            **os.environ,
            "XDG_DATA_HOME": str(stage / ".data"),
            "XDG_CONFIG_HOME": str(stage / ".config"),
        }
        lsp_port, dap_port, debug_port = (free_port() for _ in range(3))
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
                str(lsp_port),
                "--dap-port",
                str(dap_port),
                "--debug-server",
                f"tcp://127.0.0.1:{debug_port}",
            ],
            environment,
            options.output / "import.log",
        )
        command = [
            options.godot,
            "--path",
            str(stage),
            "--script",
            "res://tests/" + script,
        ]
        if options.native:
            command = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command]
        else:
            command.insert(1, "--headless")
        try:
            output = run(command, environment, options.output / "runtime.log")
        finally:
            if options.native:
                capture_dir = stage / ".data/godot/app_userdata/MT2 UI Test"
                for capture in capture_dir.glob(f"classic-{options.suite}*.png"):
                    shutil.copy2(capture, options.output / capture.name)
        match = re.search(rf"CLASSIC_{options.suite.upper()}_SMOKE PASS (\d+) checks", output)
        if not match:
            raise SystemExit("Godot UI smoke did not report completion.")
        evidence = {
            "passed": True,
            "checks": int(match.group(1)),
            "native": options.native,
            "suite": options.suite,
        }
        if options.native:
            screenshot = stage / ".data/godot/app_userdata/MT2 UI Test" / image_name
            if not screenshot.is_file():
                raise SystemExit("Native UI smoke did not produce its screenshot.")
            shutil.copy2(screenshot, options.output / image_name)
            evidence["screenshot"] = image_name
            if options.suite == "intro":
                for extra in screenshot.parent.glob("classic-intro-*.png"):
                    shutil.copy2(extra, options.output / extra.name)
        (options.output / "report.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(f"Verified {match.group(1)} Godot UI checks; evidence: {options.output}")


if __name__ == "__main__":
    main()
