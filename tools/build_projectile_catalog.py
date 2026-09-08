#!/usr/bin/env python3
"""Package converted projectile dependencies into a portable runtime catalog."""

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from content_compile import canonical_bytes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(particles_path, flights_path, meshes_paths, output):
    inputs = [particles_path, flights_path, *meshes_paths, Path(__file__)]
    frozen = {str(p.resolve()): digest(p) for p in inputs}
    particles = json.loads(particles_path.read_text())
    inventory = json.loads(flights_path.read_text())
    if (particles.get("schema"), particles.get("version")) != (
        "mt2spacetime.particle-effect-candidate",
        1,
    ) or (inventory.get("schema"), inventory.get("version")) != (
        "mt2spacetime.projectile-source-inventory",
        1,
    ):
        raise ValueError("Unsupported projectile input catalog version")
    if particles["source_revision"] != inventory["source_revision"]:
        raise ValueError("Projectile packages have different source revisions")
    for document in (particles, inventory):
        expected = document["content_hash"]
        unsigned = {k: v for k, v in document.items() if k != "content_hash"}
        if hashlib.sha256(canonical_bytes(unsigned)).hexdigest() != expected:
            raise ValueError("Projectile input catalog hash differs")
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    sidecars = {}
    texture_import = (
        '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\n\n'
        "[params]\ncompress/mode=0\nmipmaps/generate=false\n"
        "detect_3d/compress_to=0\nprocess/fix_alpha_border=false\n"
    )

    def asset(catalog, relative, expected):
        relative = Path(relative)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix not in (".png", ".glb")
        ):
            raise ValueError("Unsafe projectile resource path")
        source = catalog.resolve().parent / relative
        if digest(source) != expected:
            raise ValueError("Projectile resource differs from its catalog")
        frozen[str(source)] = expected
        path = "assets/" + expected + relative.suffix
        destination = output / path
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(source, destination)
        if digest(destination) != expected:
            raise ValueError("Projectile resource changed while copying")
        files[path] = expected
        if relative.suffix == ".png":
            sidecar = destination.with_suffix(".png.import")
            sidecar.write_text(texture_import)
            sidecars[path + ".import"] = digest(sidecar)
        return path

    effects = {e["effect_path"]: e for e in particles["effects"]}
    flights = {f["path"]: f for f in inventory["flight_definitions"]}
    if len(effects) != len(particles["effects"]) or len(flights) != len(
        inventory["flight_definitions"]
    ):
        raise ValueError("Duplicate projectile definition")
    textures = copy.deepcopy(particles["textures"])
    for texture in textures.values():
        texture["path"] = asset(particles_path, texture["path"], texture["sha256"])
    meshes = {}
    for path in meshes_paths:
        document = json.loads(path.read_text())
        receipt_path = path.parent / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("mesh_catalog_sha256") != digest(path):
            raise ValueError("Mesh catalog differs from conversion receipt")
        frozen[str(receipt_path.resolve())] = digest(receipt_path)
        source = document["source_effect"]
        if source in meshes or source in effects or len(document["meshes"]) != 1:
            raise ValueError("Duplicate or unsupported multi-mesh effect")
        mesh = copy.deepcopy(document["meshes"][0])
        mesh["model"] = asset(path, mesh["model"], mesh["model_sha256"])
        for geometry in mesh["geometries"]:
            geometry["texture"] = asset(path, geometry["texture"], geometry["texture_sha256"])
        meshes[source] = mesh
    for flight in flights.values():
        for attachment in flight["attachments"]:
            if attachment["effect"] not in effects and attachment["effect"] not in meshes:
                raise ValueError("Flight attachment dependency is missing")
        if flight["bomb_effect"] is not None and flight["bomb_effect"] not in effects:
            raise ValueError("Flight impact dependency is missing or not particle based")
    for effect in effects.values():
        for system in effect["systems"]:
            if any(t not in textures for t in system["particle"]["textures"]):
                raise ValueError("Particle texture dependency is missing")
    document = {
        "schema": "mt2spacetime.projectile-catalog",
        "version": 1,
        "source_revision": particles["source_revision"],
        "flights": flights,
        "effects": effects,
        "textures": textures,
        "meshes": meshes,
        "files": files,
        "import_sidecars": sidecars,
    }
    document["content_hash"] = hashlib.sha256(canonical_bytes(document)).hexdigest()
    if any(digest(Path(p)) != expected for p, expected in frozen.items()):
        raise ValueError("Projectile build inputs changed")
    (output / "catalog.v1.json").write_bytes(canonical_bytes(document) + b"\n")
    (output / "receipt.json").write_text(
        json.dumps(
            {"inputs": frozen, "catalog_sha256": digest(output / "catalog.v1.json")}, indent=2
        )
        + "\n"
    )
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--particles", type=Path, required=True)
    parser.add_argument("--flights", type=Path, required=True)
    parser.add_argument("--meshes", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.particles, args.flights, args.meshes, args.output)
    print(
        json.dumps(
            {
                "flights": len(result["flights"]),
                "files": len(result["files"]),
                "content_hash": result["content_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
