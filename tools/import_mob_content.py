#!/usr/bin/env python3
"""Convert an explicit original wildlife selection through the shared Blender importer."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from content_compile import ROOT, _normalise_motions, canonical_bytes, source_archive
from discover_mobs import compile_profile
from fetch_test_assets import METIN_COMMIT
from metin_archive import safe_path
from metin_root_motion import _carbon_reader
from mob_shapes import apply_skin_remaps
from npc_definitions import material_bindings, motion_groups


def normalize(profile, *, offline):
    inventory = compile_profile(profile, offline=offline)
    archive = source_archive(offline)
    declarations, bindings = [], {}
    for mob in inventory["mobs"]:
        model = mob["assets"]["model"]
        raw = _carbon_reader().read_raw(archive.get(model).read_bytes()).file_info
        textures = {
            key: archive.resolve(value)
            for key, value in material_bindings(raw, "/".join(model.split("/")[3:-1])).items()
        }
        textures = apply_skin_remaps(textures, mob["assets"]["default_shape"]["skin_remaps"])
        archive.fetch_many(sorted(set(textures.values())))
        bindings[mob["id"]] = textures
        declarations.append(
            {
                "id": mob["id"],
                "kind": "mob",
                "vnum": mob["vnum"],
                "name": mob["name"],
                "model_key": mob["model_key"],
                "race_script": mob["assets"]["race_script"],
                "model": model,
                "motion_root": mob["assets"]["motion_list"].rsplit("/", 1)[0],
                "textures": sorted(set(textures.values())),
                "output": f"actors/{mob['model_key']}-{mob['vnum']}.glb",
                "attachment_bones": {},
                "orientation": {"output_forward": "-Z", "yaw_correction_degrees": 180.0},
                "modes": [{"id": "general", "motions": motion_groups(mob["assets"]["motions"])}],
            }
        )
    actors, deferred = _normalise_motions({"actors": declarations}, archive)
    for actor in actors:
        actor["material_texture_bindings"] = bindings[actor["id"]]
    result = {
        "schema_version": 1,
        "profile_id": inventory["profile_id"],
        "compiler_version": "mob-content-v1",
        "actors": actors,
        "items": [],
        "mob_catalog": inventory["mobs"],
        "deferred_motion_events": deferred,
        "sources": [
            {"path": path, "revision": METIN_COMMIT, **record}
            for path, record in sorted(archive.used.items())
        ],
        "inventory": inventory,
    }
    result["content_hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "content/profiles/yongan-wildlife.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--blender")
    args = parser.parse_args()
    manifest = normalize(args.profile, offline=args.offline)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    normalized = output / "normalized.v1.json"
    normalized.write_text(json.dumps(manifest, indent=2) + "\n")
    if args.blender:
        files = [args.profile.resolve(), normalized]
        files.extend(
            ROOT / "tools" / name
            for name in (
                "import_mob_content.py",
                "discover_mobs.py",
                "mob_definitions.py",
                "mob_shapes.py",
                "npc_definitions.py",
                "import_actor_content.py",
                "gr2_bindings.py",
                "metin_gr2_adapter.py",
                "content_compile.py",
                "content_formats.py",
                "metin_root_motion.py",
            )
        )
        frozen = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        receipt = output / "conversion-receipt.json"
        receipt.write_text(json.dumps({"status": "started", "inputs": frozen}, indent=2) + "\n")
        with (output / "blender.log").open("w") as log:
            subprocess.run(
                [
                    args.blender,
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
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
                check=True,
            )
        if any(hashlib.sha256(p.read_bytes()).hexdigest() != frozen[str(p)] for p in files):
            raise ValueError("Mob conversion inputs changed during conversion")
        report = json.loads((output / "blender-report.json").read_text())
        if report.get("status") != "converted" or len(report["artifacts"]) != len(
            manifest["actors"]
        ):
            raise ValueError("Incomplete mob conversion")
        for artifact in report["artifacts"]:
            p = output / "generated" / safe_path(artifact["relative_path"])
            if hashlib.sha256(p.read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("Mob artifact differs from conversion report")
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
    print(
        json.dumps(
            {
                "mobs": len(manifest["actors"]),
                "content_hash": manifest["content_hash"],
                "deferred_events": len(manifest["deferred_motion_events"]),
            }
        )
    )


if __name__ == "__main__":
    main()
