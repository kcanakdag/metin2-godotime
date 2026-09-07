#!/usr/bin/env python3
"""Install a verified, source-free character presentation catalog for Godot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from build_npc_catalog import converted, validate_extracted_textures
from character_definitions import registered_combo_chains
from content_compile import ROOT, _client_motion, canonical_bytes, extract_actor_texture_pngs

INSTALL_ROOT = ROOT / "client/assets/imported/characters"
RESOURCE_ROOT = "res://assets/imported/characters/"
BASE_WARRIOR = "actor.player.warrior-male"


def public_catalog(normalized: dict, artifacts: dict) -> dict:
    source = next(
        row
        for row in normalized["sources"]
        if row["path"] == "bin/pack/root/playersettingmodule.py"
    )
    settings = (ROOT / "assets/source/content" / source["revision"] / source["path"]).read_bytes()
    if hashlib.sha256(settings).hexdigest() != source["sha256"]:
        raise ValueError("Character combo registrations differ from the converted source pin")
    registrations = settings.decode("utf-8", errors="replace")
    actors, output_artifacts = [], []
    for actor in normalized["actors"]:
        artifact = artifacts[actor["id"]]
        if artifact["forward"] != "-Z" or artifact["default_hair"]["hair_index"] != 0:
            raise ValueError("Character conversion lacks canonical facing or default hair")
        if set(artifact["attachment_bones"]) != set(actor["attachment_bones"]):
            raise ValueError("Character weapon attachments differ from the source definition")
        path = RESOURCE_ROOT + artifact["relative_path"]
        output_artifacts.append(
            {
                "id": actor["id"],
                "type": "actor",
                "path": path,
                **{
                    key: artifact[key]
                    for key in (
                        "sha256",
                        "bytes",
                        "mesh_count",
                        "textured_mesh_count",
                        "vertices",
                        "triangles",
                        "bounds_m",
                        "bones",
                        "skeleton_signature",
                    )
                },
            }
        )
        modes = []
        for mode in actor["modes"]:
            modes.append(
                {
                    "id": mode["id"],
                    "required_item_vnums": {"onehand": [10], "fan": [7000]}.get(mode["id"], []),
                    "combo_chains": registered_combo_chains(
                        registrations, actor["model_key"].split("_")[0].capitalize(), mode["id"]
                    )
                    if mode["id"] in {"onehand", "fan"}
                    else [],
                    "motions": [_client_motion(motion, None) for motion in mode["motions"]],
                }
            )
        actors.append(
            {
                **{
                    key: actor[key]
                    for key in (
                        "id",
                        "kind",
                        "race_id",
                        "name",
                        "model_key",
                        "attachment_bones",
                        "motion_vector_space",
                    )
                },
                "model": {"artifact_id": actor["id"], "path": path},
                "skeleton_signature": artifact["skeleton_signature"],
                "default_hair_index": 0,
                "forward": "-Z",
                "modes": modes,
            }
        )
    return {
        "schema": "mt2spacetime.characters",
        "version": 1,
        "classes": normalized["classes"],
        "actors": actors,
        "artifacts": output_artifacts,
    }


def validate_catalog(document: dict) -> None:
    if (
        set(document) != {"schema", "version", "classes", "actors", "artifacts"}
        or document["schema"] != "mt2spacetime.characters"
        or type(document["version"]) is not int
        or document["version"] != 1
    ):
        raise ValueError("Invalid character catalog header")
    classes, actors, artifacts = document["classes"], document["actors"], document["artifacts"]
    if len(classes) != 4 or len(actors) != 8 or len(artifacts) != 8:
        raise ValueError("Classic catalog must join four classes and eight appearances")
    class_ids, ids, races, actor_ids = set(), set(), set(), {BASE_WARRIOR}
    for row in classes:
        if (
            set(row)
            != {"id", "class_id", "name", "initial_points", "variants", "starter_weapon_vnum"}
            or not re.fullmatch(r"[a-z][a-z0-9-]*", row["id"])
            or row["id"] in ids
            or type(row["class_id"]) is not int
            or row["class_id"] not in range(4)
            or row["class_id"] in class_ids
            or type(row["starter_weapon_vnum"]) is not int
            or not 0 < row["starter_weapon_vnum"] < 2**32
        ):
            raise ValueError("Invalid or duplicate character class")
        class_ids.add(row["class_id"])
        ids.add(row["id"])
        if not isinstance(row["name"], str) or not 1 <= len(row["name"]) <= 32:
            raise ValueError("Invalid class name")
        points = row["initial_points"]
        fields = "strength vitality dexterity intelligence base_hp base_sp hp_per_vitality sp_per_intelligence hp_gain_min hp_gain_max sp_gain_min sp_gain_max stamina stamina_per_vitality stamina_gain_min stamina_gain_max".split()
        if set(points) != set(fields) or any(
            type(v) is not int or not 0 < v < 10000 for v in points.values()
        ):
            raise ValueError("Invalid class progression points")
        if len(row["variants"]) != 2 or {variant["sex"] for variant in row["variants"]} != {0, 1}:
            raise ValueError("Class must include both original appearances")
        for variant in row["variants"]:
            if (
                set(variant) != {"sex", "race_id", "actor_id"}
                or type(variant["sex"]) is not int
                or type(variant["race_id"]) is not int
                or variant["race_id"] not in range(8)
                or variant["race_id"] in races
            ):
                raise ValueError("Invalid or duplicate original race")
            expected = f"actor.player.{row['id']}-{'male' if variant['sex'] == 0 else 'female'}"
            if variant["actor_id"] != expected:
                raise ValueError("Class appearance refers to the wrong actor")
            actor_ids.add(expected)
            races.add(variant["race_id"])
    extra = actor_ids
    if {row["id"] for row in actors} != extra or {row["id"] for row in artifacts} != extra:
        raise ValueError("Character catalog has an incomplete artifact join")
    for artifact in artifacts:
        relative = "actors/" + artifact["id"].removeprefix("actor.player.") + ".glb"
        if artifact["path"] != RESOURCE_ROOT + relative or not re.fullmatch(
            r"[a-f0-9]{64}", artifact["sha256"]
        ):
            raise ValueError("Character artifact path or hash is invalid")


def validate_package(directory: Path) -> dict:
    document = json.loads((directory / "catalog.v1.json").read_text())
    validate_catalog(document)
    allowed = {"catalog.v1.json"}
    for artifact in document["artifacts"]:
        relative = artifact["path"].removeprefix(RESOURCE_ROOT)
        model = directory / relative
        if hashlib.sha256(model.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("Character GLB differs from its catalog")
        allowed.update((relative, relative + ".import"))
        allowed.update(validate_extracted_textures(directory, relative))
    actual = {
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    }
    if actual - allowed:
        raise ValueError("Character runtime directory contains undeclared files")
    return document


def build(source: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Use a new character catalog output directory")
    normalized, artifacts = converted(source.resolve())
    document = public_catalog(normalized, artifacts)
    validate_catalog(document)
    for artifact in document["artifacts"]:
        relative = artifact["path"].removeprefix(RESOURCE_ROOT)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "generated" / relative, destination)
    extract_actor_texture_pngs(
        output, {"artifacts": [artifacts[row["id"]] for row in document["artifacts"]]}
    )
    (output / "catalog.v1.json").write_bytes(canonical_bytes(document) + b"\n")
    validate_package(output)
    return document


def install(source: Path, *, replace: bool = False) -> Path | None:
    """Validate before swapping; keep any previous installation next to this build."""
    source = source.resolve()
    validate_package(source)
    backup = source.with_name(source.name + "-previous-install")
    if INSTALL_ROOT.exists() and (not replace or backup.exists()):
        raise ValueError("Use --replace with a new build output to preserve the installed catalog")
    INSTALL_ROOT.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    with tempfile.TemporaryDirectory(
        prefix=".characters-install-", dir=INSTALL_ROOT.parent
    ) as work:
        staged = Path(work) / "characters"
        shutil.copytree(source, staged)
        validate_package(staged)
        if INSTALL_ROOT.exists():
            INSTALL_ROOT.rename(backup)
            previous = backup
        try:
            staged.rename(INSTALL_ROOT)
        except OSError:
            if previous is not None:
                previous.rename(INSTALL_ROOT)
            raise
    return previous


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    parser.add_argument(
        "--replace", action="store_true", help="Preserve and replace an installed catalog"
    )
    args = parser.parse_args()
    catalog = build(args.source.resolve(), args.output.resolve())
    if args.install:
        install(args.output, replace=args.replace)
    print(
        json.dumps(
            {
                "classes": len(catalog["classes"]),
                "actors": len(catalog["actors"]),
                "installed": args.install,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
