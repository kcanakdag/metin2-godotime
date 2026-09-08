#!/usr/bin/env python3
"""Package selected converted motion effects with complete installed-skill links."""

import argparse
import copy
import hashlib
import json
import math
from io import BytesIO
from pathlib import Path

from content_compile import canonical_bytes
from PIL import Image

TEXTURE_IMPORT = (
    '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\n\n'
    "[params]\ncompress/mode=0\nmipmaps/generate=false\ndetect_3d/compress_to=0\n"
    "process/fix_alpha_border=false\n"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_links(rows, skills, characters, effects):
    expected = {
        (v["actor_id"], s["vnum"]): v["action_id"] for s in skills["skills"] for v in s["variants"]
    }
    motions = {
        m["action_id"]: m
        for a in characters["actors"]
        for mode in a["modes"]
        for m in mode["motions"]
    }
    linked = {}
    covered = set()
    for row in rows:
        key = (row["actor_id"], row["skill_vnum"])
        if key not in expected or key in covered:
            raise ValueError("Unexpected or duplicate skill appearance link")
        action = expected[key]
        if action not in motions:
            raise ValueError("Effect skill motion is absent from installed characters")
        events = row["effects"]
        if not isinstance(events, list) or not 1 <= len(events) <= 32:
            raise ValueError("Expected bounded nonempty motion effects")
        ids = set()
        for event in events:
            identity = event["source_event"]
            if not isinstance(identity, str) or not identity or identity in ids:
                raise ValueError("Missing or duplicate effect event identity")
            ids.add(identity)
            if event["effect_path"] not in effects:
                raise ValueError("Motion event references an unpackaged effect")
            start = event["start_us"]
            if type(start) is not int or not 0 <= start <= motions[action]["duration_us"]:
                raise ValueError("Effect timing exceeds installed motion")
            if event["attachment"] not in (
                "follow_root",
                "follow_bone",
                "capture_root",
                "capture_bone",
            ):
                raise ValueError("Unknown effect attachment")
            if type(event.get("enabled", True)) is not bool:
                raise ValueError("Effect enabled flag must be boolean")
            bone = event["bone"]
            if (
                not isinstance(bone, str)
                or len(bone) > 128
                or bool(bone) != event["attachment"].endswith("bone")
            ):
                raise ValueError("Effect bone does not match attachment mode")
            offset = event["position_m"]
            if (
                not isinstance(offset, list)
                or len(offset) != 3
                or any(
                    type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000
                    for v in offset
                )
            ):
                raise ValueError("Invalid effect position")
        linked[action] = copy.deepcopy(events)
        covered.add(key)
    if covered != set(expected):
        raise ValueError("Effect package does not cover every enabled skill appearance")
    return linked


def build(particle_path, mixed_paths, links_path, skills_path, characters_path, output):
    inputs = [particle_path, *mixed_paths, links_path, skills_path, characters_path, Path(__file__)]
    frozen = {str(p.resolve()): digest(p) for p in inputs}
    particles = json.loads(particle_path.read_text())
    mixed = [json.loads(p.read_text()) for p in mixed_paths]
    if (
        particles.get("schema") != "mt2spacetime.particle-effect-candidate"
        or particles.get("version") != 1
    ):
        raise ValueError("Unsupported particle catalog")
    if any(
        m.get("schema") != "mt2spacetime.mesh-effects-candidate"
        or "particle_effect" not in m
        or m.get("version") != 1
        for m in mixed
    ):
        raise ValueError("Expected complete mixed effect catalogs")
    effects = {e["effect_path"]: copy.deepcopy(e) for e in particles["effects"]}
    mixed_effects = {m["source_effect"]: copy.deepcopy(m) for m in mixed}
    if (
        len(effects) != len(particles["effects"])
        or len(mixed_effects) != len(mixed)
        or effects.keys() & mixed_effects.keys()
    ):
        raise ValueError("Duplicate effect definitions")
    links = validate_links(
        json.loads(links_path.read_text()),
        json.loads(skills_path.read_text()),
        json.loads(characters_path.read_text()),
        effects.keys() | mixed_effects.keys(),
    )
    runtime = output / "runtime"
    runtime.mkdir(parents=True, exist_ok=False)
    files, sidecars, textures = {}, {}, {}

    def asset(catalog, relative, expected):
        relative = Path(relative)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix not in (".png", ".glb")
        ):
            raise ValueError("Unsafe effect resource path")
        source = catalog.resolve().parent / relative
        if digest(source) != expected:
            raise ValueError("Effect resource hash mismatch")
        frozen[str(source)] = expected
        content = source.read_bytes()
        if relative.suffix == ".png":
            with Image.open(BytesIO(content)) as image:
                if not 1 <= image.width <= 4096 or not 1 <= image.height <= 4096:
                    raise ValueError("Effect texture dimensions exceed bounds")
                rgba = image.convert("RGBA")
                encoded = BytesIO()
                rgba.save(encoded, format="PNG", compress_level=9, optimize=False)
                content = encoded.getvalue()
                with Image.open(BytesIO(content)) as check:
                    if check.convert("RGBA").tobytes() != rgba.tobytes():
                        raise ValueError("Canonical effect texture changed pixels")
        packaged_hash = hashlib.sha256(content).hexdigest()
        target = "assets/" + packaged_hash + relative.suffix
        destination = runtime / target
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(content)
        if digest(destination) != packaged_hash:
            raise ValueError("Effect resource changed while copying")
        files[target] = packaged_hash
        if relative.suffix == ".png":
            sidecar = destination.with_suffix(".png.import")
            sidecar.write_text(TEXTURE_IMPORT)
            sidecars[target + ".import"] = digest(sidecar)
        return target

    def particle_textures(catalog_path, document):
        for virtual, texture in document["textures"].items():
            target = asset(catalog_path, texture["path"], texture["sha256"])
            if virtual in textures and textures[virtual] != target:
                raise ValueError("Conflicting effect texture definitions")
            textures[virtual] = target

    particle_textures(particle_path, particles)
    for path, source in zip(mixed_paths, mixed, strict=True):
        particle_textures(path, source)
        entry = mixed_effects[source["source_effect"]]
        entry.pop("textures")
        for mesh in entry["meshes"]:
            mesh["model"] = asset(path, mesh["model"], mesh["model_sha256"])
            for geometry in mesh["geometries"]:
                target = asset(path, geometry["texture"], geometry["texture_sha256"])
                geometry["texture"] = target
                geometry["texture_sha256"] = files[target]
                textures[target] = target
    for effect in [*effects.values(), *(m["particle_effect"] for m in mixed_effects.values())]:
        for system in effect["systems"]:
            if any(t not in textures for t in system["particle"]["textures"]):
                raise ValueError("Particle recipe references an unpackaged texture")
    document = {
        "schema": "mt2spacetime.motion-effects",
        "version": 1,
        "character_catalog_sha256": digest(characters_path),
        "skill_catalog_sha256": digest(skills_path),
        "effects": effects,
        "mixed_effects": mixed_effects,
        "textures": textures,
        "links": links,
        "files": files,
        "import_sidecars": sidecars,
        "source_to_actor_yaw_degrees": 180,
    }
    document["content_hash"] = hashlib.sha256(canonical_bytes(document)).hexdigest()
    if any(digest(Path(p)) != expected for p, expected in frozen.items()):
        raise ValueError("Effect package inputs changed")
    (runtime / "catalog.v1.json").write_bytes(canonical_bytes(document) + b"\n")
    (output / "receipt.json").write_text(
        json.dumps({"inputs": frozen, "content_hash": document["content_hash"]}, indent=2) + "\n"
    )
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("particles", "links", "skills", "characters", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--mixed", type=Path, action="append", default=[])
    args = parser.parse_args()
    result = build(
        args.particles, args.mixed, args.links, args.skills, args.characters, args.output
    )
    print(
        json.dumps(
            {
                "motions": len(result["links"]),
                "files": len(result["files"]),
                "hash": result["content_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
