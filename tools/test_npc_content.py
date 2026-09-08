#!/usr/bin/env python3
"""Import and inspect converted NPCs in a separate Godot project."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from test_actors import PROJECT, ROOT, run, sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    content, output = args.content.resolve(), args.output.resolve()
    manifest = json.loads((content / "normalized.v1.json").read_text())
    conversion = json.loads((content / "blender-report.json").read_text())
    receipt = json.loads((content / "conversion-receipt.json").read_text())
    if (
        receipt["status"] != "converted"
        or receipt["report_sha256"] != sha256(content / "blender-report.json")
        or receipt["content_hash"] != manifest["content_hash"]
        or receipt["inputs"][str(content / "normalized.v1.json")]
        != sha256(content / "normalized.v1.json")
    ):
        raise ValueError("NPC conversion receipt or normalized artifact changed")
    frozen_probe = {
        str(ROOT / "tools" / name): sha256(ROOT / "tools" / name)
        for name in ("test_npc_content.py", "npc_content_probe.gd")
    }
    if conversion["status"] != "converted" or not 1 <= len(manifest["actors"]) <= 128:
        raise ValueError("NPC gallery requires successfully converted actors")
    for artifact in conversion["artifacts"]:
        if sha256(content / "generated" / artifact["relative_path"]) != artifact["sha256"]:
            raise ValueError("Converted NPC artifact hash differs from its report")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="npc-probe-", dir=output) as scratch:
        stage = Path(scratch)
        shutil.copy2(content / "normalized.v1.json", stage / "normalized.v1.json")
        shutil.copytree(content / "generated", stage / "generated")
        shutil.copy2(ROOT / "tools/npc_content_probe.gd", stage / "probe.gd")
        (stage / "project.godot").write_text(
            PROJECT.replace(
                'config/name="MT2 Actor Test"',
                'config/name="MT2 NPC Test"\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="npc-probe"',
            )
        )
        env = {
            **os.environ,
            "XDG_DATA_HOME": str(stage / ".data"),
            "XDG_CONFIG_HOME": str(stage / ".config"),
            "XDG_CACHE_HOME": str(stage / ".cache"),
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
        command = [args.godot, "--path", str(stage), "--script", "res://probe.gd"]
        command = (
            ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command]
            if args.native
            else [*command, "--headless"]
        )
        try:
            run(command, env, output / "probe.log")
        finally:
            for filename in (
                "npc-probe.json",
                *(f"npc-preview-{actor['vnum']}.png" for actor in manifest["actors"]),
            ):
                found = list((stage / ".data").rglob(filename))
                if found:
                    shutil.copy2(found[0], output / filename)
        report = json.loads((output / "npc-probe.json").read_text())
        if args.native and any(
            not (output / f"npc-preview-{actor['vnum']}.png").is_file()
            for actor in manifest["actors"]
        ):
            raise ValueError("NPC gallery did not capture every selected actor")
        if any(sha256(Path(path)) != digest for path, digest in frozen_probe.items()):
            raise ValueError("NPC probe source changed during QA")
        report.update(
            actors=len(manifest["actors"]),
            content_hash=manifest["content_hash"],
            native=args.native,
            sources={
                name: sha256(ROOT / "tools" / name)
                for name in (
                    "npc_content_probe.gd",
                    "test_npc_content.py",
                    "import_npc_content.py",
                    "npc_definitions.py",
                    "import_actor_content.py",
                )
            },
            artifacts=conversion["artifacts"],
        )
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified NPC content: {report['checks']} checks; {output}")


if __name__ == "__main__":
    main()
