#!/usr/bin/env python3
"""Test real Godot networking with isolated identities and no editor side effects."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from generate_bindings import run_godot

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--database", default="mt2-dev-world")
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument(
        "--script",
        choices=["multiplayer_smoke", "combat_smoke", "inventory_smoke"],
        default="multiplayer_smoke",
    )
    parser.add_argument("--report", type=Path, default=ROOT / ".local/multiplayer-report.json")
    options = parser.parse_args()
    options.report = options.report.resolve()
    options.report.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / ".local").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="multiplayer-", dir=ROOT / ".local") as scratch:
        stage = Path(scratch)
        for directory in ("addons/SpacetimeDB", "spacetime_bindings", "tests"):
            shutil.copytree(ROOT / "client" / directory, stage / directory)
        (stage / "scripts/net").mkdir(parents=True)
        for filename in ("game_connection.gd", "quest_rows.gd"):
            shutil.copy2(ROOT / "client/scripts/net" / filename, stage / "scripts/net" / filename)
        (stage / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="MT2 Multiplayer Tests"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        )
        run_godot(options.godot, stage, "--editor", "--import", "--quit")
        environment = os.environ.copy()
        environment["XDG_DATA_HOME"] = str(stage / ".data")
        environment["XDG_CONFIG_HOME"] = str(stage / ".config")
        result = subprocess.run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--script",
                "res://tests/" + options.script + ".gd",
                "--",
                "--server",
                options.server,
                "--database",
                options.database,
                "--report",
                str(options.report),
                "--profile-prefix",
                f"smoke-{uuid.uuid4().hex[:10]}",
            ],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=100,
            check=False,
        )
        log_path = options.report.with_suffix(".log")
        log_path.write_text(result.stdout)
        print(result.stdout, end="")
        if (
            result.returncode
            or "SCRIPT ERROR:" in result.stdout
            or "\nERROR:" in result.stdout
            or "MT2_MULTIPLAYER_SMOKE PASS" not in result.stdout
        ):
            raise SystemExit(result.returncode or 1)
        report = json.loads(options.report.read_text())
        if not report["passed"]:
            raise SystemExit(1)
        print(f"Verified {len(report['checks'])} multiplayer checks; report: {options.report}")


if __name__ == "__main__":
    main()
