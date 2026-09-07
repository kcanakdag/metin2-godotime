"""Build a Windows client ZIP from an isolated copy of the Godot project.

python3 tools/export_client.py --server http://192.168.1.20:3210 --database mt2-training-v2
python3 tools/export_client.py --wine-smoke
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from target_effect_export import (
    audit_target_effect_pack,
    prepare_target_effect_imports,
    stage_target_effects,
    target_effect_requirements,
)

ROOT = Path(__file__).resolve().parents[1]
GODOT_VERSION = "4.7.2"
PRESET = "Windows Desktop"
DEV_ADDONS = ("godot_mcp", "mt2_dev_bridge")
P1_PROFILE = "p0-warrior-dog"
P1_MANIFEST = Path("assets/imported/content/p0-warrior-dog/manifest.v1.json")
P1_ACTIONS = Path("server/content/p0-warrior-dog/actions.v1.json")
P1_ARTIFACTS = (
    "res://assets/imported/content/p0-warrior-dog/actors/warrior-male.glb",
    "res://assets/imported/content/p0-warrior-dog/actors/wild-dog-101.glb",
    "res://assets/imported/content/p0-warrior-dog/items/sword-10.glb",
)
P1_WARRIOR_ACTOR_ID = "actor.player.warrior-male"
P1_WILD_DOG_ACTOR_ID = "actor.mob.wild-dog-101"
P1_SWORD_ITEM_ID = "item.weapon.sword-10"
GRANNY_RUNTIME_BINARIES = {"granny.dll", "granny2.dll", "granny2.so", "granny2.dylib"}
P1_PRESENTATION_FIELDS = {
    "schema",
    "schema_version",
    "profile_id",
    "content_hash",
    "gameplay_definition_hash",
    "presentation_output_hash",
    "converter",
    "coordinates",
    "artifacts",
    "actors",
    "items",
    "unsupported",
}
P1_CONVERTER_FIELDS = {"blender", "blender_import", "content_compiler", "gr2_importer_commit"}
P1_COORDINATE_FIELDS = {
    "source_axes",
    "source_linear_unit",
    "output_linear_unit",
    "godot_axes",
    "source_to_godot",
}
P1_ARTIFACT_FIELDS = {
    "id",
    "type",
    "path",
    "sha256",
    "bytes",
    "mesh_count",
    "textured_mesh_count",
    "vertices",
    "triangles",
    "bounds_m",
    "bones",
    "skeleton_signature",
}
P1_ACTOR_FIELDS = {
    "id",
    "kind",
    "name",
    "race_id",
    "vnum",
    "forward",
    "model_key",
    "model",
    "skeleton_signature",
    "motion_vector_space",
    "attachment_bones",
    "modes",
}
P1_MODEL_FIELDS = {"artifact_id", "path"}
P1_MODE_FIELDS = {"id", "motions", "combo_chains", "required_item_vnums"}
P1_MOTION_FIELDS = {
    "action",
    "action_id",
    "variant",
    "weight",
    "godot_name",
    "duration_us",
    "loop",
    "accumulation_m",
    "fallback_mode",
    "combo",
    "events",
}
P1_COMBO_FIELDS = {"direct_input_us", "input_limit_us", "link_us", "pre_input_us"}
P1_ATTACK_WINDOW_FIELDS = {
    "kind",
    "start_us",
    "end_us",
    "bone",
    "weapon_length_m",
    "coordinate_space",
    "sample_count",
    "samples",
    "source_parameters",
}
P1_SPHERE_EVENT_FIELDS = {
    "kind",
    "start_us",
    "end_us",
    "attack_type",
    "collision_type",
    "coordinate_space",
    "external_force",
    "hitting_type",
    "invisible_us",
    "stiffen_us",
    "spheres",
}
P1_SAMPLE_FIELDS = {"time_us", "start_m", "end_m"}
P1_SOURCE_PARAMETER_FIELDS = {
    "attack_type",
    "external_force",
    "hit_limit_count",
    "hitting_type",
    "invisible_us",
    "motion_type",
    "stiffen_us",
}
P1_SPHERE_FIELDS = {"position_m", "radius_m"}
P1_ITEM_FIELDS = {
    "id",
    "kind",
    "name",
    "vnum",
    "model",
    "actor_attachment",
    "attachment_transform",
    "equipment_mode",
}
P1_ATTACHMENT_TRANSFORM_FIELDS = {"translation_m", "rotation_degrees", "scale"}
P1_UNSUPPORTED_FIELDS = {"kind", "action_id", "event_type", "reason"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, log, env, timeout=180):
    # File output also avoids Wine background services retaining a pipe after exit.
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
    stdout = log.read_text(errors="replace")
    if result.returncode or "SCRIPT ERROR:" in stdout or "ERROR:" in stdout:
        raise RuntimeError(f"Command failed; see {log}\n{stdout[-5000:]}")
    return stdout


def template_directory(explicit):
    candidates = (
        [Path(explicit)]
        if explicit
        else [
            ROOT / ".cache" / "export_templates" / f"{GODOT_VERSION}.stable",
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
            / "godot/export_templates"
            / f"{GODOT_VERSION}.stable",
            Path.home() / ".local/share/godot/export_templates" / f"{GODOT_VERSION}.stable",
        ]
    )
    for directory in candidates:
        if (directory / "windows_release_x86_64.exe").is_file():
            return directory.resolve()
    raise RuntimeError(
        f"Godot {GODOT_VERSION} Windows x86_64 export template missing. Install matching "
        "templates in Godot's Export Template Manager or pass --templates DIRECTORY."
    )


def stage_project(stage, templates, include_maps=True, p1_enabled=False):
    def ignored(directory, names):
        exclusions = {".godot", ".git", "tests"}
        if Path(directory).name == "addons":
            exclusions.update(DEV_ADDONS)
        if Path(directory).name == "imported" and not include_maps:
            exclusions.add("maps")
        if Path(directory).name == "imported" and p1_enabled:
            exclusions.add("warrior.glb")
        return set(names).intersection(exclusions)

    shutil.copytree(ROOT / "client", stage, ignore=ignored)
    project = stage / "project.godot"
    lines = []
    section = ""
    for line in project.read_text().splitlines():
        if line.startswith("["):
            section = line
        if section == "[editor_plugins]":
            continue
        if any(f"addons/{addon}/" in line for addon in DEV_ADDONS):
            continue
        lines.append(line)
    project.write_text("\n".join(lines) + "\n")
    preset = stage / "export_presets.cfg"
    text = preset.read_text()
    for kind in ("debug", "release"):
        value = json.dumps(str(templates / f"windows_{kind}_x86_64.exe"))
        text = re.sub(
            rf"^custom_template/{kind}=.*$",
            f"custom_template/{kind}={value}",
            text,
            flags=re.MULTILINE,
        )
    preset.write_text(text)


def sha256_text(value, field="hash"):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError(f"Expected {field} to be a lowercase SHA-256 value")
    return value


def model_reference(entry, *, label, expected_artifact_id, expected_path):
    model = entry.get("model")
    if not isinstance(model, dict):
        raise RuntimeError(f"P1 {label} model reference must be a JSON object")
    if model.get("artifact_id") != expected_artifact_id or model.get("path") != expected_path:
        raise RuntimeError(f"P1 {label} model reference does not match its generated artifact")
    return model


def reject_unknown_fields(value, allowed, path):
    """Keep the versioned presentation manifest free of unreviewed payload fields."""
    if not isinstance(value, dict):
        raise RuntimeError(f"P1 presentation manifest object is invalid at {path}")
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        raise RuntimeError(f"P1 presentation manifest has unknown field at {path}.{unknown[0]}")


def validate_p1_presentation_fields(manifest):
    """Reject additions at every public manifest object boundary for schema version 1."""
    reject_unknown_fields(manifest, P1_PRESENTATION_FIELDS, "$")
    for key, fields in (
        ("converter", P1_CONVERTER_FIELDS),
        ("coordinates", P1_COORDINATE_FIELDS),
    ):
        if key in manifest:
            reject_unknown_fields(manifest[key], fields, f"$.{key}")
    for index, artifact in enumerate(manifest.get("artifacts", [])):
        reject_unknown_fields(artifact, P1_ARTIFACT_FIELDS, f"$.artifacts[{index}]")
    for index, record in enumerate(manifest.get("unsupported", [])):
        reject_unknown_fields(record, P1_UNSUPPORTED_FIELDS, f"$.unsupported[{index}]")
    for actor_index, actor in enumerate(manifest.get("actors", [])):
        actor_path = f"$.actors[{actor_index}]"
        reject_unknown_fields(actor, P1_ACTOR_FIELDS, actor_path)
        if "model" in actor:
            reject_unknown_fields(actor["model"], P1_MODEL_FIELDS, actor_path + ".model")
        if "attachment_bones" in actor:
            attachment_bones = actor["attachment_bones"]
            if not isinstance(attachment_bones, dict):
                raise RuntimeError(
                    f"P1 presentation manifest object is invalid at {actor_path}.attachment_bones"
                )
            allowed_attachments = (
                {"weapon_right"} if actor.get("id") == P1_WARRIOR_ACTOR_ID else set()
            )
            reject_unknown_fields(
                attachment_bones, allowed_attachments, actor_path + ".attachment_bones"
            )
        for mode_index, mode in enumerate(actor.get("modes", [])):
            mode_path = f"{actor_path}.modes[{mode_index}]"
            reject_unknown_fields(mode, P1_MODE_FIELDS, mode_path)
            for motion_index, motion in enumerate(mode.get("motions", [])):
                motion_path = f"{mode_path}.motions[{motion_index}]"
                reject_unknown_fields(motion, P1_MOTION_FIELDS, motion_path)
                if motion.get("combo") is not None:
                    reject_unknown_fields(motion["combo"], P1_COMBO_FIELDS, motion_path + ".combo")
                for event_index, event in enumerate(motion.get("events", [])):
                    event_path = f"{motion_path}.events[{event_index}]"
                    if not isinstance(event, dict):
                        raise RuntimeError(
                            f"P1 presentation manifest object is invalid at {event_path}"
                        )
                    fields = (
                        P1_ATTACK_WINDOW_FIELDS
                        if event.get("kind") == "attack_window"
                        else P1_SPHERE_EVENT_FIELDS
                    )
                    reject_unknown_fields(event, fields, event_path)
                    for sample_index, sample in enumerate(event.get("samples", [])):
                        reject_unknown_fields(
                            sample, P1_SAMPLE_FIELDS, f"{event_path}.samples[{sample_index}]"
                        )
                    if "source_parameters" in event:
                        reject_unknown_fields(
                            event["source_parameters"],
                            P1_SOURCE_PARAMETER_FIELDS,
                            event_path + ".source_parameters",
                        )
                    for sphere_index, sphere in enumerate(event.get("spheres", [])):
                        reject_unknown_fields(
                            sphere, P1_SPHERE_FIELDS, f"{event_path}.spheres[{sphere_index}]"
                        )
    for item_index, item in enumerate(manifest.get("items", [])):
        item_path = f"$.items[{item_index}]"
        reject_unknown_fields(item, P1_ITEM_FIELDS, item_path)
        if "model" in item:
            reject_unknown_fields(item["model"], P1_MODEL_FIELDS, item_path + ".model")
        if "attachment_transform" in item:
            reject_unknown_fields(
                item["attachment_transform"],
                P1_ATTACHMENT_TRANSFORM_FIELDS,
                item_path + ".attachment_transform",
            )


def validate_p1_manifest(manifest):
    """Validate the generated P1 actor manifest before and inside a player PCK."""
    if not isinstance(manifest, dict):
        raise RuntimeError("P1 actor manifest must be a JSON object")
    if manifest.get("schema") != "mt2spacetime.presentation-manifest":
        raise RuntimeError("P1 actor manifest has an unknown schema")
    if manifest.get("schema_version") != 1:
        raise RuntimeError("P1 actor manifest must declare schema_version 1")
    validate_p1_presentation_fields(manifest)
    if manifest.get("profile_id") != P1_PROFILE:
        raise RuntimeError(f"P1 actor manifest must declare profile_id {P1_PROFILE}")
    for field in ("content_hash", "gameplay_definition_hash", "presentation_output_hash"):
        sha256_text(manifest.get(field), field)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError("P1 actor manifest must contain an artifacts list")
    by_resource = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise RuntimeError("P1 actor manifest artifact must be a JSON object")
        resource = artifact.get("path")
        if not isinstance(resource, str) or not resource:
            raise RuntimeError("P1 actor manifest artifact has an invalid path")
        if resource in by_resource:
            raise RuntimeError(f"P1 actor manifest duplicates artifact path {resource}")
        by_resource[resource] = artifact
    missing = [path for path in P1_ARTIFACTS if path not in by_resource]
    unexpected = sorted(set(by_resource).difference(P1_ARTIFACTS))
    if missing or unexpected:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unexpected:
            detail.append("unexpected " + ", ".join(unexpected))
        raise RuntimeError("P1 actor manifest artifacts are invalid: " + "; ".join(detail))
    for resource in P1_ARTIFACTS:
        artifact = by_resource[resource]
        if not isinstance(artifact.get("id"), str) or not artifact["id"]:
            raise RuntimeError(f"P1 actor manifest {resource} has invalid id")
        if not isinstance(artifact.get("type"), str) or not artifact["type"]:
            raise RuntimeError(f"P1 actor manifest {resource} has invalid type")
        sha256_text(artifact.get("sha256"), f"{resource} sha256")
        for key in ("bytes", "mesh_count", "textured_mesh_count", "vertices", "triangles"):
            value = artifact.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RuntimeError(f"P1 actor manifest {resource} has invalid {key}")
        if resource.startswith("res://assets/imported/content/p0-warrior-dog/actors/"):
            if not isinstance(artifact.get("bones"), int) or artifact["bones"] <= 0:
                raise RuntimeError(f"P1 actor manifest {resource} has invalid bones")
            if (
                not isinstance(artifact.get("skeleton_signature"), str)
                or not artifact["skeleton_signature"]
            ):
                raise RuntimeError(f"P1 actor manifest {resource} has invalid skeleton_signature")
    actors = manifest.get("actors")
    items = manifest.get("items")
    if not isinstance(actors, list) or not isinstance(items, list):
        raise RuntimeError("P1 actor manifest must contain actors and items lists")
    actors_by_id = {}
    for actor in actors:
        if not isinstance(actor, dict) or not isinstance(actor.get("id"), str):
            raise RuntimeError("P1 actor manifest has an invalid actor entry")
        if actor["id"] in actors_by_id:
            raise RuntimeError(f"P1 actor manifest duplicates actor {actor['id']}")
        actors_by_id[actor["id"]] = actor
    warrior = actors_by_id.get(P1_WARRIOR_ACTOR_ID)
    if not isinstance(warrior, dict):
        raise RuntimeError("P1 actor manifest is missing the warrior actor model")
    if warrior.get("race_id") != 0 or warrior.get("forward") != "-Z":
        raise RuntimeError("P1 warrior actor has an invalid identity or forward axis")
    model_reference(
        warrior,
        label="warrior actor",
        expected_artifact_id=by_resource[P1_ARTIFACTS[0]]["id"],
        expected_path=P1_ARTIFACTS[0],
    )
    dog = actors_by_id.get(P1_WILD_DOG_ACTOR_ID)
    if not isinstance(dog, dict):
        raise RuntimeError("P1 actor manifest is missing WildDog 101")
    if dog.get("vnum") != 101 or dog.get("forward") != "-Z":
        raise RuntimeError("P1 WildDog 101 actor has an invalid identity or forward axis")
    model_reference(
        dog,
        label="WildDog 101 actor",
        expected_artifact_id=by_resource[P1_ARTIFACTS[1]]["id"],
        expected_path=P1_ARTIFACTS[1],
    )
    items_by_id = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RuntimeError("P1 actor manifest has an invalid item entry")
        if item["id"] in items_by_id:
            raise RuntimeError(f"P1 actor manifest duplicates item {item['id']}")
        items_by_id[item["id"]] = item
    sword = items_by_id.get(P1_SWORD_ITEM_ID)
    if not isinstance(sword, dict):
        raise RuntimeError("P1 actor manifest is missing starter Sword+0 vnum 10")
    if sword.get("vnum") != 10:
        raise RuntimeError("P1 starter Sword+0 has an invalid vnum")
    model_reference(
        sword,
        label="starter Sword+0 item",
        expected_artifact_id=by_resource[P1_ARTIFACTS[2]]["id"],
        expected_path=P1_ARTIFACTS[2],
    )
    return by_resource


def p1_profile_requirements(*, allow_legacy=False):
    """Load required P1 export content; legacy PCK inspection must opt in explicitly."""
    manifest_path = ROOT / "client" / P1_MANIFEST
    if not manifest_path.is_file():
        if allow_legacy:
            return None
        raise RuntimeError(
            "P1 actor manifest is missing: run "
            "make content-build BLENDER=/path/to/blender, then make content-validate"
        )
    actions_path = ROOT / P1_ACTIONS
    if not actions_path.is_file():
        raise RuntimeError(
            f"P1 actor manifest is present but trusted action definitions are missing: {actions_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text())
        actions = json.loads(actions_path.read_text())
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid generated P1 definition JSON: {error}") from error
    artifacts = validate_p1_manifest(manifest)
    for resource, artifact in artifacts.items():
        source = ROOT / "client" / resource.removeprefix("res://")
        if not source.is_file():
            raise RuntimeError(f"P1 generated artifact is missing: {source}")
        if source.stat().st_size != artifact["bytes"] or digest(source) != artifact["sha256"]:
            raise RuntimeError(f"P1 generated artifact does not match manifest: {source}")
    if not isinstance(actions, dict):
        raise RuntimeError("P1 trusted action definitions must be a JSON object")
    if actions.get("profile_id") != P1_PROFILE:
        raise RuntimeError("P1 trusted action definitions have a different profile_id")
    if actions.get("gameplay_definition_hash") != manifest["gameplay_definition_hash"]:
        raise RuntimeError(
            "P1 client manifest and trusted action definitions have different hashes"
        )
    return {
        "manifest": manifest,
        "manifest_sha256": digest(manifest_path),
        "gameplay_definition_hash": manifest["gameplay_definition_hash"],
    }


def validate_pack_paths(paths, *, allow_test_probe=False):
    """Reject development bridges and private/source files in the actual exported pack."""
    forbidden = []
    probes = []
    for path in paths:
        relative = path.removeprefix("res://")
        parts = Path(relative.lower()).parts
        name = parts[-1] if parts else ""
        if "export_probe" in name:
            probes.append(path)
        if (
            any(
                part in {".git", ".local", "identities", "accounts", "tests", "logs"}
                for part in parts
            )
            or any(addon in parts for addon in DEV_ADDONS)
            or relative.lower().startswith("assets/source/")
            or name == ".env"
            or name.startswith(".env.")
            or Path(name).suffix
            in {
                ".pem",
                ".key",
                ".token",
                ".session",
                ".log",
                ".gr2",
                ".msa",
                ".mde",
                ".mse",
                ".msm",
                ".mss",
                ".epk",
                ".eix",
                ".blend",
                ".zip",
                ".tar",
                ".gz",
            }
            or "granny" in parts
            or name in GRANNY_RUNTIME_BINARIES
            or "blender" in parts
            or name in {"blender", "blender.exe"}
            or relative.lower().startswith("server/content/")
        ):
            forbidden.append(path)
    if forbidden:
        raise RuntimeError("Forbidden packaged files: " + ", ".join(forbidden[:12]))
    if probes and not allow_test_probe:
        raise RuntimeError("Test probe included in a player export: " + ", ".join(probes))
    if allow_test_probe and not probes:
        raise RuntimeError("The requested test export has no packaged test probe")
    return {"files_checked": len(paths), "test_probe_present": bool(probes)}


def audit_pack(godot, pck, output, env, *, allow_test_probe=False, p1_requirements=None):
    # Load the actual exported PCK, checking remapped meshes and animations too.
    probe = output / "audit_pack.gd"
    probe.write_text("""extends SceneTree

const P1_MANIFEST := "res://assets/imported/content/p0-warrior-dog/manifest.v1.json"
const P1_PROFILE := "p0-warrior-dog"
const P1_PATHS := [
    "res://assets/imported/content/p0-warrior-dog/actors/warrior-male.glb",
    "res://assets/imported/content/p0-warrior-dog/actors/wild-dog-101.glb",
    "res://assets/imported/content/p0-warrior-dog/items/sword-10.glb",
]

func _initialize() -> void:
    var directories: Array[String] = ["res://"]
    var paths: Array[String] = []
    while not directories.is_empty():
        var path: String = directories.pop_back()
        var directory := DirAccess.open(path)
        if not directory:
            push_error("Cannot inspect packaged directory: " + path)
            quit(1)
            return
        directory.include_hidden = true
        directory.include_navigational = false
        directory.list_dir_begin()
        var entry := directory.get_next()
        while not entry.is_empty():
            var resource_path := path.path_join(entry)
            if directory.current_is_dir():
                directories.append(resource_path)
            else:
                paths.append(resource_path)
            entry = directory.get_next()
        directory.list_dir_end()
    paths.sort()
    var inventory := FileAccess.open(OS.get_cmdline_user_args()[1], FileAccess.WRITE)
    if not inventory:
        push_error("Could not write packaged file inventory")
        quit(1)
        return
    inventory.store_string(JSON.stringify(paths, "  "))
    inventory.close()
    for setting in ProjectSettings.get_property_list():
        var key := str(setting["name"])
        if key.begins_with("autoload/") and "mcp" in key.to_lower():
            push_error("Development MCP autoload included: " + key)
            quit(1)
            return
    if DirAccess.dir_exists_absolute("res://addons/godot_mcp"):
        push_error("Development MCP addon included")
        quit(1)
        return
    if FileAccess.file_exists("res://client_config.json"):
        var config = JSON.parse_string(FileAccess.get_file_as_string("res://client_config.json"))
        if not config is Dictionary:
            push_error("Invalid packaged connection defaults")
            quit(1)
            return
        for key in config:
            if key not in ["server_url", "database", "default_player_name"]:
                push_error("Unexpected packaged connection setting: " + str(key))
                quit(1)
                return
    var ui_images := audit_ui()
    if ui_images < 0:
        quit(1)
        return
    var p1_audit: Variant = audit_p1_profile(OS.get_cmdline_user_args()[2], OS.get_cmdline_user_args()[3] == "1")
    if p1_audit == null:
        quit(1)
        return
    if p1_audit is Dictionary:
        var license_file := FileAccess.open(OS.get_cmdline_user_args()[0], FileAccess.WRITE)
        if not license_file:
            push_error("Could not write engine notices")
            quit(1)
            return
        license_file.store_line(Engine.get_license_text())
        license_file.store_line("Third-party copyrights:")
        license_file.store_line(JSON.stringify(Engine.get_copyright_info(), "  "))
        license_file.store_line("Third-party licenses:")
        license_file.store_line(JSON.stringify(Engine.get_license_info(), "  "))
        license_file.close()
        p1_audit["ui_images"] = ui_images
        p1_audit["ui_pixels_verified"] = true
        print("PACK_AUDIT " + JSON.stringify(p1_audit))
        quit(0)
        return
    var packed := load("res://assets/imported/warrior.glb") as PackedScene
    if not packed:
        push_error("Packaged warrior could not load")
        quit(1)
        return
    var model := packed.instantiate()
    var pending: Array[Node] = [model]
    var meshes := 0
    var textured_meshes := 0
    var bones := 0
    var clips: Array[String] = []
    while not pending.is_empty():
        var node: Node = pending.pop_back()
        if node is MeshInstance3D:
            meshes += 1
            var textured := false
            for surface in range(node.mesh.get_surface_count()):
                var material = node.get_active_material(surface)
                if material is BaseMaterial3D and material.albedo_texture:
                    textured = true
            if textured:
                textured_meshes += 1
        if node is Skeleton3D:
            bones += node.get_bone_count()
        if node is AnimationPlayer:
            for clip in node.get_animation_list():
                clips.append(str(clip))
        for child in node.get_children():
            pending.append(child)
    model.free()
    var license_file := FileAccess.open(OS.get_cmdline_user_args()[0], FileAccess.WRITE)
    if not license_file:
        push_error("Could not write engine notices")
        quit(1)
        return
    license_file.store_line(Engine.get_license_text())
    license_file.store_line("Third-party copyrights:")
    license_file.store_line(JSON.stringify(Engine.get_copyright_info(), "  "))
    license_file.store_line("Third-party licenses:")
    license_file.store_line(JSON.stringify(Engine.get_license_info(), "  "))
    license_file.close()
    print("PACK_AUDIT " + JSON.stringify({"meshes": meshes, "textured_meshes": textured_meshes, "bones": bones, "animations": clips, "ui_images": ui_images, "ui_pixels_verified": true}))
    quit(0 if meshes >= 3 and textured_meshes == meshes and bones >= 75 and clips.size() >= 4 else 1)

func audit_ui() -> int:
    var path := "res://assets/imported/ui/manifest.json"
    if not FileAccess.file_exists(path):
        push_error("Original UI manifest missing. Run make import-ui before exporting.")
        return -1
    var manifest = JSON.parse_string(FileAccess.get_file_as_string(path))
    if not manifest is Dictionary or not manifest.get("assets") is Dictionary or not manifest.get("maps") is Dictionary:
        push_error("Invalid original UI manifest")
        return -1
    var entries: Array = manifest.assets.values() + manifest.maps.values()
    if entries.is_empty():
        push_error("Original UI fixture is empty")
        return -1
    for entry in entries:
        var resource := str(entry.get("resource", ""))
        if not resource.begins_with("res://assets/imported/ui/") or not resource.ends_with(".png"):
            push_error("Invalid original UI resource path")
            return -1
        var texture := load(resource) as Texture2D
        if not texture:
            push_error("Missing packaged UI image: " + resource)
            return -1
        var image := texture.get_image()
        if not image or image.is_compressed() or image.has_mipmaps():
            push_error("UI texture must remain lossless without mipmaps: " + resource)
            return -1
        image.convert(Image.FORMAT_RGBA8)
        var hash := HashingContext.new()
        hash.start(HashingContext.HASH_SHA256)
        hash.update(image.get_data())
        if hash.finish().hex_encode() != str(entry.get("rgba_sha256", "")):
            push_error("Packaged UI pixels differ from the pinned conversion: " + resource)
            return -1
    return entries.size()


func has_no_unknown_fields(value: Variant, allowed: Array, path: String) -> bool:
    if not value is Dictionary:
        push_error("P1 presentation manifest object is invalid at " + path)
        return false
    for key in value:
        if not key is String or key not in allowed:
            push_error("P1 presentation manifest has unknown field at " + path + "." + str(key))
            return false
    return true


func validate_presentation_fields(manifest: Dictionary) -> bool:
    if not has_no_unknown_fields(manifest, ["schema", "schema_version", "profile_id", "content_hash", "gameplay_definition_hash", "presentation_output_hash", "converter", "coordinates", "artifacts", "actors", "items", "unsupported"], "$"):
        return false
    if manifest.has("converter") and not has_no_unknown_fields(manifest["converter"], ["blender", "blender_import", "content_compiler", "gr2_importer_commit"], "$.converter"):
        return false
    if manifest.has("coordinates") and not has_no_unknown_fields(manifest["coordinates"], ["source_axes", "source_linear_unit", "output_linear_unit", "godot_axes", "source_to_godot"], "$.coordinates"):
        return false
    for unsupported_index in manifest.get("unsupported", []).size():
        if not has_no_unknown_fields(manifest["unsupported"][unsupported_index], ["kind", "action_id", "event_type", "reason"], "$.unsupported[%d]" % unsupported_index):
            return false
    for artifact_index in manifest.get("artifacts", []).size():
        if not has_no_unknown_fields(manifest["artifacts"][artifact_index], ["id", "type", "path", "sha256", "bytes", "mesh_count", "textured_mesh_count", "vertices", "triangles", "bounds_m", "bones", "skeleton_signature"], "$.artifacts[%d]" % artifact_index):
            return false
    for actor_index in manifest.get("actors", []).size():
        var actor = manifest["actors"][actor_index]
        var actor_path := "$.actors[%d]" % actor_index
        if not has_no_unknown_fields(actor, ["id", "kind", "name", "race_id", "vnum", "forward", "model_key", "model", "skeleton_signature", "motion_vector_space", "attachment_bones", "modes"], actor_path):
            return false
        if actor.has("model") and not has_no_unknown_fields(actor["model"], ["artifact_id", "path"], actor_path + ".model"):
            return false
        if actor.has("attachment_bones"):
            var attachment_fields: Array = ["weapon_right"] if actor.get("id") == "actor.player.warrior-male" else []
            if not has_no_unknown_fields(actor["attachment_bones"], attachment_fields, actor_path + ".attachment_bones"):
                return false
        for mode_index in actor.get("modes", []).size():
            var mode = actor["modes"][mode_index]
            var mode_path := actor_path + ".modes[%d]" % mode_index
            if not has_no_unknown_fields(mode, ["id", "motions", "combo_chains", "required_item_vnums"], mode_path):
                return false
            for motion_index in mode.get("motions", []).size():
                var motion = mode["motions"][motion_index]
                var motion_path := mode_path + ".motions[%d]" % motion_index
                if not has_no_unknown_fields(motion, ["action", "action_id", "variant", "weight", "godot_name", "duration_us", "loop", "accumulation_m", "fallback_mode", "combo", "events"], motion_path):
                    return false
                if motion.get("combo") != null and not has_no_unknown_fields(motion["combo"], ["direct_input_us", "input_limit_us", "link_us", "pre_input_us"], motion_path + ".combo"):
                    return false
                for event_index in motion.get("events", []).size():
                    var event = motion["events"][event_index]
                    var event_path := motion_path + ".events[%d]" % event_index
                    var event_fields: Array = ["kind", "start_us", "end_us", "attack_type", "collision_type", "coordinate_space", "external_force", "hitting_type", "invisible_us", "stiffen_us", "spheres"]
                    if event is Dictionary and event.get("kind") == "attack_window":
                        event_fields = ["kind", "start_us", "end_us", "bone", "weapon_length_m", "coordinate_space", "sample_count", "samples", "source_parameters"]
                    if not has_no_unknown_fields(event, event_fields, event_path):
                        return false
                    for sample_index in event.get("samples", []).size():
                        if not has_no_unknown_fields(event["samples"][sample_index], ["time_us", "start_m", "end_m"], event_path + ".samples[%d]" % sample_index):
                            return false
                    if event.has("source_parameters") and not has_no_unknown_fields(event["source_parameters"], ["attack_type", "external_force", "hit_limit_count", "hitting_type", "invisible_us", "motion_type", "stiffen_us"], event_path + ".source_parameters"):
                        return false
                    for sphere_index in event.get("spheres", []).size():
                        if not has_no_unknown_fields(event["spheres"][sphere_index], ["position_m", "radius_m"], event_path + ".spheres[%d]" % sphere_index):
                            return false
    for item_index in manifest.get("items", []).size():
        var item = manifest["items"][item_index]
        var item_path := "$.items[%d]" % item_index
        if not has_no_unknown_fields(item, ["id", "kind", "name", "vnum", "model", "actor_attachment", "attachment_transform", "equipment_mode"], item_path):
            return false
        if item.has("model") and not has_no_unknown_fields(item["model"], ["artifact_id", "path"], item_path + ".model"):
            return false
        if item.has("attachment_transform") and not has_no_unknown_fields(item["attachment_transform"], ["translation_m", "rotation_degrees", "scale"], item_path + ".attachment_transform"):
            return false
    return true


func audit_p1_profile(expected_manifest_hash: String, required: bool) -> Variant:
    if not FileAccess.file_exists(P1_MANIFEST):
        if required:
            push_error("P1 actor manifest was staged but is missing from the exported PCK")
            return null
        return false
    var manifest_bytes := FileAccess.get_file_as_bytes(P1_MANIFEST)
    if not expected_manifest_hash.is_empty() and sha256(manifest_bytes) != expected_manifest_hash:
        push_error("Packaged P1 actor manifest does not match the staged manifest")
        return null
    var manifest = JSON.parse_string(manifest_bytes.get_string_from_utf8())
    if not manifest is Dictionary:
        push_error("Invalid packaged P1 actor manifest")
        return null
    if manifest.get("schema") != "mt2spacetime.presentation-manifest" or manifest.get("schema_version") != 1 or manifest.get("profile_id") != P1_PROFILE:
        push_error("Packaged P1 actor manifest schema or profile mismatch")
        return null
    if not validate_presentation_fields(manifest):
        return null
    for hash_key in ["content_hash", "gameplay_definition_hash", "presentation_output_hash"]:
        if not is_sha256(manifest.get(hash_key, "")):
            push_error("Packaged P1 actor manifest has invalid " + hash_key)
            return null
    var artifacts = manifest.get("artifacts")
    if not artifacts is Array or artifacts.size() != P1_PATHS.size():
        push_error("Packaged P1 actor manifest must list exactly the required artifacts")
        return null
    var by_path := {}
    for artifact in artifacts:
        if not artifact is Dictionary:
            push_error("Packaged P1 artifact is invalid")
            return null
        var resource_value = artifact.get("path", "")
        if not resource_value is String or resource_value.is_empty():
            push_error("Packaged P1 artifact has an invalid path")
            return null
        var resource: String = resource_value
        if resource in by_path:
            push_error("Packaged P1 actor manifest duplicates artifact " + resource)
            return null
        by_path[resource] = artifact
    for resource in P1_PATHS:
        if not by_path.has(resource):
            push_error("Packaged P1 actor manifest is missing " + resource)
            return null
    var result := {"p1_profile": P1_PROFILE, "p1_gameplay_definition_hash": manifest["gameplay_definition_hash"], "actors": []}
    for resource in P1_PATHS:
        var artifact: Dictionary = by_path[resource]
        if not is_sha256(artifact.get("sha256", "")):
            push_error("Packaged P1 artifact path or SHA-256 is invalid: " + resource)
            return null
        var packed := load(resource) as PackedScene
        if not packed:
            push_error("Packaged P1 model could not load: " + resource)
            return null
        var model := packed.instantiate()
        var summary := inspect_model(model)
        model.free()
        for count_key in ["mesh_count", "textured_mesh_count", "bones"]:
            if artifact.has(count_key) and summary.get(count_key) != artifact[count_key]:
                push_error("Packaged P1 model has a mismatched " + count_key + ": " + resource)
                return null
        if resource.contains("/actors/") and summary["skinned_mesh_count"] <= 0:
            push_error("Packaged P1 actor has no skinned mesh: " + resource)
            return null
        var actor := find_actor_for_model(manifest.get("actors", []), artifact.get("id", ""))
        if resource.contains("/actors/"):
            if actor.is_empty() or not verify_actor_metadata(actor, summary, resource):
                return null
        var actor_result := summary.duplicate()
        actor_result["path"] = resource
        result["actors"].append(actor_result)
    if not has_required_entities(manifest, by_path):
        return null
    return result


func is_sha256(value: Variant) -> bool:
    return value is String and value.length() == 64 and value == value.to_lower() and value.is_valid_hex_number()


func sha256(bytes: PackedByteArray) -> String:
    var hash := HashingContext.new()
    hash.start(HashingContext.HASH_SHA256)
    hash.update(bytes)
    return hash.finish().hex_encode()


func inspect_model(model: Node) -> Dictionary:
    var pending: Array[Node] = [model]
    var meshes := 0
    var textured_meshes := 0
    var skinned_meshes := 0
    var bones := 0
    var bone_names: Array[String] = []
    var clips: Array[String] = []
    while not pending.is_empty():
        var node: Node = pending.pop_back()
        if node is MeshInstance3D:
            meshes += 1
            if node.skin:
                skinned_meshes += 1
            var textured := false
            for surface in range(node.mesh.get_surface_count()):
                var material = node.get_active_material(surface)
                if material is BaseMaterial3D and material.albedo_texture:
                    textured = true
            if textured:
                textured_meshes += 1
        if node is Skeleton3D:
            bones += node.get_bone_count()
            for bone in node.get_bone_count():
                bone_names.append(node.get_bone_name(bone))
        if node is AnimationPlayer:
            for clip in node.get_animation_list():
                clips.append(str(clip))
        for child in node.get_children():
            pending.append(child)
    return {"mesh_count": meshes, "textured_mesh_count": textured_meshes, "skinned_mesh_count": skinned_meshes, "bones": bones, "bone_names": bone_names, "clips": clips}


func find_actor_for_model(actors: Variant, model_id: String) -> Dictionary:
    if not actors is Array:
        return {}
    for actor in actors:
        if actor is Dictionary:
            var model = actor.get("model")
            if model is Dictionary and model.get("artifact_id") == model_id:
                return actor
    return {}


func collect_string_values(value: Variant, key: String, found: Dictionary) -> void:
    if value is Dictionary:
        for child_key in value:
            if child_key == key and value[child_key] is String and not value[child_key].is_empty():
                found[value[child_key]] = true
            collect_string_values(value[child_key], key, found)
    elif value is Array:
        for child in value:
            collect_string_values(child, key, found)


func verify_actor_metadata(actor: Dictionary, summary: Dictionary, resource: String) -> bool:
    var required_clips := {}
    collect_string_values(actor.get("modes", []), "godot_name", required_clips)
    if required_clips.is_empty():
        push_error("Packaged P1 actor has no declared motions: " + resource)
        return false
    for clip in required_clips:
        if clip not in summary["clips"]:
            push_error("Packaged P1 actor is missing declared animation " + clip + ": " + resource)
            return false
    var required_bones := {}
    var attachments = actor.get("attachment_bones", [])
    if attachments is Dictionary:
        for attachment in attachments:
            if attachments[attachment] is String and not attachments[attachment].is_empty():
                required_bones[attachments[attachment]] = true
    elif attachments is Array:
        for bone in attachments:
            if bone is String and not bone.is_empty():
                required_bones[bone] = true
    for bone in required_bones:
        if bone not in summary["bone_names"]:
            push_error("Packaged P1 actor is missing attachment bone " + bone + ": " + resource)
            return false
    return true


func has_required_entities(manifest: Dictionary, artifacts: Dictionary) -> bool:
    var warrior_id: String = str(artifacts[P1_PATHS[0]].get("id"))
    var dog_id: String = str(artifacts[P1_PATHS[1]].get("id"))
    var sword_id: String = str(artifacts[P1_PATHS[2]].get("id"))
    var warrior := false
    var dog := false
    for actor in manifest.get("actors", []):
        if actor is Dictionary:
            var model = actor.get("model")
            if model is Dictionary:
                warrior = warrior or (actor.get("id") == "actor.player.warrior-male" and actor.get("race_id") == 0 and model.get("artifact_id") == warrior_id)
                dog = dog or (actor.get("id") == "actor.mob.wild-dog-101" and actor.get("vnum") == 101 and model.get("artifact_id") == dog_id)
    var sword := false
    for item in manifest.get("items", []):
        if item is Dictionary:
            var model = item.get("model")
            if model is Dictionary and item.get("id") == "item.weapon.sword-10" and item.get("vnum") == 10 and model.get("artifact_id") == sword_id:
                sword = true
    if not warrior or not dog or not sword:
        push_error("Packaged P1 actor manifest must include warrior, WildDog 101 and starter Sword+0 vnum 10")
        return false
    return true
""")
    stdout = run(
        [
            godot,
            "--headless",
            "--main-pack",
            pck,
            "--script",
            probe,
            "--",
            output / "godot-licenses.txt",
            output / "pack-inventory.json",
            p1_requirements["manifest_sha256"] if p1_requirements else "",
            "1" if p1_requirements else "0",
        ],
        output / "pack-audit.log",
        env,
    )
    line = next(line for line in stdout.splitlines() if line.startswith("PACK_AUDIT "))
    audit = json.loads(line.removeprefix("PACK_AUDIT "))
    audit.update(
        validate_pack_paths(
            json.loads((output / "pack-inventory.json").read_text()),
            allow_test_probe=allow_test_probe,
        )
    )
    return audit


def package_notices(stage, build, local):
    notices = build / "licenses"
    notices.mkdir()
    shutil.copy2(local / "godot-licenses.txt", notices / "Godot.txt")
    addon_directory = stage / "addons"
    names = {"license", "license.txt", "license.md", "copying", "notice", "notice.txt"}
    if addon_directory.is_dir():
        for path in addon_directory.rglob("*"):
            if path.is_file() and path.name.lower() in names:
                destination = notices / path.relative_to(addon_directory)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument(
        "--templates", help="Directory containing matching Windows export templates"
    )
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--database", default="mt2-training-v2")
    parser.add_argument("--player-name", default="")
    parser.add_argument(
        "--wine-smoke", action="store_true", help="Run the Windows EXE headlessly under Wine"
    )
    options = parser.parse_args()
    server = urlparse(options.server)
    if server.scheme not in ("http", "https") or not server.hostname:
        parser.error("--server must be an http:// or https:// SpacetimeDB address")
    if not options.database:
        parser.error("--database cannot be empty")
    p1_requirements = p1_profile_requirements()
    live_target_effects = target_effect_requirements(ROOT / "client")
    if p1_requirements is None and not (ROOT / "client/assets/imported/warrior.glb").is_file():
        parser.error("Warrior asset missing: run make assets and make import-assets first")
    godot = shutil.which(options.godot)
    if not godot:
        parser.error(f"Godot executable not found: {options.godot}")
    version = subprocess.check_output([godot, "--version"], text=True).strip()
    if not version.startswith(GODOT_VERSION + ".stable"):
        parser.error(f"Expected Godot {GODOT_VERSION}.stable, found {version}")
    templates = template_directory(options.templates)
    local = ROOT / ".local/export"
    local.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for variable, folder in (
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        directory = local / folder
        directory.mkdir(exist_ok=True)
        env[variable] = str(directory)
    destination = ROOT / "dist/windows-x86_64"
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="client-", dir=local) as temporary:
        stage = Path(temporary) / "project"
        build = Path(temporary) / "windows-x86_64"
        build.mkdir()
        stage_project(stage, templates, include_maps=False, p1_enabled=p1_requirements is not None)
        staged_target_effects = stage_target_effects(ROOT / "client", stage, live_target_effects)
        executable = build / "MT2Spacetime.exe"
        run(
            [godot, "--headless", "--path", stage, "--editor", "--import", "--quit"],
            local / "import.log",
            env,
        )
        prepare_target_effect_imports(stage, staged_target_effects)
        run(
            [godot, "--headless", "--path", stage, "--editor", "--import", "--quit"],
            local / "target-effect-reimport.log",
            env,
        )
        run(
            [godot, "--headless", "--path", stage, "--export-release", PRESET, executable],
            local / "export.log",
            env,
        )
        pack_audit = audit_pack(
            godot,
            executable.with_suffix(".pck"),
            local,
            env,
            p1_requirements=p1_requirements,
        )
        pack_audit["target_effects"] = audit_target_effect_pack(
            godot,
            executable.with_suffix(".pck"),
            local,
            env,
            staged_target_effects,
        )
        package_notices(stage, build, local)
        connection = {
            "server_url": options.server.rstrip("/"),
            "database": options.database,
            "default_player_name": options.player_name,
        }
        (build / "client_config.json").write_text(json.dumps(connection, indent=2) + "\n")
        (build / "README.txt").write_text(
            "MT2 Spacetime development client\n\n"
            "Extract the whole ZIP into a folder, then run MT2Spacetime.exe.\n"
            "Keep MT2Spacetime.pck and client_config.json next to the executable.\n"
            "No Godot, Blender, Rust, Python or SpacetimeDB SDK installation is needed.\n"
            "Choose a name and connect to the host's server and database.\n"
            "The host must run SpacetimeDB; localhost means your own computer.\n"
            "Edit client_config.json to change the default server address.\n"
            "See the repository docs/distribution.md for hosting and connection help.\n"
        )
        manifest = {
            "godot": version,
            "target": "windows-x86_64",
            "mode": "release",
            "pack_audit": pack_audit,
            "connection_defaults": connection,
            "template_sha256": digest(templates / "windows_release_x86_64.exe"),
            "files": {
                p.relative_to(build).as_posix(): digest(p)
                for p in sorted(build.rglob("*"))
                if p.is_file()
            },
        }
        if options.wine_smoke:
            wine = shutil.which("wine")
            if not wine:
                parser.error("Wine was requested but is not installed")
            wine_env = {
                **env,
                "WINEPREFIX": str(ROOT / ".local/wine-client"),
                "WINEARCH": "win64",
                "WINEDEBUG": "-all",
                "WINEDLLOVERRIDES": "mscoree,mshtml=d",
            }
            wine_output = run(
                [wine, executable, "--headless", "--quit-after", "90"],
                local / "wine-smoke.log",
                wine_env,
                timeout=120,
            )
            if GODOT_VERSION not in wine_output:
                raise RuntimeError("Wine smoke run did not print the expected Godot version")
            manifest["wine_smoke"] = {
                "status": "passed",
                "mode": "headless",
                "version": subprocess.check_output([wine, "--version"], text=True).strip(),
            }
        (build / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(build, destination)
    archive = destination.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(destination.parent))
    print(
        json.dumps(
            {
                "archive": str(archive),
                "archive_sha256": digest(archive),
                "executable": str(destination / "MT2Spacetime.exe"),
                "pack_audit": pack_audit,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
