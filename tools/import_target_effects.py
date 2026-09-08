#!/usr/bin/env python3
"""Offline conversion of exactly the pinned hover and combat-target mesh effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

from fetch_test_assets import METIN_COMMIT, ROOT
from metin_archive import Archive, write_json
from metin_effect_mesh import MdeFile, MseFile, d3dx_color_byte, parse_mde, parse_mse
from PIL import Image
from PIL import __version__ as pillow_version

REPOSITORY = "https://git.old-metin2.com/metin2/client"
AUDIT = ROOT / ".local/p2/target-effect-asset-audit.json"
SOURCE_ROOT = ROOT / "assets/source/maps" / METIN_COMMIT
OUTPUT = ROOT / ".local/p2-target/effects/generated"
WORK = ROOT / ".local/p2-target/effects/work"
INSTALL_ROOT = ROOT / "client/assets/imported/content/p2-target-effects"
RUNTIME_RESOURCE_ROOT = "res://assets/imported/content/p2-target-effects"
BLENDER = Path("/home/kcan/Downloads/blender-5.2.1-linux-x64/blender")
GODOT_CANDIDATES = (
    Path("/home/kcan/.local/bin/godot4.7.2"),
    Path("/home/kcan/Godot_v4.7.2-stable_linux.x86_64"),
    Path("/home/kcan/.local/bin/godot"),
)
EFFECT_DIRECTORY = "bin/pack/Effect/ymir work/effect/etc/click"

EXPECTED_AUDIT = {
    "bin/pack/etc/ymir work/ui/pattern/gauge_red.tga": (
        556,
        "9103149090d0a1e8b1aa585d7fce31945d46fb44",
        "292ce483c19520bb6d32ba6b2f4dc8cb11cd162ffdbb18437fa52528852b25d3",
    ),
    f"{EFFECT_DIRECTORY}/click_select.mse": (
        1327,
        "4e92d200f9b3ac0d54c0930c12fa3b483a55fbc0",
        "9e6e3315487cdea2811330d40d40316d2bc3eb40b15f149464b4776640542048",
    ),
    f"{EFFECT_DIRECTORY}/click_glow_select.mse": (
        2744,
        "519d85b4dde8d9c57e6803b145124d6cf4fabe01",
        "f43ec501bc3bc98d22cf4fea807f6e9c123caff4ede09326781fffe563ec05fd",
    ),
    f"{EFFECT_DIRECTORY}/click_select.mde": (
        19547,
        "726025d49b9b723a45e5143716cf6b97aa70f539",
        "14a1180b306113716d14cdf7fda4bfa014197150754507a076b6d3c02d06614f",
    ),
    f"{EFFECT_DIRECTORY}/click_glow_select.mde": (
        19547,
        "46cc3efa387eac1c473d6cff10eeac335ba32647",
        "7f2dfbbe7c32c4672349342079711639a6ebe1f9951ecf838e361a0c9e88d4d1",
    ),
    f"{EFFECT_DIRECTORY}/click_select_vertical.tga": (
        32812,
        "82f1f47dc53ed11e9b89019b5e4f788cf3a73285",
        "3ccecde2d445ddddde2ad9aca6571c46f58e7ff41bcda68a60560d64a704e89e",
    ),
    f"{EFFECT_DIRECTORY}/click_select.tga": (
        65580,
        "4c009b84e54bcc71985fe319354aa993790ac904",
        "e329212f2b164733552a3bf9b3b515e82b459071cba789cc539f3eafc5b3d2c0",
    ),
    f"{EFFECT_DIRECTORY}/click_glow_select_vertical copy.jpg": (
        11722,
        "6c35623a5b5187cee77533e2d0023499b7885e31",
        "3796d867113da782bbc49cb93f8f4b393f9314f716c3731dae67f2102906c195",
    ),
    f"{EFFECT_DIRECTORY}/click_glow_select copy.jpg": (
        15516,
        "d7a9cce0b4d726f89982869cc0d3b31093c1db3a",
        "62a14e2c130c53bff0580b61aabbca29ded663de108dc628730c24247b3e27d4",
    ),
}

EFFECTS = {
    "click_select": {
        "effect_id": "effect.actor.hover.v1",
        "semantic_role": "hover_candidate",
        "registration": "EFFECT_SELECT",
        "expected_mesh_files": ["click_select.mde"],
    },
    "click_glow_select": {
        "effect_id": "effect.actor.target.v1",
        "semantic_role": "combat_target",
        "registration": "EFFECT_TARGET",
        "expected_mesh_files": ["click_select.mde", "click_glow_select.mde"],
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def canonical_hash(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def expected_virtual_path(archive_path: str) -> str:
    for prefix in ("bin/pack/Effect/", "bin/pack/etc/"):
        if archive_path.startswith(prefix):
            return "d:/" + archive_path.removeprefix(prefix)
    raise ValueError(f"No pinned virtual-path rule for {archive_path}")


def verify_sources(audit_path: Path | None, source_root: Path) -> dict[str, dict]:
    pinned_records = [
        {
            "archive_path": archive_path,
            "bytes": size,
            "git_blob_sha1": blob,
            "sha256": digest,
            "virtual_path": expected_virtual_path(archive_path),
        }
        for archive_path, (size, blob, digest) in EXPECTED_AUDIT.items()
    ]
    audit_report = None
    if audit_path is not None:
        audit_bytes = audit_path.read_bytes()
        audit = json.loads(audit_bytes)
        if audit.get("repository") != REPOSITORY or audit.get("commit") != METIN_COMMIT:
            raise ValueError("Target-effect audit repository/revision mismatch")
        indexed = {entry["archive_path"]: entry for entry in audit.get("files", [])}
        if set(indexed) != set(EXPECTED_AUDIT):
            raise ValueError("Target-effect audit must contain exactly the nine pinned records")
        for expected in pinned_records:
            entry = indexed[expected["archive_path"]]
            actual = {
                "archive_path": entry.get("archive_path"),
                "bytes": entry.get("bytes"),
                "git_blob_sha1": entry.get("git_sha"),
                "sha256": entry.get("sha256"),
                "virtual_path": entry.get("virtual_path"),
            }
            if actual != expected:
                raise ValueError(f"Pinned audit values changed for {expected['archive_path']}")
        audit_report = {"path": str(audit_path), "sha256": sha256(audit_bytes)}
    verified = {}
    for expected in pinned_records:
        archive_path = expected["archive_path"]
        path = source_root / archive_path
        data = path.read_bytes()
        if (
            len(data) != expected["bytes"]
            or sha256(data) != expected["sha256"]
            or git_blob_sha(data) != expected["git_blob_sha1"]
        ):
            raise ValueError(f"Pinned source bytes do not match audit: {archive_path}")
        verified[archive_path] = expected
    return {
        "pinned_metadata_sha256": canonical_hash(
            {"repository": REPOSITORY, "commit": METIN_COMMIT, "files": pinned_records}
        ),
        "optional_audit_report": audit_report,
        "files": verified,
    }


def fetch_sources(source_root: Path) -> None:
    """Fetch only the tracked, hash-pinned source fixture into the ignored source cache."""
    archive = Archive()
    archive.sources = source_root
    archive.inventory()
    archive.fetch_many(EXPECTED_AUDIT)


def normalized_virtual(value: str) -> str:
    value = value.replace("\\", "/").lower()
    if value.startswith("d:/"):
        value = value[3:]
    return value


def image_target(source_name: str) -> Path:
    stem = Path(source_name).stem.lower().replace(" ", "_")
    return Path("textures") / f"{stem}.png"


def convert_image(source: Path, target: Path) -> dict:
    with Image.open(source) as original:
        rgba = original.convert("RGBA")
        source_mode = original.mode
        source_size = list(original.size)
    target.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(target, format="PNG", compress_level=9, optimize=False)
    with Image.open(target) as reopened:
        decoded = reopened.convert("RGBA")
        if decoded.size != rgba.size or decoded.tobytes() != rgba.tobytes():
            raise ValueError(f"PNG round trip changed decoded pixels: {target}")
    return {
        "resource": target.relative_to(target.parents[1]).as_posix(),
        "width": source_size[0],
        "height": source_size[1],
        "source_mode": source_mode,
        "rgba_sha256": sha256(rgba.tobytes()),
        "png_sha256": sha256(target.read_bytes()),
    }


def frame_payload(frame) -> dict:
    return {
        "visibility": frame.visibility,
        "positions": frame.positions,
        "position_indices": frame.position_indices,
        "texture_coordinates": frame.texture_coordinates,
        "texture_indices": frame.texture_indices,
    }


def validate_mde(name: str, mde: MdeFile) -> None:
    if mde.version != 1 or mde.frame_count != 11:
        raise ValueError(f"{name} must be an 11-frame MDE v001")
    expected = (("Cylinder01", 36, 108), ("Plane01", 4, 6))
    actual = tuple(
        (geometry.name, len(geometry.frames[0].positions), len(geometry.frames[0].position_indices))
        for geometry in mde.geometries
    )
    if actual != expected:
        raise ValueError(f"Unexpected {name} geometry contract: {actual}")


def validate_mse(name: str, mse: MseFile) -> None:
    expected = EFFECTS[name]["expected_mesh_files"]
    if [mesh.mesh_file for mesh in mse.meshes] != expected:
        raise ValueError(f"Unexpected {name} mesh layers")
    expected_destinations = [6 if mesh_file == "click_select.mde" else 2 for mesh_file in expected]
    for mesh, expected_destination in zip(mse.meshes, expected_destinations, strict=True):
        if (
            mesh.start_time != 0.0
            or mesh.frame_delay != 0.02
            or not mesh.animation_loop
            or mesh.animation_loop_count != 0
            or mesh.position_events[0].position != (0.0, 0.0, 41.60334)
            or len(mesh.position_events) != 1
            or len(mesh.elements) != 2
        ):
            raise ValueError(f"Unexpected playback contract in {name}/{mesh.mesh_file}")
        for element in mesh.elements:
            if (
                not element.blending_enabled
                or element.blending_source != 5
                or element.blending_destination != expected_destination
                or not element.texture_animation_loop
                or element.texture_frame_delay != 0.02
                or element.texture_start_frame != 0
                or element.color_operation != 4
                or element.color_factor != (1.0, 0.054902, 0.0, 1.0)
                or element.alpha_events
            ):
                raise ValueError(f"Unexpected material contract in {name}/{mesh.mesh_file}")


def parse_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError(f"Truncated GLB: {path}")
    magic, version, total = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or total != len(data):
        raise ValueError(f"Invalid GLB header: {path}")
    offset = 12
    chunks = {}
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        chunks[kind] = data[offset : offset + length]
        offset += length
    if offset != len(data) or 0x4E4F534A not in chunks or 0x004E4942 not in chunks:
        raise ValueError(f"Invalid GLB chunks: {path}")
    return json.loads(chunks[0x4E4F534A].rstrip(b" \0")), chunks[0x004E4942]


def accessor_floats(document: dict, binary: bytes, index: int) -> tuple[float, ...]:
    accessor = document["accessors"][index]
    if accessor["componentType"] != 5126:
        raise ValueError("Expected float GLB accessor")
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    count = accessor["count"]
    if type(count) is not int or not 0 <= count <= 1_000_000:
        raise ValueError("Invalid GLB accessor count")

    def read(view_id, offset, items, width, code, size, *, packed=False):
        view = document["bufferViews"][view_id]
        stride = view.get("byteStride", width * size)
        start = view.get("byteOffset", 0)
        length = view["byteLength"]
        if (
            view.get("buffer", 0) != 0
            or min(offset, start, length) < 0
            or stride < width * size
            or (packed and stride != width * size)
            or start + length > len(binary)
            or offset + (items - 1) * stride + width * size > length
        ):
            raise ValueError("GLB accessor exceeds its buffer view")
        result = []
        for item in range(items):
            result.extend(
                struct.unpack_from(f"<{width}{code}", binary, start + offset + item * stride)
            )
        return result

    result = (
        read(accessor["bufferView"], accessor.get("byteOffset", 0), count, components, "f", 4)
        if "bufferView" in accessor
        else [0.0] * (count * components)
    )
    if sparse := accessor.get("sparse"):
        amount = sparse["count"]
        if type(amount) is not int or not 1 <= amount <= count:
            raise ValueError("Invalid sparse GLB count")
        indices, values = sparse["indices"], sparse["values"]
        code, size = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}[indices["componentType"]]
        slots = read(
            indices["bufferView"], indices.get("byteOffset", 0), amount, 1, code, size, packed=True
        )
        if any(i >= count for i in slots) or any(
            a >= b for a, b in zip(slots, slots[1:], strict=False)
        ):
            raise ValueError("Sparse GLB indices must increase within the accessor")
        replacements = read(
            values["bufferView"],
            values.get("byteOffset", 0),
            amount,
            components,
            "f",
            4,
            packed=True,
        )
        for item, slot in enumerate(slots):
            result[slot * components : (slot + 1) * components] = replacements[
                item * components : (item + 1) * components
            ]
    return tuple(result)


def audit_glb(
    path: Path, mde: MdeFile, *, position_cm=(0.0, 0.0, 41.60334), frame_delay=0.02
) -> dict:
    document, binary = parse_glb(path)
    meshes = document.get("meshes", [])
    if len(meshes) != 1 or len(meshes[0].get("primitives", [])) != len(mde.geometries):
        raise ValueError(f"GLB must retain its source material primitives: {path}")
    scenes = document.get("scenes", [])
    nodes = document.get("nodes", [])
    scene_index = document.get("scene")
    if scene_index != 0 or len(scenes) != 1 or scenes[0].get("nodes") != [0]:
        raise ValueError(f"GLB must contain one active scene with one root node: {path}")
    if len(nodes) != 1 or nodes[0].get("mesh") != 0 or nodes[0].get("children"):
        raise ValueError(f"GLB mesh must be the only root node: {path}")
    node = nodes[0]
    identity_matrix = [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    ]
    if (
        node.get("matrix", identity_matrix) != identity_matrix
        or node.get("translation", [0.0, 0.0, 0.0]) != [0.0, 0.0, 0.0]
        or node.get("rotation", [0.0, 0.0, 0.0, 1.0]) != [0.0, 0.0, 0.0, 1.0]
        or node.get("scale", [1.0, 1.0, 1.0]) != [1.0, 1.0, 1.0]
    ):
        raise ValueError(f"GLB root mesh node must have an identity transform: {path}")
    actual_uv_count = 0
    target_count = None
    material_geometries = {
        index: material["name"].rsplit(".", 1)[-1]
        for index, material in enumerate(document.get("materials", []))
    }
    position_frames = {geometry.name: [] for geometry in mde.geometries}
    for primitive in meshes[0]["primitives"]:
        values = accessor_floats(document, binary, primitive["attributes"]["TEXCOORD_0"])
        geometry_name = material_geometries.get(primitive.get("material"))
        if geometry_name not in position_frames:
            raise ValueError("GLB primitive material no longer identifies its source geometry")
        geometry = next(item for item in mde.geometries if item.name == geometry_name)
        source_frame = geometry.frames[0]
        actual_uv = tuple(
            (round(values[index], 5), round(values[index + 1], 5))
            for index in range(0, len(values), 2)
        )
        expected_uv = tuple(
            (
                round(source_frame.texture_coordinates[texture_index][0], 5),
                round(1.0 - source_frame.texture_coordinates[texture_index][1], 5),
            )
            for texture_index in source_frame.texture_indices
        )
        if actual_uv != expected_uv:
            raise ValueError(f"GLB corner UV correspondence changed for {geometry_name}")
        actual_uv_count += len(actual_uv)
        base = accessor_floats(document, binary, primitive["attributes"]["POSITION"])
        position_frames[geometry_name].append(base)
        for target in primitive.get("targets", []):
            delta = accessor_floats(document, binary, target["POSITION"])
            position_frames[geometry_name].append(
                tuple(base[index] + delta[index] for index in range(len(base)))
            )
        primitive_targets = len(primitive.get("targets", []))
        target_count = primitive_targets if target_count is None else target_count
        if primitive_targets != target_count:
            raise ValueError("GLB primitives disagree on morph-target count")
    if target_count != mde.frame_count - 1:
        raise ValueError(f"Expected {mde.frame_count - 1} GLB morph targets, got {target_count}")
    max_position_error_m = 0.0
    for geometry in mde.geometries:
        if len(position_frames[geometry.name]) != mde.frame_count:
            raise ValueError(f"GLB frame count changed for {geometry.name}")
        for frame_index, actual_values in enumerate(position_frames[geometry.name]):
            source_frame = geometry.frames[frame_index]
            expected_values = []
            for position_index in source_frame.position_indices:
                x, y, z = source_frame.positions[position_index]
                expected_values.extend(
                    (
                        (x + position_cm[0]) / 100.0,
                        (z + position_cm[2]) / 100.0,
                        -(y + position_cm[1]) / 100.0,
                    )
                )
            if len(actual_values) != len(expected_values):
                raise ValueError(
                    f"GLB position count changed in {geometry.name} frame {frame_index}"
                )
            frame_error = max(
                abs(actual - expected)
                for actual, expected in zip(actual_values, expected_values, strict=True)
            )
            max_position_error_m = max(max_position_error_m, frame_error)
            if frame_error > 0.000_02:
                raise ValueError(
                    f"Blender/glTF coordinate transform mismatch in {geometry.name} frame {frame_index}"
                )
    animations = document.get("animations", [])
    if not animations:
        raise ValueError("GLB has no mesh-frame animation")
    interpolation = {
        sampler.get("interpolation", "LINEAR")
        for animation in animations
        for sampler in animation["samplers"]
    }
    if interpolation != {"STEP"}:
        raise ValueError(f"GLB frame animation is not constant/STEP: {interpolation}")
    times = []
    for animation in animations:
        for sampler in animation["samplers"]:
            times.extend(accessor_floats(document, binary, sampler["input"]))
    if (
        not times
        or abs(min(times)) > 1e-7
        or abs(max(times) - mde.frame_count * frame_delay) > 1e-6
    ):
        raise ValueError(f"GLB animation boundary mismatch: {min(times)}..{max(times)}")
    weight_samplers = [
        animation["samplers"][channel["sampler"]]
        for animation in animations
        for channel in animation["channels"]
        if channel["target"]["path"] == "weights"
    ]
    if len(weight_samplers) != 1:
        raise ValueError(f"Expected one GLB weight sampler, got {len(weight_samplers)}")
    weights = accessor_floats(document, binary, weight_samplers[0]["output"])
    expected_weights = []
    for timeline_frame in range(mde.frame_count + 1):
        active_frame = timeline_frame if timeline_frame < mde.frame_count else 0
        expected_weights.extend(
            1.0 if source_frame == active_frame else 0.0
            for source_frame in range(1, mde.frame_count)
        )
    if tuple(weights) != tuple(expected_weights):
        raise ValueError("GLB morph-weight sequence is not the expected discrete frame cycle")
    return {
        "sha256": sha256(path.read_bytes()),
        "bytes": path.stat().st_size,
        "morph_targets": target_count,
        "animation_count": len(animations),
        "animation_start_s": min(times),
        "animation_end_s": max(times),
        "animation_interpolation": "STEP",
        "uv_transform": "raw MDE UV assigned in Blender; glTF TEXCOORD_0 equals (u, 1-v)",
        "uv_audit_tolerance": "rounded to 5 decimal places after Blender float32 storage",
        "uv_value_count": actual_uv_count,
        "coordinate_transform": "source centimeters XYZ -> glTF/Godot meters (x,z,-y)",
        "scene_graph_audit": "one active scene, one root mesh node, identity world transform",
        "root_node_transform": {
            "translation": [0.0, 0.0, 0.0],
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "max_position_readback_error_m": max_position_error_m,
        "position_readback_tolerance_m": 0.000_02,
        "morph_weight_sequence": f"frames 0..{mde.frame_count - 1} one-hot, frame {mde.frame_count} returns to frame 0",
    }


def run_blender(executable: Path, input_path: Path, output: Path, work: Path) -> dict:
    report = work / "blender-report.json"
    log = work / "blender.log"
    command = [
        str(executable),
        "--background",
        "--factory-startup",
        "-setaudio",
        "None",
        "--python-exit-code",
        "1",
        "--python",
        str(ROOT / "tools/blender_target_effects.py"),
        "--",
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--report",
        str(report),
    ]
    with log.open("w") as stream:
        subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    result = json.loads(report.read_text())
    result["log"] = str(log)
    return result


def material_sidecar(asset_name: str, mde: MdeFile, texture_resources: dict[str, str]) -> dict:
    blend = "alpha" if asset_name == "click_select" else "additive_source_alpha"
    destination = 6 if blend == "alpha" else 2
    materials = []
    tint = [d3dx_color_byte(value) for value in (1.0, 0.054902, 0.0, 1.0)]
    for geometry in mde.geometries:
        materials.append(
            {
                "geometry": geometry.name,
                "texture": texture_resources[normalized_virtual(geometry.texture_path)],
                "source_texture_factor_srgba8": tint,
                "source_color_operation": {"value": 4, "name": "D3DTOP_MODULATE"},
                "source_blend": {
                    "source": {"value": 5, "name": "D3DBLEND_SRCALPHA"},
                    "destination": {
                        "value": destination,
                        "name": "D3DBLEND_INVSRCALPHA" if destination == 6 else "D3DBLEND_ONE",
                    },
                },
                "godot_material": {
                    "blend": "blend_mix" if destination == 6 else "blend_add",
                    "unshaded": True,
                    "cull_disabled": True,
                    "depth_draw": "never",
                    "depth_test": "enabled",
                    "texture_repeat": True,
                },
                "frame_alpha": [
                    {
                        "source_float32": frame.visibility,
                        "effective_u8": d3dx_color_byte(frame.visibility),
                        "effective": d3dx_color_byte(frame.visibility) / 255.0,
                    }
                    for frame in geometry.frames
                ],
            }
        )
    return {
        "schema": "mt2spacetime.target-effect-materials",
        "schema_version": 1,
        "asset_id": asset_name,
        "materials": materials,
        "application": "Override both imported GLB surfaces and update frame_alpha per frame",
    }


def runtime_catalog(output: Path, models: dict, textures: dict, sidecars: dict) -> dict:
    packaged = sorted(
        [entry["resource"] for entry in models.values()]
        + [entry["resource"] for entry in textures.values()]
    )
    files = {
        relative: {
            "bytes": (output / relative).stat().st_size,
            "sha256": sha256((output / relative).read_bytes()),
        }
        for relative in packaged
    }
    assets = []
    for asset_id in ("click_select", "click_glow_select"):
        sidecar = json.loads((output / sidecars[asset_id]["resource"]).read_text())
        assets.append(
            {
                "id": asset_id,
                "model": models[asset_id]["resource"],
                "surfaces": [
                    {
                        "index": index,
                        "geometry": material["geometry"],
                        "texture": material["texture"],
                        "tint_srgba8": material["source_texture_factor_srgba8"],
                        "blend": (
                            "source_alpha_inverse_source_alpha"
                            if material["godot_material"]["blend"] == "blend_mix"
                            else "source_alpha_one"
                        ),
                        "unshaded": True,
                        "cull_disabled": True,
                        "depth_draw": False,
                        "depth_test": True,
                        "texture_repeat": True,
                        "frame_alpha_u8": [
                            frame["effective_u8"] for frame in material["frame_alpha"]
                        ],
                    }
                    for index, material in enumerate(sidecar["materials"])
                ],
            }
        )
    catalog = {
        "schema": "mt2spacetime.target-effect-catalog",
        "schema_version": 1,
        "resource_root": RUNTIME_RESOURCE_ROOT,
        "files": files,
        "playback": {
            "frame_count": 11,
            "frame_us": 20_000,
            "loop": True,
            "advance_boundary": "strict_remaining_lt_zero",
            "max_advances_per_tick": 20,
            "geometry_interpolation": "none",
        },
        "assets": assets,
        "effects": [
            {
                "id": "effect.actor.hover.v1",
                "attachment_space": "actor_local",
                "runtime_offset_m": [0.0, 0.0, 0.0],
                "layers": ["click_select"],
            },
            {
                "id": "effect.actor.target.v1",
                "attachment_space": "actor_local",
                "runtime_offset_m": [0.0, 0.0, 0.0],
                "layers": ["click_select", "click_glow_select"],
            },
        ],
    }
    catalog["content_hash"] = canonical_hash(catalog)
    return catalog


def install_runtime(output: Path) -> list[str]:
    catalog = json.loads((output / "runtime-catalog.v1.json").read_text())
    packaged = ["runtime-catalog.v1.json", *sorted(catalog["files"])]
    if INSTALL_ROOT.exists():
        shutil.rmtree(INSTALL_ROOT)
    for relative in packaged:
        source = output / relative
        destination = INSTALL_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return packaged


def build(args) -> dict:
    output_boundary = (ROOT / ".local/p2-target/effects").resolve()
    resolved_output = args.output.resolve()
    if resolved_output == output_boundary or output_boundary not in resolved_output.parents:
        raise ValueError("Output must be a child of .local/p2-target/effects")
    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    verified = verify_sources(args.audit, args.source_root)
    parsed_mde = {}
    parsed_mse = {}
    for name in EFFECTS:
        mde_path = args.source_root / EFFECT_DIRECTORY / f"{name}.mde"
        mse_path = args.source_root / EFFECT_DIRECTORY / f"{name}.mse"
        parsed_mde[name] = parse_mde(mde_path.read_bytes())
        parsed_mse[name] = parse_mse(mse_path.read_text(encoding="ascii"))
        validate_mde(name, parsed_mde[name])
        validate_mse(name, parsed_mse[name])

    virtual_sources = {
        entry["virtual_path"].replace("d:/", "").lower(): archive_path
        for archive_path, entry in verified["files"].items()
    }
    texture_resources = {}
    textures = {}
    for mde in parsed_mde.values():
        for geometry in mde.geometries:
            virtual = normalized_virtual(geometry.texture_path)
            archive_path = virtual_sources.get(virtual)
            if archive_path is None:
                raise ValueError(
                    f"MDE texture is outside the pinned fixture: {geometry.texture_path}"
                )
            relative = image_target(Path(archive_path).name)
            texture_resources[virtual] = relative.as_posix()
            if relative.as_posix() not in textures:
                textures[relative.as_posix()] = {
                    "source": verified["files"][archive_path],
                    **convert_image(args.source_root / archive_path, args.output / relative),
                }

    blender_assets = []
    for name, mde in parsed_mde.items():
        mesh = parsed_mse[name].meshes[-1]
        blender_assets.append(
            {
                "id": name,
                "position_cm": mesh.position_events[0].position,
                "frames": list(range(mde.frame_count)),
                "geometries": [
                    {
                        "name": geometry.name,
                        "texture_resource": texture_resources[
                            normalized_virtual(geometry.texture_path)
                        ],
                        "frames": [frame_payload(frame) for frame in geometry.frames],
                    }
                    for geometry in mde.geometries
                ],
            }
        )
    blender_input = args.work / "blender-input.json"
    write_json(blender_input, {"assets": blender_assets})
    blender_report = run_blender(args.blender, blender_input, args.output, args.work)

    models = {}
    sidecars = {}
    for name, mde in parsed_mde.items():
        glb_relative = Path("models") / f"{name}.glb"
        models[name] = {
            "resource": glb_relative.as_posix(),
            **audit_glb(args.output / glb_relative, mde),
        }
        sidecar = material_sidecar(name, mde, texture_resources)
        sidecar_relative = Path("materials") / f"{name}.materials.v1.json"
        write_json(args.output / sidecar_relative, sidecar)
        sidecars[name] = {
            "resource": sidecar_relative.as_posix(),
            "sha256": sha256((args.output / sidecar_relative).read_bytes()),
        }

    effects = []
    for name, definition in EFFECTS.items():
        mse = parsed_mse[name]
        mse_source_path = f"{EFFECT_DIRECTORY}/{name}.mse"
        layers = []
        for index, mesh in enumerate(mse.meshes):
            asset_name = Path(mesh.mesh_file).stem
            destination = mesh.elements[0].blending_destination
            layers.append(
                {
                    "index": index,
                    "asset_id": asset_name,
                    "model": models[asset_name]["resource"],
                    "material_sidecar": sidecars[asset_name]["resource"],
                    "blend": "source_alpha_inverse_source_alpha"
                    if destination == 6
                    else "source_alpha_one",
                    "simultaneous": True,
                }
            )
        effects.append(
            {
                **definition,
                "source": verified["files"][mse_source_path],
                "layers": layers,
                "frame_count": 11,
                "frame_us": 20_000,
                "cycle_us": 220_000,
                "loop": True,
                "attachment": {
                    "space": "actor_local",
                    "source_element_position_cm": [0.0, 0.0, 41.60334],
                    "source_element_position_baked_into_model_vertices": True,
                    "runtime_attachment_offset_m": [0.0, 0.0, 0.0],
                    "billboard": False,
                    "ground_plane_oriented": True,
                },
            }
        )

    manifest = {
        "schema": "mt2spacetime.target-effect-assets",
        "schema_version": 1,
        "source": {
            "repository": REPOSITORY,
            "commit": METIN_COMMIT,
            "pinned_metadata_sha256": verified["pinned_metadata_sha256"],
            "inputs": list(verified["files"].values()),
            "excluded_fixture_input": "d:/ymir work/ui/pattern/gauge_red.tga",
        },
        "converter": {
            "driver": "tools/import_target_effects.py",
            "blender_helper": "tools/blender_target_effects.py",
            "pillow_version": pillow_version,
            "blender_version": blender_report["blender_version"],
        },
        "effects": effects,
        "models": models,
        "textures": textures,
        "material_sidecars": sidecars,
        "playback": {
            "source_boundary": "advance only when remaining frame time is strictly less than zero",
            "source_max_frame_advances_per_update": 20,
            "source_geometry_interpolation": "none",
            "source_loop_count_zero_with_loop_enabled": "infinite",
            "glb_interpolation": "STEP",
            "glb_cycle_boundary_s": 0.22,
            "bounded_divergence": (
                "At an update landing exactly on a 20 ms boundary, the source keeps the prior frame "
                "until elapsed time becomes greater; an ordinary STEP GLB changes at that boundary."
            ),
        },
        "render_contract": {
            "source_texture_stage_color": "texture * D3DXCOLOR texture factor",
            "source_texture_stage_alpha": "texture alpha * quantized frame visibility",
            "source_alpha_quantization": (
                "D3DXCOLOR DWORD cast: <=0 to 0, >=1 to 255, otherwise int(value*255+0.5)"
            ),
            "source_uv": "MDE paired position/texture indices; renderer multiplies V by -1",
            "source_culling": "disabled",
            "source_depth_write": "disabled",
            "source_depth_test": "retained",
            "color_space_limit": (
                "Pinned client code contains no explicit effect-local sRGB state; Godot texture/color "
                "conversion can differ from Direct3D9 fixed-function gamma-space multiplication."
            ),
            "blend_limit": (
                "glTF has no additive material mode; exact requested Godot settings are in sidecars."
            ),
        },
        "unsupported": [
            "MDEData002 and any MDE version except EffectData v001",
            "particles, lights, sounds and non-mesh MSE groups",
            "billboards, bezier movement and texture animation lists",
            "blend pairs and color operations outside the two pinned effects",
            "runtime target ownership, selection and lifecycle behavior",
        ],
    }
    output_hashes = {
        relative: sha256((args.output / relative).read_bytes())
        for relative in sorted(
            [entry["resource"] for entry in models.values()]
            + [entry["resource"] for entry in textures.values()]
            + [entry["resource"] for entry in sidecars.values()]
        )
    }
    manifest["output_hashes"] = output_hashes
    manifest["content_hash"] = canonical_hash(manifest)
    write_json(args.output / "manifest.v1.json", manifest)

    catalog = runtime_catalog(args.output, models, textures, sidecars)
    write_json(args.output / "runtime-catalog.v1.json", catalog)

    runtime_contract = {
        "schema": "mt2spacetime.target-effect-runtime-attachment-contract",
        "schema_version": 1,
        "hover": (
            "effect.actor.hover.v1 is transient and exists only while pointer picking resolves a valid actor"
        ),
        "combat_target": (
            "effect.actor.target.v1 attaches only after the owner-private server target row accepts "
            "the exact monster id and life_sequence; its two layers run simultaneously"
        ),
        "clear_on": [
            "pointer no longer resolves the hover actor (hover only)",
            "explicit target clear",
            "target death or life-generation change",
            "target removal from subscription",
            "own death",
            "leave, character switch, logout or disconnect",
        ],
        "reconnect": "starts with no target",
        "ground_movement": "does not itself clear an existing combat target",
        "same_actor_composition": (
            "preserve both effect IDs when hover and accepted target name the same actor; the target's "
            "two internal layers remain one target-effect instance"
        ),
        "instance_lifetime": (
            "preserve an attached instance through HP and position updates and same-target renewals; "
            "reset only when role, actor id or life_sequence changes, or on actual detach"
        ),
        "first_slice_attack": "target selection followed by Space; no third attack-flash effect",
    }
    write_json(args.output / "runtime-attachment-contract.v1.json", runtime_contract)
    report = {
        "status": "converted",
        "manifest": str(args.output / "manifest.v1.json"),
        "runtime_contract": str(args.output / "runtime-attachment-contract.v1.json"),
        "runtime_catalog": str(args.output / "runtime-catalog.v1.json"),
        "runtime_catalog_content_hash": catalog["content_hash"],
        "content_hash": manifest["content_hash"],
        "models": models,
        "blender": blender_report,
        "source_verification": {
            "pinned_metadata_sha256": verified["pinned_metadata_sha256"],
            "optional_audit_report": verified["optional_audit_report"],
        },
    }
    write_json(args.work / "conversion-report.json", report)
    return report


def default_godot() -> Path:
    return next((path for path in GODOT_CANDIDATES if path.is_file()), GODOT_CANDIDATES[-1])


def run_preview(godot: Path, output: Path, work: Path) -> dict:
    project = work / "preview-project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(output, project)
    (project / "project.godot").write_text(
        '[application]\nconfig/name="TargetEffectPreview"\nrun/main_scene=""\n'
        "[display]\nwindow/size/viewport_width=960\nwindow/size/viewport_height=540\n"
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )
    environment = dict(os.environ)
    for variable, folder in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config")):
        directory = work / "godot" / folder
        directory.mkdir(parents=True, exist_ok=True)
        environment[variable] = str(directory)
    log = work / "godot-preview.log"
    command = [
        str(godot),
        "--headless",
        "--path",
        str(project),
        "--import",
        "--quit-after",
        "2",
    ]
    first = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    log.write_text(first.stdout)
    if first.returncode or "ERROR:" in first.stdout:
        raise RuntimeError(f"Godot preview import failed; see {log}")
    # Rendering is delegated to a tracked, narrowly scoped Godot script so the
    # generated project contains no reusable runtime evaluator or bridge.
    command = [
        "xvfb-run",
        "-a",
        str(godot),
        "--display-driver",
        "x11",
        "--rendering-method",
        "gl_compatibility",
        "--audio-driver",
        "Dummy",
        "--path",
        str(project),
        "--script",
        str(ROOT / "tools/render_target_effects.gd"),
        "--",
        str(project / "manifest.v1.json"),
        str(work / "preview-corrected"),
    ]
    second = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    with log.open("a") as stream:
        stream.write(second.stdout)
    if second.returncode or "ERROR:" in second.stdout:
        raise RuntimeError(f"Godot preview render failed; see {log}")
    preview_report = json.loads((work / "preview-corrected/report.json").read_text())
    if preview_report.get("status") != "rendered" or len(preview_report.get("captures", [])) != 4:
        raise RuntimeError("Godot preview did not produce the four required rendered captures")
    preview_report["godot_log"] = str(log)
    write_json(work / "preview-report.json", preview_report)
    return preview_report


def run_geometry_check(godot: Path, output: Path, work: Path) -> dict:
    project = work / "preview-project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(output, project)
    (project / "project.godot").write_text(
        '[application]\nconfig/name="TargetEffectPreview"\nrun/main_scene=""\n'
        "[display]\nwindow/size/viewport_width=960\nwindow/size/viewport_height=540\n"
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )
    geometry_output = work / "preview-geometry"
    environment = dict(os.environ)
    for variable, folder in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config")):
        directory = work / "godot" / folder
        directory.mkdir(parents=True, exist_ok=True)
        environment[variable] = str(directory)
    log = work / "godot-geometry.log"
    imported = subprocess.run(
        [
            str(godot),
            "--headless",
            "--path",
            str(project),
            "--import",
            "--quit-after",
            "2",
        ],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    log.write_text(imported.stdout)
    if imported.returncode or "ERROR:" in imported.stdout:
        raise RuntimeError(f"Godot geometry import failed; see {log}")
    result = subprocess.run(
        [
            str(godot),
            "--headless",
            "--rendering-method",
            "gl_compatibility",
            "--audio-driver",
            "Dummy",
            "--path",
            str(project),
            "--script",
            str(ROOT / "tools/render_target_effects.gd"),
            "--",
            str(project / "manifest.v1.json"),
            str(geometry_output),
        ],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    with log.open("a") as stream:
        stream.write(result.stdout)
    if result.returncode or "ERROR:" in result.stdout or "SCRIPT ERROR:" in result.stdout:
        raise RuntimeError(f"Godot geometry check failed; see {log}")
    report = json.loads((geometry_output / "report.json").read_text())
    if (
        report.get("status") != "geometry_checked_headless"
        or len(report.get("imported_geometry", [])) != 3
    ):
        raise RuntimeError("Godot geometry check did not inspect the three effect layers")
    report["godot_log"] = str(log)
    write_json(work / "geometry-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit",
        type=Path,
        help=(
            "Optional extraction audit to verify in addition to tracked pinned metadata; "
            f"for example {AUDIT.relative_to(ROOT)}"
        ),
    )
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch exactly the pinned source fixture before offline conversion",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--godot", type=Path, default=default_godot())
    qa = parser.add_mutually_exclusive_group()
    qa.add_argument("--render", action="store_true", help="Render isolated Godot QA samples")
    qa.add_argument(
        "--geometry-only",
        action="store_true",
        help="Read imported Godot transforms and bounds without claiming rendered QA",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install only the bounded runtime catalog, two GLBs, and four PNGs",
    )
    args = parser.parse_args()
    if args.fetch:
        fetch_sources(args.source_root)
    if not args.blender.is_file():
        parser.error(f"Blender executable not found: {args.blender}")
    report = build(args)
    if args.render:
        if not args.godot.is_file():
            parser.error(f"Godot executable not found: {args.godot}")
        report["preview"] = run_preview(args.godot, args.output, args.work)
        write_json(args.work / "conversion-report.json", report)
    elif args.geometry_only:
        if not args.godot.is_file():
            parser.error(f"Godot executable not found: {args.godot}")
        report["geometry"] = run_geometry_check(args.godot, args.output, args.work)
        write_json(args.work / "conversion-report.json", report)
    if args.install:
        report["installed"] = {
            "root": str(INSTALL_ROOT),
            "files": install_runtime(args.output),
        }
        write_json(args.work / "conversion-report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
