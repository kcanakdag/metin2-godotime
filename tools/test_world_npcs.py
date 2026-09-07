#!/usr/bin/env python3
"""Exercise NPCs through the real Main/map scene in an isolated Godot project."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from build_npc_catalog import INSTALL_ROOT, validate_package
from test_actors import PROJECT, ROOT, run, sha256
from world_content import run_preview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    validate_package(INSTALL_ROOT)
    output = args.output.resolve()
    stage = output / "project"
    stage.mkdir(parents=True, exist_ok=False)
    sources = {}
    for relative in (
        "scripts",
        "scenes",
        "shaders",
        "spacetime_bindings",
        "addons/SpacetimeDB",
        "assets/imported",
    ):
        source = ROOT / "client" / relative
        shutil.copytree(source, stage / relative)
        if relative in ("scripts", "scenes", "shaders"):
            for path in source.rglob("*"):
                if path.is_file():
                    sources[str(path)] = sha256(path)
    (stage / "tests").mkdir()
    test = ROOT / "client/tests/world_npc_smoke.gd"
    shutil.copy2(test, stage / "tests" / test.name)
    sources[str(test)] = sha256(test)
    for path in INSTALL_ROOT.rglob("*"):
        if path.is_file() and path.suffix != ".import":
            sources[str(path)] = sha256(path)
    sources[str(Path(__file__).resolve())] = sha256(Path(__file__))
    (stage / "project.godot").write_text(
        PROJECT.replace(
            'config/name="MT2 Actor Test"',
            'config/name="MT2 NPC Runtime QA"\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="npc-runtime-qa"',
        )
    )
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(output / "data"),
        "XDG_CONFIG_HOME": str(output / "config"),
        "XDG_CACHE_HOME": str(output / "cache"),
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
            "6367",
            "--dap-port",
            "6368",
        ],
        env,
        output / "import.log",
    )
    command = [args.godot, "--path", str(stage), "--script", "res://tests/world_npc_smoke.gd"]
    command = (
        ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command]
        if args.native
        else [*command, "--headless"]
    )
    try:
        run_preview(command, env, output / "runtime.log", smoke=True)
    finally:
        for filename in ("world-npc.json", "world-npc.png"):
            found = list((output / "data").rglob(filename))
            if found:
                shutil.copy2(found[0], output / filename)
    report = json.loads((output / "world-npc.json").read_text())
    if any(sha256(Path(path)) != digest for path, digest in sources.items()):
        raise ValueError("NPC runtime sources changed during QA")
    report.update(sources=sources, native=args.native)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"World NPC runtime: {report['checks']} checks; {output}")


if __name__ == "__main__":
    main()
