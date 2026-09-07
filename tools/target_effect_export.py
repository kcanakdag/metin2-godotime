"""Preflight and actual-PCK qualification for the bounded target-effect package."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

RESOURCE_ROOT = "res://assets/imported/content/p2-target-effects"
RELATIVE_ROOT = Path("assets/imported/content/p2-target-effects")
CATALOG_NAME = "runtime-catalog.v1.json"
MODEL_PATHS = (
    "models/click_glow_select.glb",
    "models/click_select.glb",
)
TEXTURE_PATHS = (
    "textures/click_glow_select_copy.png",
    "textures/click_glow_select_vertical_copy.png",
    "textures/click_select.png",
    "textures/click_select_vertical.png",
)
FILE_PATHS = (*MODEL_PATHS, *TEXTURE_PATHS)
ASSET_IDS = ("click_select", "click_glow_select")
EFFECT_IDS = ("effect.actor.hover.v1", "effect.actor.target.v1")
FRAME_ALPHA = (
    (255, 255, 255, 255, 255, 255, 255, 249, 222, 182, 0),
    (255, 255, 255, 255, 255, 255, 255, 221, 164, 81, 0),
)
LOSSLESS_IMPORT = (
    '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\n\n'
    "[params]\ncompress/mode=0\nmipmaps/generate=false\n"
    "detect_3d/compress_to=0\nprocess/fix_alpha_border=false\n"
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run(command, log: Path, env, timeout=180):
    with log.open("w") as stream:
        try:
            result = subprocess.run(
                [str(part) for part in command],
                stdout=stream,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Command timed out after {timeout}s; see {log}") from error
    output = log.read_text(errors="replace")
    if result.returncode or "SCRIPT ERROR:" in output or "ERROR:" in output:
        raise RuntimeError(f"Command failed; see {log}\n{output[-5000:]}")
    return output


def _canonical_hash(value: dict) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise RuntimeError(f"Target-effect {label} has unknown or missing fields")


def _sha256(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError(f"Target-effect {label} must be a lowercase SHA-256 value")
    return value


def _integer(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Target-effect {label} must be an integer")
    if not float(value).is_integer() or not minimum <= value <= maximum:
        raise RuntimeError(f"Target-effect {label} is outside its accepted range")
    return int(value)


def _u8_vector(value, expected, label):
    if not isinstance(value, list) or len(value) != len(expected):
        raise RuntimeError(f"Target-effect {label} must contain {len(expected)} values")
    normalized = tuple(_integer(item, 0, 255, label) for item in value)
    if normalized != tuple(expected):
        raise RuntimeError(f"Target-effect {label} differs from the pinned fixture")


def _validate_surface(asset_id, surface_index, surface):
    _exact_keys(
        surface,
        {
            "index",
            "geometry",
            "texture",
            "tint_srgba8",
            "blend",
            "unshaded",
            "cull_disabled",
            "depth_draw",
            "depth_test",
            "texture_repeat",
            "frame_alpha_u8",
        },
        f"{asset_id} surface {surface_index}",
    )
    suffix = "_vertical" if surface_index == 0 else ""
    copy = "_copy" if asset_id == "click_glow_select" else ""
    expected_texture = f"textures/{asset_id}{suffix}{copy}.png"
    expected_blend = (
        "source_alpha_inverse_source_alpha" if asset_id == "click_select" else "source_alpha_one"
    )
    expected = {
        "index": surface_index,
        "geometry": "Cylinder01" if surface_index == 0 else "Plane01",
        "texture": expected_texture,
        "blend": expected_blend,
        "unshaded": True,
        "cull_disabled": True,
        "depth_draw": False,
        "depth_test": True,
        "texture_repeat": True,
    }
    for key, value in expected.items():
        if surface.get(key) != value or type(surface.get(key)) is not type(value):
            raise RuntimeError(f"Target-effect {asset_id} surface {surface_index} {key} changed")
    _u8_vector(surface["tint_srgba8"], (255, 14, 0, 255), f"{asset_id} tint")
    _u8_vector(
        surface["frame_alpha_u8"],
        FRAME_ALPHA[surface_index],
        f"{asset_id} surface {surface_index} alpha",
    )


def _validate_document(document):
    _exact_keys(
        document,
        {
            "schema",
            "schema_version",
            "resource_root",
            "content_hash",
            "files",
            "playback",
            "assets",
            "effects",
        },
        "catalog",
    )
    if (
        document["schema"] != "mt2spacetime.target-effect-catalog"
        or document["schema_version"] != 1
        or document["resource_root"] != RESOURCE_ROOT
    ):
        raise RuntimeError("Target-effect catalog schema, version, or resource root changed")
    claimed_hash = _sha256(document["content_hash"], "catalog content_hash")
    unhashed = {key: value for key, value in document.items() if key != "content_hash"}
    if _canonical_hash(unhashed) != claimed_hash:
        raise RuntimeError("Target-effect catalog content_hash does not match its document")

    files = document["files"]
    if not isinstance(files, dict) or tuple(files) != FILE_PATHS:
        raise RuntimeError("Target-effect catalog must declare exactly two GLBs and four PNGs")
    for relative in FILE_PATHS:
        record = files[relative]
        _exact_keys(record, {"bytes", "sha256"}, f"file record {relative}")
        _integer(record["bytes"], 1, 64 * 1024 * 1024, f"file size {relative}")
        _sha256(record["sha256"], f"file hash {relative}")

    playback = document["playback"]
    expected_playback = {
        "frame_count": 11,
        "frame_us": 20_000,
        "loop": True,
        "advance_boundary": "strict_remaining_lt_zero",
        "max_advances_per_tick": 20,
        "geometry_interpolation": "none",
    }
    _exact_keys(playback, expected_playback, "playback")
    if playback != expected_playback:
        raise RuntimeError("Target-effect playback contract changed")

    assets = document["assets"]
    if not isinstance(assets, list) or len(assets) != 2:
        raise RuntimeError("Target-effect catalog must contain exactly two ordered assets")
    for asset_index, asset_id in enumerate(ASSET_IDS):
        asset = assets[asset_index]
        _exact_keys(asset, {"id", "model", "surfaces"}, f"asset {asset_index}")
        if asset["id"] != asset_id or asset["model"] != f"models/{asset_id}.glb":
            raise RuntimeError("Target-effect asset ID, order, or model changed")
        if not isinstance(asset["surfaces"], list) or len(asset["surfaces"]) != 2:
            raise RuntimeError(f"Target-effect {asset_id} must contain exactly two surfaces")
        for surface_index, surface in enumerate(asset["surfaces"]):
            _validate_surface(asset_id, surface_index, surface)

    effects = document["effects"]
    if not isinstance(effects, list) or len(effects) != 2:
        raise RuntimeError("Target-effect catalog must contain exactly two ordered effects")
    for effect_index, effect_id in enumerate(EFFECT_IDS):
        effect = effects[effect_index]
        _exact_keys(
            effect,
            {"id", "attachment_space", "runtime_offset_m", "layers"},
            f"effect {effect_index}",
        )
        expected_layers = [ASSET_IDS[0]] if effect_index == 0 else list(ASSET_IDS)
        offset = effect["runtime_offset_m"]
        if (
            effect["id"] != effect_id
            or effect["attachment_space"] != "actor_local"
            or effect["layers"] != expected_layers
            or not isinstance(offset, list)
            or len(offset) != 3
            or any(type(value) not in (int, float) or value != 0 for value in offset)
        ):
            raise RuntimeError("Target-effect ID, attachment, offset, or layers changed")


def _decoded_image(path):
    try:
        with Image.open(path) as source:
            rgba = source.convert("RGBA")
            return {
                "width": rgba.width,
                "height": rgba.height,
                "rgba_sha256": _sha256_bytes(rgba.tobytes()),
            }
    except OSError as error:
        raise RuntimeError(f"Target-effect PNG cannot be decoded: {path}") from error


def _validate_installed_files(root, texture_expectations, *, allow_extracted):
    allowed = {CATALOG_NAME, *FILE_PATHS}
    for relative in FILE_PATHS:
        allowed.add(relative + ".import")
    for model in MODEL_PATHS:
        model_stem = Path(model).stem
        for texture in TEXTURE_PATHS:
            extracted = f"models/{model_stem}_{Path(texture).name}"
            path = root / extracted
            if path.exists():
                if not allow_extracted:
                    continue
                expected = texture_expectations.get(texture)
                if _decoded_image(path) != expected:
                    raise RuntimeError(
                        f"Godot-extracted target-effect image differs from {texture}: {extracted}"
                    )
                allowed.add(extracted)
                allowed.add(extracted + ".import")
    present = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    unknown = sorted(present - allowed)
    if unknown:
        raise RuntimeError("Unexpected target-effect installed payload: " + ", ".join(unknown))
    for relative in present:
        if (root / relative).is_symlink():
            raise RuntimeError(f"Target-effect installed payload cannot be a symlink: {relative}")


def _write_lossless_import(path: Path):
    path.with_suffix(path.suffix + ".import").write_text(LOSSLESS_IMPORT)


def target_effect_requirements(project_root: Path, *, allow_editor_derivatives=True) -> dict:
    """Validate authoritative installed bytes and return immutable PCK expectations."""
    root = project_root / RELATIVE_ROOT
    catalog_path = root / CATALOG_NAME
    if not catalog_path.is_file() or catalog_path.is_symlink():
        raise RuntimeError(
            "Required target effects are missing; run import_target_effects.py --fetch --install"
        )
    try:
        document = json.loads(catalog_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Required target-effect catalog is not valid JSON") from error
    _validate_document(document)
    for relative in FILE_PATHS:
        path = root / relative
        record = document["files"][relative]
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Required target-effect file is missing: {relative}")
        if path.stat().st_size != int(record["bytes"]) or digest(path) != record["sha256"]:
            raise RuntimeError(f"Required target-effect file differs from its catalog: {relative}")
    textures = []
    texture_expectations = {}
    for relative in TEXTURE_PATHS:
        decoded = _decoded_image(root / relative)
        if (decoded["width"], decoded["height"]) not in ((128, 64), (128, 128)):
            raise RuntimeError(f"Target-effect texture has incompatible dimensions: {relative}")
        texture_expectations[relative] = decoded
        textures.append({"path": RESOURCE_ROOT + "/" + relative, **decoded})
    _validate_installed_files(root, texture_expectations, allow_extracted=allow_editor_derivatives)
    requirements = {
        "schema": "mt2spacetime.target-effect-pack-expectations",
        "schema_version": 1,
        "catalog_path": RESOURCE_ROOT + "/" + CATALOG_NAME,
        "catalog_sha256": digest(catalog_path),
        "catalog_content_hash": document["content_hash"],
        "files": {
            relative: {
                "bytes": int(document["files"][relative]["bytes"]),
                "sha256": document["files"][relative]["sha256"],
            }
            for relative in FILE_PATHS
        },
        "models": [
            {
                "path": RESOURCE_ROOT + "/" + relative,
                "surface_count": 2,
                "blend_shape_count": 10,
                "frame_count": 11,
                "track_count": 10,
                "animation_length": 0.22,
            }
            for relative in MODEL_PATHS
        ],
        "textures": textures,
    }
    return requirements


def stage_target_effects(source_project: Path, staged_project: Path, expected: dict) -> dict:
    """Replace copied editor outputs with the seven authoritative catalog resources."""
    source = source_project / RELATIVE_ROOT
    destination = staged_project / RELATIVE_ROOT
    if destination.exists():
        shutil.rmtree(destination)
    for relative in (CATALOG_NAME, *FILE_PATHS):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    for relative in TEXTURE_PATHS:
        _write_lossless_import(destination / relative)
    staged = target_effect_requirements(staged_project, allow_editor_derivatives=False)
    if staged != expected:
        raise RuntimeError("Target-effect inputs changed while the isolated project was staged")
    return staged


def prepare_target_effect_imports(staged_project: Path, requirements: dict) -> list[str]:
    """Pin lossless settings after Godot extracts images embedded in the GLBs."""
    root = staged_project / RELATIVE_ROOT
    texture_expectations = {
        str(entry["path"]).removeprefix(RESOURCE_ROOT + "/"): {
            "width": entry["width"],
            "height": entry["height"],
            "rgba_sha256": entry["rgba_sha256"],
        }
        for entry in requirements["textures"]
    }
    _validate_installed_files(root, texture_expectations, allow_extracted=True)
    configured = []
    for path in sorted(root.rglob("*.png")):
        _write_lossless_import(path)
        configured.append(path.relative_to(root).as_posix())
    if len(configured) < 4:
        raise RuntimeError("Godot import removed required target-effect textures")
    return configured


def audit_target_effect_pack(godot, pck, output, env, requirements):
    """Load remapped resources from an actual PCK and compare imported runtime data."""
    expected_path = output / "target-effect-pack-expected.json"
    report_path = output / "target-effect-pack-audit.json"
    expected_path.write_text(json.dumps(requirements, indent=2, sort_keys=True) + "\n")
    if report_path.exists():
        report_path.unlink()
    report_path.write_text(json.dumps({"passed": False, "status": "started"}) + "\n")
    _run(
        [
            godot,
            "--headless",
            "--main-pack",
            pck,
            "--script",
            Path(__file__).with_name("audit_target_effect_pack.gd"),
            "--",
            expected_path,
            report_path,
        ],
        output / "target-effect-pack-audit.log",
        env,
    )
    try:
        report = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Target-effect actual-PCK audit did not write a valid report") from error
    if (
        report.get("passed") is not True
        or report.get("catalog_sha256") != requirements["catalog_sha256"]
        or report.get("catalog_content_hash") != requirements["catalog_content_hash"]
        or len(report.get("models", [])) != 2
        or len(report.get("textures", [])) != 4
    ):
        raise RuntimeError("Target-effect actual-PCK audit report is incomplete or inconsistent")
    return report
