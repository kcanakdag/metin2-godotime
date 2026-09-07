#!/usr/bin/env python3
"""Discover selected player assets from pinned race/animation definitions and convert them."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from character_definitions import initial_points, registered_motions
from content_compile import (
    ROOT,
    _normalise_motions,
    canonical_bytes,
    fetch_server_references,
    source_archive,
)
from content_formats import parse_race_script
from fetch_test_assets import METIN_COMMIT
from metin_archive import safe_path
from metin_root_motion import _carbon_reader
from npc_definitions import material_paths

DEFAULT_PROFILE = ROOT / "content/profiles/classic-characters.json"


def compile_profile(path: Path, *, offline: bool) -> dict:
    profile = json.loads(path.read_text())
    if (
        profile["schema_version"] != 1
        or type(profile["schema_version"]) is not int
        or profile["source"]["client_revision"] != METIN_COMMIT
    ):
        raise ValueError("Unsupported character profile or source revision")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", profile["profile_id"]):
        raise ValueError("Invalid character profile ID")
    archive = source_archive(offline)
    references = fetch_server_references(profile, offline=offline)
    server_root = (
        ROOT / "assets/source/content/server" / profile["source"]["server_reference"]["revision"]
    )
    points = initial_points(
        (server_root / "src/game/src/constants.cpp").read_text(errors="replace")
    )
    settings = archive.get("bin/pack/root/playersettingmodule.py").read_text(errors="replace")
    loader = archive.get("src/GameLib/RaceMotionData.cpp").read_text(errors="replace")
    if re.search(r'GetToken\w+\("linktime"', loader, re.I):
        raise ValueError("Original motion loader now consumes legacy LinkTime; review the adapter")
    classes, declarations = [], []
    ids, appearances, race_ids = set(), set(), set()
    for selected in profile["classes"]:
        class_id = selected["class_id"]
        if type(class_id) is not int or not 0 <= class_id < len(points) or class_id in ids:
            raise ValueError("Invalid or duplicate class ID")
        ids.add(class_id)
        modes, attachments = registered_motions(settings, selected["source_class"])
        variants = []
        for variant in selected["variants"]:
            sex, key = variant["sex"], variant["model_key"]
            if (
                type(sex) is not int
                or sex not in (0, 1)
                or (class_id, sex) in appearances
                or not re.fullmatch(r"[a-z]+_[mw]", key)
            ):
                raise ValueError("Invalid or duplicate character appearance")
            appearances.add((class_id, sex))
            race_match = re.search(r"^RACE_" + key.upper() + r"\s*=\s*(\d+)\s*$", settings, re.M)
            if not race_match or int(race_match[1]) in race_ids:
                raise ValueError("Missing or duplicate original race ID")
            race_id = int(race_match[1])
            race_ids.add(race_id)
            script = "bin/pack/root/" + key + ".msm"
            race = parse_race_script(archive.get(script).read_text(errors="replace"))
            model = archive.resolve(race["base_model"])
            raw = _carbon_reader().read_raw(archive.get(model).read_bytes()).file_info
            textures = [archive.resolve(texture) for texture in material_paths(raw)]
            hairs = [hair for hair in race["hair"] if hair["hair_index"] == 0]
            if len(hairs) != 1:
                raise ValueError(f"Expected exactly one default hair in {script}")
            hair = {
                field: archive.resolve(value) if field != "hair_index" else value
                for field, value in hairs[0].items()
            }
            archive.fetch_many(
                set(textures + [hair["model"], hair["source_skin"], hair["target_skin"]])
            )
            actor_id = f"actor.player.{selected['id']}-{'male' if sex == 0 else 'female'}"
            actor_modes = json.loads(json.dumps(modes))
            # Resolve each MSA through the original pack precedence, just like its model.
            root = race["base_model"].rsplit("/", 1)[0]
            for mode in actor_modes:
                for motion in mode["motions"]:
                    motion["files"] = [
                        archive.resolve(root + "/" + file) for file in motion["files"]
                    ]
            archive.fetch_many(
                {
                    file
                    for mode in actor_modes
                    for motion in mode["motions"]
                    for file in motion["files"]
                }
            )
            declarations.append(
                {
                    "id": actor_id,
                    "kind": "player",
                    "name": selected["name"],
                    "race_id": race_id,
                    "model_key": key,
                    "race_script": script,
                    "model": model,
                    "textures": textures,
                    "default_hair": hair,
                    "output": "actors/" + actor_id.removeprefix("actor.player.") + ".glb",
                    "orientation": {"output_forward": "-Z", "yaw_correction_degrees": 180.0},
                    "attachment_bones": attachments,
                    "modes": actor_modes,
                }
            )
            variants.append({"sex": sex, "race_id": race_id, "actor_id": actor_id})
        classes.append(
            {
                "id": selected["id"],
                "class_id": class_id,
                "name": selected["name"],
                "initial_points": points[class_id],
                "starter_weapon_vnum": selected["starter_weapon_vnum"],
                "variants": variants,
            }
        )
    if ids != {0, 1, 2, 3} or len(appearances) != 8:
        raise ValueError(
            "The classic character profile requires four classes and eight appearances"
        )
    # This pinned loader reads only PreInputTime, DirectInputTime and InputLimitTime.
    # Some source LinkTime fields contain an uninitialized float. They never drive
    # the original client, and must not become a Godot/server timestamp either.
    actors, unsupported = _normalise_motions(
        {"actors": declarations, "ignore_legacy_link_time": True, "allow_post_clip_combo": True},
        archive,
    )
    payload = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "compiler_version": "character-content-v1.0.0",
        "actors": actors,
        "items": [],
        "classes": classes,
        "unsupported_motion_metadata": unsupported,
        "motion_adapter": {
            "ignored_field": "ComboInputData.LinkTime",
            "evidence": "src/GameLib/RaceMotionData.cpp",
        },
        "sources": [
            {"path": path, "revision": METIN_COMMIT, **record}
            for path, record in sorted(archive.used.items())
        ]
        + references,
        "distribution": profile["distribution"],
    }
    payload["content_hash"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def conversion_inputs(profile: Path, normalized: Path) -> dict[str, str]:
    inputs = [profile.resolve(), normalized.resolve()]
    inputs.extend(
        ROOT / "tools" / name
        for name in (
            "import_character_content.py",
            "character_definitions.py",
            "import_actor_content.py",
            "gr2_bindings.py",
            "metin_gr2_adapter.py",
            "content_compile.py",
            "content_formats.py",
            "npc_definitions.py",
        )
    )
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}


def convert(profile: Path, normalized: Path, output: Path, blender: str) -> None:
    frozen = conversion_inputs(profile, normalized)
    receipt = output / "conversion-receipt.json"
    receipt.write_text(json.dumps({"status": "started", "inputs": frozen}, indent=2) + "\n")
    command = [
        blender,
        "--background",
        "--factory-startup",
        "-noaudio",
        "--python-exit-code",
        "1",
        "--python",
        str(ROOT / "tools/import_actor_content.py"),
        "--",
        "--manifest",
        str(normalized),
        "--source-root",
        str(ROOT / "assets/source/content" / METIN_COMMIT),
        "--output",
        str(output / "generated"),
        "--report",
        str(output / "blender-report.json"),
    ]
    with (output / "blender.log").open("w") as log:
        result = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=False
        )
    if result.returncode or conversion_inputs(profile, normalized) != frozen:
        raise RuntimeError(
            f"Character conversion failed or inputs changed; see {output / 'blender.log'}"
        )
    report = json.loads((output / "blender-report.json").read_text())
    manifest = json.loads(normalized.read_text())
    if report.get("status") != "converted" or {row["id"] for row in report["artifacts"]} != {
        row["id"] for row in manifest["actors"]
    }:
        raise ValueError("Incomplete character conversion report")
    for row in report["artifacts"]:
        if (
            hashlib.sha256(
                (output / "generated" / safe_path(row["relative_path"])).read_bytes()
            ).hexdigest()
            != row["sha256"]
        ):
            raise ValueError("Changed character conversion artifact")
    receipt.write_text(
        json.dumps(
            {
                "status": "converted",
                "inputs": frozen,
                "content_hash": manifest["content_hash"],
                "report_sha256": hashlib.sha256(
                    (output / "blender-report.json").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--blender")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Build and install the verified Godot catalog after conversion",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Preserve the previously installed catalog before replacing it",
    )
    args = parser.parse_args()
    if (args.install and not args.blender) or (args.replace and not args.install):
        parser.error("--install requires --blender; --replace requires --install")
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Use a new output directory to preserve previous conversion evidence")
    manifest = compile_profile(args.profile, offline=args.offline)
    output.mkdir(parents=True)
    normalized = output / "normalized.v1.json"
    normalized.write_text(json.dumps(manifest, indent=2) + "\n")
    if args.blender:
        convert(args.profile, normalized, output, args.blender)
    if args.install:
        from build_character_catalog import build, install

        build(output, output / "runtime")
        install(output / "runtime", replace=args.replace)
    print(
        json.dumps(
            {
                "output": str(output),
                "actors": len(manifest["actors"]),
                "motions": sum(
                    len(mode["motions"]) for actor in manifest["actors"] for mode in actor["modes"]
                ),
                "unsupported_metadata": len(manifest["unsupported_motion_metadata"]),
                "content_hash": manifest["content_hash"],
                "installed": args.install,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
