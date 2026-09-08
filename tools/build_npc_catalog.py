#!/usr/bin/env python3
"""Compile selected converted stationary NPCs into a public, map-bound catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from content_compile import extract_actor_texture_pngs
from PIL import Image
from test_actors import ROOT, sha256
from world_content import inspector, validate

INSTALL_ROOT = ROOT / "client/assets/imported/npcs"
RESOURCE_ROOT = "res://assets/imported/npcs/"
CATALOG = "catalog.v1.json"


def artifact_path(directory: Path, relative: str) -> Path:
    if not re.fullmatch(r"actors/[a-z0-9][a-z0-9-]*\.glb", relative):
        raise ValueError("NPC artifact must be a converted actors/*.glb resource")
    result = (directory / relative).resolve()
    if directory.resolve() not in result.parents:
        raise ValueError("NPC artifact escapes its build directory")
    return result


def converted(directory: Path) -> tuple[dict, dict]:
    normalized = json.loads((directory / "normalized.v1.json").read_text())
    report = json.loads((directory / "blender-report.json").read_text())
    receipt = json.loads((directory / "conversion-receipt.json").read_text())
    if (
        receipt["status"] != "converted"
        or report["status"] != "converted"
        or receipt["report_sha256"] != sha256(directory / "blender-report.json")
        or receipt["content_hash"] != normalized["content_hash"]
        or receipt["inputs"][str(directory / "normalized.v1.json")]
        != sha256(directory / "normalized.v1.json")
    ):
        raise ValueError("NPC conversion receipt is incomplete or changed")
    artifacts = {}
    for row in report["artifacts"]:
        path = artifact_path(directory / "generated", row["relative_path"])
        if row["id"] in artifacts or sha256(path) != row["sha256"]:
            raise ValueError("NPC conversion contains duplicate or changed artifacts")
        artifacts[row["id"]] = row
    return normalized, artifacts


def heading(spawn: dict) -> float:
    direction = spawn["source_direction"]
    if type(direction) is not int or not 0 <= direction <= 8:
        raise ValueError("Invalid original NPC direction")
    # Source zero is random, not north. Pick an octant deterministically for this
    # immutable presentation; every client/reconnect sees the same orientation.
    if direction == 0:
        return (int(hashlib.sha256(spawn["id"].encode()).hexdigest()[:8], 16) % 8) * math.pi / 4
    # Original GetDeltaByDegree is (sin(angle), cos(angle)); our model's
    # forward vector is (-sin(yaw), -cos(yaw)) in positive map X/Z.
    return (math.pi + (direction - 1) * math.pi / 4) % math.tau


def public_actor(actor: dict, artifact: dict) -> dict:
    if actor["kind"] != "npc" or artifact["forward"] != "-Z":
        raise ValueError("Expected a converted stationary NPC facing -Z")
    idle = [
        {"clip": motion["godot_name"], "weight": motion["weight"]}
        for mode in actor["modes"]
        if mode["id"] == "general"
        for motion in mode["motions"]
        if motion["action"] == "wait"
    ]
    return {
        "id": actor["id"],
        "vnum": actor["vnum"],
        "name": actor["name"],
        "model": RESOURCE_ROOT + artifact["relative_path"],
        "sha256": artifact["sha256"],
        "label_height": artifact["bounds_m"][1][1] + 0.2,
        "idle": idle,
        "presentation": actor.get("presentation", "animated"),
    }


def exact(row: dict, fields: str) -> None:
    if not isinstance(row, dict) or set(row) != set(fields.split()):
        raise ValueError("Unexpected NPC public catalog fields")


def finite(value: object, minimum: float, maximum: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def validate_public(document: dict) -> None:
    """Used before installation and export; no source paths/receipts may ship."""
    exact(document, "schema version actors maps")
    if document["schema"] != "mt2spacetime.static-npcs" or document["version"] not in (1, 2):
        raise ValueError("Unsupported NPC catalog")
    actors, maps = document["actors"], document["maps"]
    if not isinstance(actors, list) or not 1 <= len(actors) <= 256:
        raise ValueError("Expected 1..256 NPC definitions")
    ids, models, vnums = set(), set(), set()
    for actor in actors:
        exact(
            actor,
            "id vnum name model sha256 label_height idle"
            + (" presentation" if document["version"] == 2 else ""),
        )
        if (
            not re.fullmatch(r"actor\.npc\.[a-z0-9-]+", actor["id"])
            or actor["id"] in ids
            or actor["vnum"] in vnums
            or type(actor["vnum"]) is not int
            or not 1 <= actor["vnum"] <= 0xFFFFFFFF
            or not isinstance(actor["name"], str)
            or not 1 <= len(actor["name"]) <= 80
            or not finite(actor["label_height"], 0.1, 100)
            or not re.fullmatch(r"[a-f0-9]{64}", actor["sha256"])
            or not actor["model"].startswith(RESOURCE_ROOT)
            or actor["model"] in models
        ):
            raise ValueError("Invalid or duplicate NPC definition")
        artifact_path(INSTALL_ROOT, actor["model"].removeprefix(RESOURCE_ROOT))
        ids.add(actor["id"])
        vnums.add(actor["vnum"])
        models.add(actor["model"])
        presentation = actor.get("presentation", "animated")
        if presentation not in ("animated", "static"):
            raise ValueError("Unsupported NPC presentation")
        if presentation == "static":
            if actor["idle"] != []:
                raise ValueError("Static NPCs must not declare idle animations")
            continue
        if not isinstance(actor["idle"], list) or not 1 <= len(actor["idle"]) <= 16:
            raise ValueError("Missing NPC idle variants")
        clips = set()
        for motion in actor["idle"]:
            exact(motion, "clip weight")
            if (
                not re.fullmatch(r"[a-z0-9_]+", motion["clip"])
                or motion["clip"] in clips
                or type(motion["weight"]) is not int
                or not 1 <= motion["weight"] <= 100
            ):
                raise ValueError("Invalid NPC idle variant")
            clips.add(motion["clip"])
        if sum(m["weight"] for m in actor["idle"]) != 100:
            raise ValueError("NPC idle weights must sum to 100")
    if not isinstance(maps, list) or not 1 <= len(maps) <= 32:
        raise ValueError("Expected 1..32 NPC map layouts")
    map_ids, spawn_ids = set(), set()
    for world in maps:
        exact(world, "id content_hash placements")
        if (
            not re.fullmatch(r"[a-z0-9_]+", world["id"])
            or world["id"] in map_ids
            or not re.fullmatch(r"[a-f0-9]{64}", world["content_hash"])
            or not isinstance(world["placements"], list)
            or not 1 <= len(world["placements"]) <= 4096
        ):
            raise ValueError("Invalid NPC map layout")
        map_ids.add(world["id"])
        for spawn in world["placements"]:
            exact(spawn, "id actor_id position yaw")
            if (
                not re.fullmatch(r"spawn\.[a-z0-9.-]+", spawn["id"])
                or spawn["id"] in spawn_ids
                or spawn["actor_id"] not in ids
                or not isinstance(spawn["position"], list)
                or len(spawn["position"]) != 3
                or not all(finite(v, -1e6, 1e6) for v in spawn["position"])
                or not finite(spawn["yaw"], -math.tau, math.tau)
            ):
                raise ValueError("Invalid or duplicate NPC placement")
            spawn_ids.add(spawn["id"])


def validate_package(directory: Path) -> dict:
    document = json.loads((directory / CATALOG).read_text())
    validate_public(document)
    allowed = {CATALOG}
    for actor in document["actors"]:
        relative = actor["model"].removeprefix(RESOURCE_ROOT)
        if sha256(artifact_path(directory, relative)) != actor["sha256"]:
            raise ValueError("Installed NPC model differs from its catalog")
        allowed.update((relative, relative + ".import"))
        allowed.update(validate_extracted_textures(directory, relative))
    extras = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if extras - allowed:
        raise ValueError("NPC runtime directory contains undeclared files")
    return document


def validate_extracted_textures(directory: Path, relative: str) -> set[str]:
    """Godot may re-encode extracted PNGs; compare pixels to the hash-checked GLB."""
    model = directory / relative
    with tempfile.TemporaryDirectory(prefix="npc-textures-") as scratch:
        root = Path(scratch)
        target = root / relative
        target.parent.mkdir(parents=True)
        shutil.copy2(model, target)
        paths = extract_actor_texture_pngs(
            root,
            {
                "artifacts": [
                    {"type": "actor", "relative_path": relative},
                ]
            },
        )
        allowed = set()
        for source in paths:
            name = source.relative_to(root).as_posix()
            destination = directory / name
            if destination.exists():
                with Image.open(source) as expected, Image.open(destination) as actual:
                    if (
                        expected.size != actual.size
                        or expected.convert("RGBA").tobytes() != actual.convert("RGBA").tobytes()
                    ):
                        raise ValueError("NPC extracted texture differs from its converted GLB")
            allowed.update((name, name + ".import"))
        return allowed


def build(contents: list[Path], profiles: list[Path], output: Path) -> dict:
    actors, spawns, files, inputs = [], [], {}, {}
    if output.exists() or output == INSTALL_ROOT or INSTALL_ROOT in output.parents:
        raise ValueError("Choose a new build output outside the installed NPC directory")
    for relative in (
        "tools/build_npc_catalog.py",
        "tools/world_content.py",
        "tools/content_compile.py",
        "tools/actor_texture_import.py",
        "server/build_population.rs",
        "server/examples/world_content.rs",
        "server/src/content.rs",
        "server/src/movement.rs",
    ):
        path = ROOT / relative
        inputs[str(path)] = sha256(path)
    for directory in contents:
        manifest, artifacts = converted(directory)
        if any(
            spawn.get("position_policy") == "server-random-area" for spawn in manifest["spawns"]
        ):
            raise ValueError(
                "Area NPCs require server-owned sampled placements; cannot install them as fixed points"
            )
        for name in ("conversion-receipt.json", "normalized.v1.json", "blender-report.json"):
            inputs[str(directory / name)] = sha256(directory / name)
        for actor in manifest["actors"]:
            artifact = artifacts[actor["id"]]
            actors.append(public_actor(actor, artifact))
            relative = artifact["relative_path"]
            if relative in files:
                raise ValueError("NPC conversion outputs overlap")
            files[relative] = artifact_path(directory / "generated", relative)
        spawns.extend(manifest["spawns"])
    maps = []
    covered = set()
    for path in profiles:
        inputs[str(path)] = sha256(path)
        profile = json.loads(path.read_text())
        selected = [row for row in spawns if row["map_id"] == profile["map_id"]]
        if not selected:
            raise ValueError("Population profile has no selected NPC placements")
        report = validate(
            profile,
            inspector(profile["map_id"]),
            [{"id": s["id"], "x": s["x_m"], "z": s["z_m"]} for s in selected],
            point_policy="static_npc",
        )
        placements = []
        for spawn, point in zip(selected, report["points"], strict=True):
            placements.append(
                {
                    "id": spawn["id"],
                    "actor_id": spawn["actor_id"],
                    "position": [point["x"], point["y"], point["z"]],
                    "yaw": heading(spawn),
                }
            )
            covered.add(spawn["map_id"])
        maps.append(
            {
                "id": report["map_id"],
                "content_hash": report["map_content_hash"],
                "placements": sorted(placements, key=lambda s: s["id"]),
            }
        )
    if covered != {s["map_id"] for s in spawns}:
        raise ValueError("Every NPC map needs a population profile for terrain validation")
    document = {
        "schema": "mt2spacetime.static-npcs",
        "version": 2,
        "actors": sorted(actors, key=lambda a: a["id"]),
        "maps": sorted(maps, key=lambda m: m["id"]),
    }
    validate_public(document)
    output.mkdir(parents=True, exist_ok=False)
    runtime = output / "runtime"
    for relative, source in files.items():
        destination = runtime / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (runtime / CATALOG).write_text(json.dumps(document, indent=2) + "\n")
    extract_actor_texture_pngs(
        runtime, {"artifacts": [{"type": "actor", "relative_path": relative} for relative in files]}
    )
    validate_package(runtime)
    if any(sha256(Path(path)) != digest for path, digest in inputs.items()):
        raise ValueError("NPC build inputs changed during compilation")
    receipt = {
        "status": "compiled",
        "inputs": inputs,
        "catalog_sha256": sha256(runtime / CATALOG),
        "heading_policy": "source fixed octants; source random octants seeded by spawn ID",
    }
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, action="append", required=True)
    parser.add_argument("--population", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    build([p.resolve() for p in args.content], [p.resolve() for p in args.population], output)
    if args.install:
        if INSTALL_ROOT.exists():
            INSTALL_ROOT.rename(output / "previous-installed")
        try:
            shutil.copytree(output / "runtime", INSTALL_ROOT)
        except OSError:
            shutil.rmtree(INSTALL_ROOT, ignore_errors=True)
            if (output / "previous-installed").exists():
                (output / "previous-installed").rename(INSTALL_ROOT)
            raise
    print(f"Compiled NPC catalog: {output}")


if __name__ == "__main__":
    main()
