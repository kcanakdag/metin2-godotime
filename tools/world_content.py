#!/usr/bin/env python3
"""Validate, author and preview map populations using the server's collision code."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

from test_actors import PROJECT, ROOT, run, sha256

DEFAULT_PROFILE = ROOT / "content/worlds/yongan.population.json"


def run_preview(command: list[str], environment: dict, log_path: Path, *, smoke: bool) -> None:
    # Own the group so an expired QA run also closes its Xvfb/Godot children.
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            status = process.wait(timeout=90 if smoke else None)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RuntimeError(f"World preview interrupted or timed out; see {log_path}") from None
    text = log_path.read_text()
    if status or "SCRIPT ERROR:" in text or "\nERROR:" in text:
        raise RuntimeError(f"World preview failed; see {log_path}\n{text[-2500:]}")


def inspector(map_id: str) -> Path:
    if map_id not in ("training", "metin2_map_a1"):
        raise ValueError(
            "This server currently has terrain adapters for training and metin2_map_a1"
        )
    command = [
        "cargo",
        "build",
        "--quiet",
        "--locked",
        "--manifest-path",
        str(ROOT / "server/Cargo.toml"),
        "--example",
        "world_content",
    ]
    if map_id == "metin2_map_a1":
        command.extend(["--features", "yongan"])
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("MT2_COMBAT_TEST_FIXTURE", "MT2_ITEM_TEST_FIXTURE", "MT2_POPULATION_PROFILE")
    }
    # A separate Cargo output tree avoids replacing a developer's selected build.
    target = ROOT / ".local/world-content/cargo"
    environment["CARGO_TARGET_DIR"] = str(target)
    subprocess.run(command, env=environment, check=True)
    return target / "debug/examples/world_content"


def validate(profile: dict, binary: Path, points: list[dict] | None = None) -> dict:
    result = subprocess.run(
        [str(binary)],
        input=json.dumps({"profile": profile, "points": points or []}),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip())
    report = json.loads(result.stdout)
    if not report["valid"]:
        failures = [row for row in report["spawns"] + report["points"] if not row["valid"]]
        raise ValueError("Blocked authored positions: " + json.dumps(failures))
    return report


def edit_profile(
    profile: dict, command: str, identity: int, x: float | None, z: float | None, vnum: int | None
) -> dict:
    draft = copy.deepcopy(profile)
    matches = [row for row in draft["placements"] if row["id"] == identity]
    if command in ("move", "remove") and len(matches) != 1:
        raise ValueError("Select exactly one existing spawn ID")
    if command == "add":
        if matches or x is None or z is None or vnum is None:
            raise ValueError("Add needs an unused ID, X/Z and definition vnum")
        draft["placements"].append(
            {"id": identity, "definition_vnum": vnum, "home_x": x, "home_z": z}
        )
    elif command == "move":
        if x is None or z is None:
            raise ValueError("Move needs X and Z in map-local meters")
        matches[0].update(home_x=x, home_z=z)
    else:
        draft["placements"].remove(matches[0])
    draft["revision"] += 1
    return draft


def preview(report: dict, output: Path, godot: str, *, npc: Path | None, smoke: bool) -> None:
    stage = output / "project"
    stage.mkdir(parents=True, exist_ok=False)
    for directory in ("scripts", "scenes", "shaders"):
        (stage / directory).mkdir()
    for name in ("map_preview.gd",):
        shutil.copy2(ROOT / "client/scripts" / name, stage / "scripts" / name)
    shutil.copy2(
        ROOT / "tools/world_population_preview.gd", stage / "scripts/population_preview.gd"
    )
    scene = (ROOT / "client/scenes/map_preview.tscn").read_text()
    (stage / "scenes/preview.tscn").write_text(
        scene.replace("scripts/map_preview.gd", "scripts/population_preview.gd")
    )
    for path in (ROOT / "client/shaders").glob("*.gdshader"):
        shutil.copy2(path, stage / "shaders" / path.name)
    map_id = report["map_id"]
    if map_id != "metin2_map_a1":
        raise ValueError("Rendered population preview currently requires an imported Yongan map")
    relative = Path("assets/imported/maps") / map_id
    shutil.copytree(ROOT / "client" / relative, stage / relative)
    actor_relative = Path("assets/imported/content/p0-warrior-dog")
    shutil.copytree(ROOT / "client" / actor_relative, stage / actor_relative)
    manifest = json.loads((ROOT / "client" / actor_relative / "manifest.v1.json").read_text())
    mobs = {actor["vnum"]: actor for actor in manifest["actors"] if actor["kind"] == "mob"}
    report["actors"] = {
        str(vnum): {
            "path": actor["model"]["path"],
            "name": actor["name"],
            "idle": next(
                motion["godot_name"]
                for mode in actor["modes"]
                for motion in mode["motions"]
                if motion["action"] == "wait"
            ),
        }
        for vnum, actor in mobs.items()
    }
    if npc:
        conversion = json.loads((npc / "blender-report.json").read_text())
        receipt = json.loads((npc / "conversion-receipt.json").read_text())
        if receipt["status"] != "converted" or receipt["report_sha256"] != sha256(
            npc / "blender-report.json"
        ):
            raise ValueError("NPC conversion receipt is incomplete or changed")
        normalized = json.loads((npc / "normalized.v1.json").read_text())
        for artifact in conversion["artifacts"]:
            if sha256(npc / "generated" / artifact["relative_path"]) != artifact["sha256"]:
                raise ValueError("NPC model differs from its conversion record")
        shutil.copytree(npc / "generated", stage / "npc")
        report["npc_actors"] = {
            actor["id"]: {
                "path": "res://npc/" + actor["output"],
                "name": actor["name"],
                "idle": next(
                    motion["godot_name"]
                    for mode in actor["modes"]
                    for motion in mode["motions"]
                    if motion["action"] == "wait"
                ),
            }
            for actor in normalized["actors"]
        }
    (stage / "world-content.json").write_text(json.dumps(report, indent=2) + "\n")
    (stage / "project.godot").write_text(
        PROJECT.replace(
            'config/name="MT2 Actor Test"',
            'config/name="MT2 World Content"\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="world-content"',
        )
    )
    environment = {
        **os.environ,
        "XDG_DATA_HOME": str(output / "data"),
        "XDG_CONFIG_HOME": str(output / "config"),
        "XDG_CACHE_HOME": str(output / "cache"),
    }
    run(
        [
            godot,
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
        environment,
        output / "import.log",
    )
    command = [godot, "--path", str(stage), "res://scenes/preview.tscn", "--", "--map", map_id]
    if smoke:
        command = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command, "--population-smoke"]
        run_preview(command, environment, output / "preview.log", smoke=True)
        for name in ("population-preview.png", "population-probe.json"):
            paths = list((output / "data").rglob(name))
            if paths:
                shutil.copy2(paths[0], output / name)
    else:
        run_preview(command, environment, output / "preview.log", smoke=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "add", "move", "remove", "preview"))
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--id", type=int)
    parser.add_argument("--x", type=float)
    parser.add_argument("--z", type=float)
    parser.add_argument("--vnum", type=int)
    parser.add_argument(
        "--npc", type=Path, help="Optional converted NPC profile for offline inspection"
    )
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    binary = inspector(profile["map_id"])
    validate(profile, binary)
    if args.command in ("add", "move", "remove"):
        profile = edit_profile(profile, args.command, args.id, args.x, args.z, args.vnum)
    points = []
    if args.npc:
        normalized = json.loads((args.npc / "normalized.v1.json").read_text())
        points = [
            {"id": row["id"], "x": row["x_m"], "z": row["z_m"]}
            for row in normalized["spawns"]
            if row["map_id"] == profile["map_id"]
        ]
    report = validate(profile, binary, points)
    if args.npc:
        for point in report["points"]:
            point["actor_id"] = next(
                row["actor_id"] for row in normalized["spawns"] if row["id"] == point["id"]
            )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "population.json").write_text(json.dumps(profile, indent=2) + "\n")
    report["inputs"] = {
        str(path): sha256(path)
        for path in (
            args.profile.resolve(),
            ROOT / "server/build_population.rs",
            ROOT / "server/src/content.rs",
            ROOT / "server/src/movement.rs",
            ROOT / "server/examples/world_content.rs",
        )
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.command == "preview":
        preview(report, output, args.godot, npc=args.npc, smoke=args.smoke)
    print(
        f"Validated {len(report['spawns'])} mob homes and {len(points)} inspection points: {output}"
    )


if __name__ == "__main__":
    main()
