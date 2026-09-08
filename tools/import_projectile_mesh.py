#!/usr/bin/env python3
"""Convert a selected mesh-only projectile effect; retain its original render recipe."""

import argparse
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path, PurePosixPath

from content_compile import ROOT, source_archive
from content_formats import parse_legacy_script, virtual_path
from import_target_effects import audit_glb, convert_image, frame_payload, run_blender
from metin_effect_mesh import parse_mde, parse_mesh_root, parse_mse
from mixed_effects import parse_mixed_effect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effect", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--mixed", action="store_true", help="Convert every layer of a mixed particle/mesh effect"
    )
    args = parser.parse_args()
    effect = virtual_path(args.effect)
    if not effect.startswith("ymir work/") or not effect.endswith(".mse"):
        raise ValueError("Select an original mesh-effect path")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    frozen = {
        str(ROOT / "tools" / n): hashlib.sha256((ROOT / "tools" / n).read_bytes()).hexdigest()
        for n in (
            "import_projectile_mesh.py",
            "import_target_effects.py",
            "metin_effect_mesh.py",
            "metin_particles.py",
            "mixed_effects.py",
            "blender_target_effects.py",
            "content_formats.py",
            "content_compile.py",
            "metin_archive.py",
        )
    }
    archive = source_archive(args.offline)
    source_files = {}

    def fetch(path):
        result = archive.get(archive.resolve(path))
        source_files[str(result)] = hashlib.sha256(result.read_bytes()).hexdigest()
        return result

    script = fetch(effect).read_text()
    mixed = parse_mixed_effect(script, effect) if args.mixed else None
    if mixed:
        root = parse_legacy_script(script)
        mse = parse_mesh_root(
            replace(root, groups=[g for g in root.groups if g.name == "Mesh"]),
            blend_pairs={(3, 2), (3, 8), (5, 2), (5, 6)},
        )
    else:
        mse = parse_mse(script, blend_pairs={(3, 8), (5, 2), (5, 6)})
    particle_textures = {}
    if mixed:
        paths = {t for s in mixed["particles"]["systems"] for t in s["particle"]["textures"]}
        if len(paths) > 256:
            raise ValueError("Mixed particle textures exceed budget")
        for path in sorted(paths):
            relative = f"textures/{hashlib.sha256(path.encode()).hexdigest()[:16]}.png"
            receipt = convert_image(fetch(path), output / relative)
            particle_textures[path] = {
                "path": relative,
                "sha256": receipt["png_sha256"],
                "rgba_sha256": receipt["rgba_sha256"],
                "width": receipt["width"],
                "height": receipt["height"],
            }
    assets, originals, recipes = [], [], []
    for index, mesh in enumerate(mse.meshes):
        if len(mesh.position_events) != 1:
            raise ValueError("Mesh converter currently needs a fixed offset")
        mde = parse_mde(fetch(str(PurePosixPath(effect).parent / mesh.mesh_file)).read_bytes())
        if len(mesh.elements) != len(mde.geometries):
            raise ValueError("Mesh effect element count differs from geometry")
        geometries = []
        for geometry in mde.geometries:
            texture_path = virtual_path(geometry.texture_path)
            texture = f"textures/{hashlib.sha256(texture_path.encode()).hexdigest()[:16]}.png"
            convert_image(fetch(texture_path), output / texture)
            geometries.append(
                {
                    "name": geometry.name,
                    "texture_resource": texture,
                    "frames": [frame_payload(f) for f in geometry.frames],
                }
            )
        identity = f"mesh-{index}"
        assets.append(
            {
                "id": identity,
                "frame_delay": mesh.frame_delay,
                "position_cm": mesh.position_events[0].position,
                "frames": list(range(mde.frame_count)),
                "geometries": geometries,
            }
        )
        originals.append(mde)
        recipes.append(asdict(mesh))
    input_path = output / "blender-input.json"
    input_path.write_text(json.dumps({"assets": assets}, indent=2) + "\n")
    run_blender(args.blender.resolve(), input_path, output, output)
    audits = [
        audit_glb(
            output / "models" / f"mesh-{i}.glb",
            mde,
            position_cm=mse.meshes[i].position_events[0].position,
            frame_delay=mse.meshes[i].frame_delay,
        )
        for i, mde in enumerate(originals)
    ]
    for path, digest in {**frozen, **source_files}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError("Mesh conversion inputs changed")
    catalog = {
        "schema": "mt2spacetime.mesh-effects-candidate",
        "version": 1,
        "source_effect": effect,
        "meshes": [
            {
                "model": f"models/mesh-{i}.glb",
                "model_sha256": audits[i]["sha256"],
                "recipe": recipes[i],
                "frame_count": original.frame_count,
                "geometries": [
                    {
                        "texture": assets[i]["geometries"][j]["texture_resource"],
                        "texture_sha256": hashlib.sha256(
                            (output / assets[i]["geometries"][j]["texture_resource"]).read_bytes()
                        ).hexdigest(),
                        "visibility": [frame.visibility for frame in geometry.frames],
                    }
                    for j, geometry in enumerate(original.geometries)
                ],
            }
            for i, original in enumerate(originals)
        ],
    }
    if mixed:
        catalog.update(
            particle_effect=mixed["particles"],
            textures=particle_textures,
            layer_order=mixed["layer_order"],
        )
    catalog_path = output / "mesh-effects.v1.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")
    report = {
        "status": "geometry-converted-not-runtime-qualified",
        "source_effect": effect,
        "source_files": source_files,
        "tools": frozen,
        "models": audits,
        "render_recipes": recipes,
        "particle_systems": len(mixed["particles"]["systems"]) if mixed else 0,
        "layer_order": mixed["layer_order"] if mixed else [],
        "mesh_catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "runtime_requirements": ["original-blend-and-color-recipe", "flight-attachment-rendering"],
    }
    (output / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"models": len(audits), "status": report["status"]}))


if __name__ == "__main__":
    main()
