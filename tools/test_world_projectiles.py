#!/usr/bin/env python3
"""Exercise real Main projectile routing with converted mobs and controlled rows."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from install_mob_content import collect, install
from test_actors import PROJECT, ROOT, run, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--mobs", type=Path, required=True)
    parser.add_argument("--projectiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    stage = output / "project"
    stage.mkdir(parents=True, exist_ok=False)
    frozen = {
        str(path.resolve()): sha256(path)
        for path in (Path(__file__), ROOT / "tools/install_mob_content.py")
    }
    for relative in (
        "scripts",
        "scenes",
        "shaders",
        "addons/SpacetimeDB",
        "spacetime_bindings",
        "assets/imported/skills",
        "assets/imported/characters",
        "assets/imported/ui",
        "assets/imported/content/p0-warrior-dog",
        "assets/imported/content/p2-target-effects",
        "assets/imported/authored/training-dummy",
    ):
        source = ROOT / "client" / relative
        shutil.copytree(source, stage / relative)
        for path in source.rglob("*"):
            if path.is_file() and path.suffix != ".import":
                frozen[str(path)] = sha256(path)
    subprocess.run(
        [
            os.sys.executable,
            str(ROOT / "tools/build_mob_catalog.py"),
            "--content",
            str(args.mobs.resolve()),
            "--output",
            str(stage / "candidate"),
        ],
        check=True,
    )
    packages, gameplay_hash = collect(args.mobs, stage / "candidate", args.projectiles)
    install(stage, packages, gameplay_hash)
    for package in (args.mobs.resolve(), args.projectiles.resolve()):
        for path in package.rglob("*"):
            if path.is_file():
                frozen[str(path)] = sha256(path)
    (stage / "tests").mkdir()
    test = ROOT / "client/tests/world_projectile_smoke.gd"
    shutil.copy2(test, stage / "tests" / test.name)
    frozen[str(test)] = sha256(test)
    (stage / "project.godot").write_text(PROJECT)
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(output / "data"),
        "XDG_CONFIG_HOME": str(output / "config"),
    }
    run(
        [
            args.godot,
            "--headless",
            "--path",
            str(stage),
            "--editor",
            "--import",
            "--quit",
            "--lsp-port",
            "6381",
            "--dap-port",
            "6382",
        ],
        env,
        output / "import.log",
    )
    install(stage, packages, gameplay_hash)  # Godot may expand import metadata.
    run(
        [
            "xvfb-run",
            "-a",
            args.godot,
            "--path",
            str(stage),
            "--script",
            "res://tests/world_projectile_smoke.gd",
        ],
        env,
        output / "runtime.log",
    )
    if any(sha256(Path(p)) != expected for p, expected in frozen.items()):
        raise ValueError("World projectile fixture inputs changed")
    report = json.loads((stage / "report.json").read_text())
    report.update(
        inputs=frozen,
        live_subscriptions=False,
        captures={p.name: sha256(p) for p in stage.glob("projectile-*.png")},
    )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"checks": report["checks"], "failures": report["failures"]}))


if __name__ == "__main__":
    main()
