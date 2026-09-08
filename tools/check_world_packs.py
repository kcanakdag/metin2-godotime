#!/usr/bin/env python3
"""Audit every streamed chunk using a fresh Godot loader with only its two required packs."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from export_client import ROOT, run


def check_world_packs(godot, world, output, env):
    world = Path(world).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((world / "manifest.json").read_text())
    results = []
    with tempfile.TemporaryDirectory(prefix="world-check-", dir=output) as temporary:
        project = Path(temporary)
        audit_env = dict(env)
        for variable in ["XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"]:
            folder = project / variable.lower()
            folder.mkdir()
            audit_env[variable] = str(folder)
        (project / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="World Pack Audit"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        )
        helper = project / "scripts/world/stream_resource_uids.gd"
        helper.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "client/scripts/world/stream_resource_uids.gd", helper)
        for chunk in sorted(manifest["chunks"]):
            stdout = run(
                [
                    godot,
                    "--headless",
                    "--path",
                    project,
                    "--script",
                    ROOT / "tools/check_world_packs.gd",
                    "--",
                    world,
                    chunk,
                    ROOT / "client/assets/imported/maps/metin2_map_a1/terrain",
                ],
                output / ("world-check-" + chunk + ".log"),
                audit_env,
            )
            if "invalid UID:" in stdout:
                raise ValueError(f"Unresolved streamed resource UID in chunk {chunk}")
            line = next(
                line for line in stdout.splitlines() if line.startswith("WORLD_PACK_CHECK ")
            )
            results.append(json.loads(line.removeprefix("WORLD_PACK_CHECK ")))
    report = {"chunks": len(results), "isolated_dependencies": True, "results": results}
    (output / "world-pack-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--world-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/world-pack-audit")
    args = parser.parse_args()
    print(json.dumps(check_world_packs(args.godot, args.world_dir, args.output, dict(os.environ))))


if __name__ == "__main__":
    main()
