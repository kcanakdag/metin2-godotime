#!/usr/bin/env python3
"""Convert explicitly selected particle recipes and textures; does not install them."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import ROOT, canonical_bytes, source_archive
from fetch_test_assets import METIN_COMMIT
from metin_particles import parse_particle_mse
from PIL import Image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effect", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not 1 <= len(args.effect) <= 32 or len(set(args.effect)) != len(args.effect):
        raise ValueError("Select 1–32 distinct particle effects")
    inputs = {
        str(ROOT / "tools" / name): digest(ROOT / "tools" / name)
        for name in (
            "import_particle_effects.py",
            "metin_particles.py",
            "metin_effect_mesh.py",
            "content_compile.py",
            "content_formats.py",
            "metin_archive.py",
            "fetch_test_assets.py",
        )
    }
    args.output.mkdir(parents=True, exist_ok=False)
    archive = source_archive(args.offline)
    sources, recipes = {}, []
    for effect in sorted(args.effect):
        path = archive.get(archive.resolve(effect))
        sources[str(path)] = digest(path)
        recipes.append(parse_particle_mse(path.read_text(), effect))
    texture_paths = sorted(
        {
            texture
            for recipe in recipes
            for system in recipe["systems"]
            for texture in system["particle"]["textures"]
        }
    )
    if len(texture_paths) > 256:
        raise ValueError("Selected effects exceed texture budget")
    (args.output / "textures").mkdir()
    textures = {}
    for virtual in texture_paths:
        source = archive.get(archive.resolve(virtual))
        sources[str(source)] = digest(source)
        output = "textures/" + hashlib.sha256(virtual.encode()).hexdigest()[:16] + ".png"
        with Image.open(source) as image:
            if not 1 <= image.width <= 4096 or not 1 <= image.height <= 4096:
                raise ValueError("Particle texture exceeds dimensions limit")
            rgba = image.convert("RGBA")
            rgba.save(args.output / output)
            with Image.open(args.output / output) as converted:
                if (
                    converted.size != rgba.size
                    or converted.convert("RGBA").tobytes() != rgba.tobytes()
                ):
                    raise ValueError("Particle texture conversion changed decoded pixels")
            textures[virtual] = {
                "path": output,
                "width": rgba.width,
                "height": rgba.height,
                "sha256": digest(args.output / output),
                "rgba_sha256": hashlib.sha256(rgba.tobytes()).hexdigest(),
            }
    frozen = {**inputs, **sources}
    if any(digest(Path(path)) != expected for path, expected in frozen.items()):
        raise ValueError("Particle conversion inputs changed during the build")
    result = {
        "schema": "mt2spacetime.particle-effect-candidate",
        "version": 1,
        "source_revision": METIN_COMMIT,
        "effects": recipes,
        "textures": textures,
        "source_units": "centimetres-seconds-degrees",
        "runtime_status": "converted-not-installed",
        "runtime_requirements": [
            "particle-simulation",
            "original-blend-and-billboard-rendering",
            "flight-attachment",
        ],
    }
    result["content_hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    (args.output / "effects.v1.json").write_bytes(canonical_bytes(result) + b"\n")
    receipt = {
        "inputs": frozen,
        "catalog_sha256": digest(args.output / "effects.v1.json"),
        "source_rule_references": [
            "EffectLib/ParticleSystemData.cpp:OnLoadScript",
            "EffectLib/Type.h:GetTimeEventBlendValue",
            "EffectLib/EmitterProperty.h",
            "EffectLib/ParticleProperty.h",
        ],
        "effects": len(recipes),
        "systems": sum(len(r["systems"]) for r in recipes),
        "textures": len(textures),
        "texture_pixels_verified": True,
        "runtime_qualified": False,
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps({k: receipt[k] for k in ("effects", "systems", "textures", "runtime_qualified")})
    )


if __name__ == "__main__":
    main()
