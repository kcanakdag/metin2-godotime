#!/usr/bin/env python3
"""Compile one explicit Metin2 source profile into normalized client/server data."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

from actor_texture_import import write_actor_texture_import
from content_formats import parse_item_script, parse_motion_list, parse_msa, parse_race_script
from fetch_test_assets import METIN_COMMIT, ROOT
from metin_archive import Archive, safe_path, virtual_path, write_json
from metin_root_motion import (
    COORDINATE_CONVERSION,
    MAX_ENDPOINT_COMPONENT_M,
    MAX_INITIAL_PLACEMENT_COMPONENT_CM,
    MAX_SOURCE_COMPONENT_CM,
    MSA_COMPONENT_TOLERANCE_M,
    extract_root_motion,
    source_cm_to_output_actor_local_m,
)
from metin_root_motion import (
    EXPECTED_INPUTS as EXPECTED_ROOT_MOTION_INPUTS,
)
from metin_root_motion import (
    MAX_DURATION_US as MAX_ROOT_MOTION_DURATION_US,
)
from metin_root_motion import (
    POLICY_ID as ROOT_MOTION_POLICY_ID,
)
from progression_definitions import parse_progression_definitions, quarter_thresholds

SCHEMA = "mt2spacetime.normalized-content-manifest"
SERVER_SCHEMA = "mt2spacetime.trusted-action-definitions"
CLIENT_SCHEMA = "mt2spacetime.presentation-manifest"
SCHEMA_VERSION = 1
SERVER_SCHEMA_VERSION = 5
COMPILER_VERSION = "content-compiler-v1.4.0"
DEFAULT_PROFILE = ROOT / "content/profiles/p0-warrior-dog.json"

PLAYER_ACTOR_ID = "actor.player.warrior-male"
MOB_ACTOR_ID = "actor.mob.wild-dog-101"
PLAYER_GENERAL_ACTION_ID = f"{PLAYER_ACTOR_ID}.general.normal_attack.v1"
PLAYER_COMBO_ACTION_IDS = (
    f"{PLAYER_ACTOR_ID}.onehand.combo_1",
    f"{PLAYER_ACTOR_ID}.onehand.combo_2",
    f"{PLAYER_ACTOR_ID}.onehand.combo_3",
    f"{PLAYER_ACTOR_ID}.onehand.combo_4",
)
MOB_ACTION_ID = f"{MOB_ACTOR_ID}.general.normal_attack.v1"
EXPECTED_SERVER_ACTION_IDS = {
    PLAYER_GENERAL_ACTION_ID,
    *PLAYER_COMBO_ACTION_IDS,
    MOB_ACTION_ID,
}
COMBO_INPUT_FIELDS = {"pre_input_us", "direct_input_us", "input_limit_us", "link_us"}
MAX_COMBO_TIME_US = 60_000_000
ROOT_MOTION_FIELDS = {"endpoint_x_m", "endpoint_z_m", "duration_us"}
ROOT_MOTION_POLICY = {
    "id": ROOT_MOTION_POLICY_ID,
    "source_endpoint": "raw-gr2-loop-translation",
    "coordinate_conversion": COORDINATE_CONVERSION,
    "msa_role": "rounded-corroboration-with-one-pinned-terminal-exception",
    "msa_component_tolerance_micrometers": 50,
    "granny_within_cycle_parity": False,
    "granny_transition_blend_parity": False,
    "pinned_exception_action_id": PLAYER_COMBO_ACTION_IDS[3],
    "pinned_exception_reason": "raw-gr2-endpoint-disagrees-with-serialized-msa-accumulation",
}
SPECIAL_AREA_POLICY = {
    "id": "legacy-60hz-fixed-sphere-once-per-life-v1",
    "dispatch_fps": 60,
    "activation_uses_frame_floor_then_next_tick": True,
    "sphere_space": "action-start-actor-local-to-world-at-activation",
    "victim_filter": "live-exact-life-same-map-attackable",
    "hit_once_scope": "area-instance-and-victim-life",
    "force_policy": "linear-unobstructed-distance-approx-v1",
    "legacy_physics_collision_parity": False,
}
SCREEN_WAVE_POLICY = {
    "id": "legacy-60hz-viewer-range-metadata-v1",
    "dispatch_fps": 60,
    "activation_uses_frame_floor_then_next_tick": True,
    "camera_randomization_runtime_parity": False,
}
DEFENDING_SPHERE_POLICY = {
    "id": "static-full-3d-swept-sphere-v1",
    "source_collision_type": 3,
    "bone": "Bip01",
}
MOB_REACTION_IDS = {
    "front_knockdown": f"{MOB_ACTOR_ID}.general.front_knockdown",
    "front_standup": f"{MOB_ACTOR_ID}.general.front_standup",
    "back_knockdown": f"{MOB_ACTOR_ID}.general.back_knockdown",
}
MOB_REACTION_DURATIONS_US = {
    "front_knockdown": 1_166_667,
    "front_standup": 1_000_000,
    "back_knockdown": 1_166_667,
}
ORDINARY_HIT_INVULNERABILITY_US = {
    PLAYER_GENERAL_ACTION_ID: 500_000,
    PLAYER_COMBO_ACTION_IDS[0]: 100_000,
    PLAYER_COMBO_ACTION_IDS[1]: 100_000,
    PLAYER_COMBO_ACTION_IDS[2]: 200_000,
    PLAYER_COMBO_ACTION_IDS[3]: 0,
    MOB_ACTION_ID: 300_000,
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_profile(path: Path) -> dict:
    profile = json.loads(path.read_text())
    if profile.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Only content profile schema_version 1 is supported")
    profile_id = profile.get("profile_id", "")
    if not profile_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in profile_id):
        raise ValueError(f"Invalid profile_id {profile_id!r}")
    if profile["source"]["client"]["revision"] != METIN_COMMIT:
        raise ValueError("Profile does not use the pinned client revision")
    ids = [entry["id"] for entry in [*profile["actors"], *profile["items"]]]
    if len(ids) != len(set(ids)):
        raise ValueError("Profile content IDs must be unique")
    action_ids = []
    godot_names = []
    for actor in profile["actors"]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", actor["id"]):
            raise ValueError(f"Invalid actor ID {actor['id']!r}")
        mode_ids = [mode["id"] for mode in actor["modes"]]
        if len(mode_ids) != len(set(mode_ids)):
            raise ValueError(f"Duplicate mode ID in {actor['id']}")
        output = safe_path(actor["output"])
        if not output.endswith(".glb"):
            raise ValueError(f"Actor output must be a GLB: {output}")
        orientation = actor["orientation"]
        if orientation.get("output_forward") != "-Z":
            raise ValueError(f"Actor output forward must be -Z: {actor['id']}")
        yaw = orientation.get("yaw_correction_degrees")
        if not isinstance(yaw, (int, float)) or not math.isfinite(yaw):
            raise ValueError(f"Invalid actor yaw correction: {actor['id']}")
        for mode in actor["modes"]:
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", mode["id"]):
                raise ValueError(f"Invalid mode ID in {actor['id']}")
            actions = [motion["action"] for motion in mode["motions"]]
            if len(actions) != len(set(actions)):
                raise ValueError(f"Duplicate action in {actor['id']}.{mode['id']}")
            for motion in mode["motions"]:
                if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", motion["action"]):
                    raise ValueError(f"Invalid action ID in {actor['id']}.{mode['id']}")
                files = motion["files"]
                weights = motion.get("weights", [100] if len(files) == 1 else None)
                if (
                    not weights
                    or len(files) != len(weights)
                    or any(type(weight) is not int or weight <= 0 for weight in weights)
                    or sum(weights) != 100
                ):
                    raise ValueError(
                        f"Invalid variant weights for {actor['id']}.{motion['action']}"
                    )
                for name in files:
                    safe_path(name)
                base_id = f"{actor['id']}.{mode['id']}.{motion['action']}"
                variants = [
                    base_id if len(files) == 1 else f"{base_id}.v{index + 1}"
                    for index in range(len(files))
                ]
                action_ids.extend(variants)
                godot_names.extend(
                    re.sub(r"[^A-Za-z0-9_]+", "_", action_id).strip("_") for action_id in variants
                )
    for item in profile["items"]:
        output = safe_path(item["output"])
        if not output.endswith(".glb"):
            raise ValueError(f"Item output must be a GLB: {output}")
        transform = item["attachment_transform"]
        for field in ("translation_m", "rotation_degrees", "scale"):
            values = transform[field]
            if len(values) != 3 or not all(
                type(value) in {int, float} and math.isfinite(value) for value in values
            ):
                raise ValueError(f"Invalid {field} for {item['id']}")
            if field == "scale" and any(value <= 0 for value in values):
                raise ValueError(f"Invalid scale for {item['id']}")
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("Profile action IDs must be globally unique")
    if len(godot_names) != len(set(godot_names)):
        raise ValueError("Profile action IDs collide after Godot name normalization")
    outputs = [entry["output"] for entry in [*profile["actors"], *profile["items"]]]
    if len(outputs) != len(set(outputs)):
        raise ValueError("Profile output paths must be unique")
    for section in profile["trusted_gameplay"].values():
        for key, value in section.items():
            if key.endswith(("_m", "_mps")) and (
                type(value) not in {int, float} or not math.isfinite(value) or value <= 0
            ):
                raise ValueError(f"Invalid gameplay value {key}")
            if key.endswith("_us") and (type(value) is not int or value <= 0):
                raise ValueError(f"Invalid gameplay duration {key}")
    base_damage = profile["trusted_gameplay"]["player"].get("base_damage")
    if type(base_damage) is not int or not 0 < base_damage <= 65535:
        raise ValueError("trusted_gameplay.player.base_damage must be a positive u16")
    return profile


def fetch_server_references(profile: dict, *, offline: bool) -> list[dict]:
    server = profile["source"]["server_reference"]
    revision = server["revision"]
    cache = ROOT / "assets/source/content/server" / revision
    result = []
    for declared in server["files"]:
        relative = safe_path(declared["path"])
        destination = cache / relative
        if destination.exists():
            content = destination.read_bytes()
        else:
            if offline:
                raise FileNotFoundError(f"Not cached; retry online: server/{relative}")
            url = (
                "https://git.old-metin2.com/api/v1/repos/metin2/server/contents/"
                + urllib.parse.quote(relative, safe="/")
                + "?ref="
                + revision
            )
            request = urllib.request.Request(
                url, headers={"User-Agent": "mt2spacetime-content-compiler"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                entry = json.load(response)
            if entry["sha"] != declared["git_sha"]:
                raise ValueError(f"Server archive metadata mismatch: {relative}")
            content = base64.b64decode(entry["content"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        git_sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()
        if git_sha != declared["git_sha"] or sha256 != declared["sha256"]:
            raise ValueError(f"Pinned server reference hash mismatch: {relative}")
        result.append(
            {
                "path": relative,
                "git_sha": git_sha,
                "sha256": sha256,
                "bytes": len(content),
                "revision": revision,
                "role": "server-reference",
            }
        )
    return result


def _server_reference_text(profile: dict, relative: str) -> str:
    revision = profile["source"]["server_reference"]["revision"]
    path = ROOT / "assets/source/content/server" / revision / relative
    try:
        return path.read_text()
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _selected_progression(profile: dict) -> dict:
    definitions = parse_progression_definitions(
        _server_reference_text(profile, "src/game/src/constants.cpp"),
        _server_reference_text(profile, "src/common/length.h"),
        _server_reference_text(profile, "src/game/src/config.cpp"),
    ).to_record()
    selected = profile["trusted_gameplay"]["progression"]
    expected = {
        "supported_character_class": 0,
        "supported_sex": 0,
        "mob_exp_rate_percent": 100,
        "selected_modifiers": "all-zero-or-disabled",
        "stat_cap": 90,
        "stat_point_last_level_exclusive": 91,
        "low_level_death_loss_exclusive": 10,
        "quarter_reward_count": 2,
        "small_potion_vnum": 27001,
        "medium_potion_vnum": 27002,
        "small_potion_resulting_level_max": 10,
        "item_stack_limit": 200,
        "automatic_drop_reservation_us": 60_000_000,
        "automatic_drop_expiry_us": 300_000_000,
        "eligibility_distance_source_cm": 5000,
    }
    if selected != expected:
        raise ValueError("The selected progression profile constants changed without a contract")

    mob_lines = _server_reference_text(profile, "gamefiles/conf/mob_proto.txt").splitlines()
    mob_header = mob_lines[0].split("\t")
    mob_rows = [dict(zip(mob_header, line.split("\t"), strict=True)) for line in mob_lines[1:]]
    mob = next((row for row in mob_rows if row["VNUM"] == "101"), None)
    if mob is None or int(mob["LEVEL"]) != 1 or int(mob["EXP"]) != 15:
        raise ValueError("Pinned mob_proto must define Wild Dog 101 as level 1 with EXP 15")

    item_rows = {
        int(parts[0]): parts
        for line in _server_reference_text(profile, "gamefiles/conf/item_proto.txt").splitlines()[
            1:
        ]
        if (parts := line.split("\t")) and parts[0].isdigit()
    }
    item_names = {
        int(parts[0]): parts[1]
        for line in _server_reference_text(
            profile, "gamefiles/conf/item_names_en.txt"
        ).splitlines()[1:]
        if len(parts := line.split("\t", 1)) == 2 and parts[0].isdigit()
    }
    reward_items = []
    for vnum, expected_name in ((27001, "Red Potion(S)"), (27002, "Red Potion(M)")):
        row = item_rows.get(vnum)
        if (
            row is None
            or len(row) < 7
            or row[2:5] != ["ITEM_USE", "USE_POTION", "1"]
            or "ITEM_STACKABLE" not in row[6].split(" | ")
            or item_names.get(vnum) != expected_name
        ):
            raise ValueError(f"Pinned item catalogs do not define selected potion {vnum}")
        reward_items.append(
            {
                "vnum": vnum,
                "source_name": expected_name,
                "presentation_name": expected_name.replace("(", " (").replace(")", ")"),
                "size": 1,
                "stack_limit": selected["item_stack_limit"],
            }
        )

    stack_source = _server_reference_text(profile, "src/common/item_length.h")
    if len(re.findall(r"\bITEM_MAX_COUNT\s*=\s*200\s*,", stack_source)) != 1:
        raise ValueError("Pinned item stack limit is missing or ambiguous")

    return definitions | {
        "selected_profile": selected,
        "monster_reward": {"vnum": 101, "level": 1, "experience": 15},
        "reward_items": reward_items,
    }


def source_archive(offline: bool) -> Archive:
    archive = Archive(offline=offline)
    archive.sources = ROOT / "assets/source/content" / METIN_COMMIT
    archive.inventory()
    return archive


def archive_virtual(path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) < 4 or parts[:2] != ("bin", "pack"):
        raise ValueError(f"Expected archive pack path, got {path!r}")
    return virtual_path("/".join(parts[3:]))


def _get_text(archive: Archive, path: str) -> str:
    content = archive.get(path).read_bytes()
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        # The pinned Python catalog contains legacy locale comments. The selected
        # identifiers and paths are ASCII; latin-1 preserves every other byte.
        return content.decode("latin-1")


def _validate_catalogs(profile: dict, archive: Archive) -> dict:
    catalog = {path: _get_text(archive, path) for path in profile["catalog_sources"]}
    dog = next(actor for actor in profile["actors"] if actor["kind"] == "mob")
    npc_rows = [line.split() for line in catalog["bin/pack/root/npclist.txt"].splitlines()]
    match = next((row for row in npc_rows if row and row[0] == str(dog["vnum"])), None)
    if match is None or len(match) < 2 or match[1] != dog["model_key"]:
        raise ValueError(f"npclist does not map vnum {dog['vnum']} to {dog['model_key']}")
    warrior = next(actor for actor in profile["actors"] if actor["kind"] == "player")
    settings = catalog["bin/pack/root/playersettingmodule.py"]
    required_fragments = [
        "RACE_WARRIOR_M\t= 0",
        '__LoadGameWarriorEx(RACE_WARRIOR_M, "d:/ymir work/pc/warrior/")',
        'RegisterAttachingBoneName(chr.PART_WEAPON, "equip_right_hand")',
    ]
    for fragment in required_fragments:
        if fragment not in settings:
            raise ValueError(f"Missing canonical warrior registration: {fragment}")
    race = parse_race_script(_get_text(archive, warrior["race_script"]))
    if race["base_model"] != archive_virtual(warrior["model"]):
        raise ValueError("Male Warrior race script does not select the declared model")
    selected_hair = warrior.get("default_hair")
    if not isinstance(selected_hair, dict):
        raise ValueError("Male Warrior requires one declared default hair record")
    expected_hair = {
        "hair_index": selected_hair.get("hair_index"),
        "model": archive_virtual(selected_hair.get("model", "")),
        "source_skin": archive_virtual(selected_hair.get("source_skin", "")),
        "target_skin": archive_virtual(selected_hair.get("target_skin", "")),
    }
    if expected_hair not in race["hair"] or expected_hair["hair_index"] != 0:
        raise ValueError("Male Warrior race script does not select declared HairIndex 0")
    dog_race = parse_race_script(_get_text(archive, dog["race_script"]))
    if dog_race["base_model"] != archive_virtual(dog["model"]):
        raise ValueError("Wild Dog race script does not select the declared model")
    motion_list = parse_motion_list(_get_text(archive, dog["motion_list"]))
    selected_dog_files = {
        virtual_path(file)
        for mode in dog["modes"]
        for motion in mode["motions"]
        for file in motion["files"]
    }
    listed = {entry["path"] for entry in motion_list}
    missing = sorted(selected_dog_files - listed)
    if missing:
        raise ValueError(f"Wild Dog motlist omits selected files: {missing}")
    return {
        "npc_registration": {"vnum": dog["vnum"], "model_key": match[1]},
        "wild_dog_motion_list": motion_list,
        "wild_dog_unselected_motions": sorted(listed - selected_dog_files),
        "race_collision": {dog["id"]: dog_race["collision"]},
    }


def _motion_path(actor: dict, relative: str) -> str:
    return safe_path(f"{actor['motion_root'].rstrip('/')}/{relative}")


def rotate_actor_local_vector(vector: list[float], yaw_degrees: float) -> list[float]:
    radians = math.radians(yaw_degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    x, y, z = vector
    return [cosine * x + sine * z, y, -sine * x + cosine * z]


def _orient_motion_vectors(motion: dict, yaw_degrees: float) -> None:
    motion["accumulation_m"] = rotate_actor_local_vector(motion["accumulation_m"], yaw_degrees)
    for event in motion["events"]:
        event["coordinate_space"] = "output_actor_local_godot"
        for sample in event.get("samples", []):
            sample["start_m"] = rotate_actor_local_vector(sample["start_m"], yaw_degrees)
            sample["end_m"] = rotate_actor_local_vector(sample["end_m"], yaw_degrees)
        for sphere in event.get("spheres", []):
            sphere["position_m"] = rotate_actor_local_vector(sphere["position_m"], yaw_degrees)


def _normalise_motions(profile: dict, archive: Archive) -> tuple[list[dict], list[dict]]:
    actors, unsupported = [], []
    for actor in profile["actors"]:
        archive.get(actor["model"])
        modes = []
        for mode in actor["modes"]:
            motions = []
            for declaration in mode["motions"]:
                weights = declaration.get(
                    "weights", [100] if len(declaration["files"]) == 1 else None
                )
                for index, (relative, weight) in enumerate(
                    zip(declaration["files"], weights, strict=True)
                ):
                    msa_path = _motion_path(actor, relative)
                    parsed = parse_msa(_get_text(archive, msa_path))
                    _orient_motion_vectors(parsed, actor["orientation"]["yaw_correction_degrees"])
                    gr2_path = archive.resolve(parsed["motion_file"])
                    if Path(gr2_path).suffix.lower() != ".gr2":
                        raise ValueError(f"MSA did not resolve to GR2: {msa_path}")
                    gr2_local = archive.get(gr2_path)
                    base_id = f"{actor['id']}.{mode['id']}.{declaration['action']}"
                    action_id = (
                        base_id if len(declaration["files"]) == 1 else f"{base_id}.v{index + 1}"
                    )
                    godot_name = re.sub(r"[^A-Za-z0-9_]+", "_", action_id).strip("_")
                    root_motion_source = None
                    if action_id in EXPECTED_ROOT_MOTION_INPUTS:
                        root_motion_source = extract_root_motion(
                            gr2_local,
                            archive.get(msa_path),
                            source_gr2=gr2_path,
                            source_msa=msa_path,
                            action_id=action_id,
                            duration_us=parsed["duration_us"],
                            msa_accumulation_m=parsed["accumulation_m"],
                            yaw_degrees=actor["orientation"]["yaw_correction_degrees"],
                        )
                    for entry in parsed.pop("unsupported"):
                        unsupported.append(
                            {
                                "actor_id": actor["id"],
                                "action_id": action_id,
                                "source": msa_path,
                                **entry,
                            }
                        )
                    motions.append(
                        {
                            "action_id": action_id,
                            "action": declaration["action"],
                            "variant": index + 1,
                            "weight": weight,
                            "godot_name": godot_name,
                            "loop": declaration["loop"],
                            "fallback_mode": declaration.get("fallback_mode"),
                            "source_msa": msa_path,
                            "source_gr2": gr2_path,
                            **(
                                {"root_motion_source": root_motion_source}
                                if root_motion_source is not None
                                else {}
                            ),
                            **parsed,
                        }
                    )
            modes.append(
                {
                    "id": mode["id"],
                    "required_item_vnums": mode.get("required_item_vnums", []),
                    "combo_chains": mode.get("combo_chains", []),
                    "motions": motions,
                }
            )
        actors.append(
            {
                "id": actor["id"],
                "kind": actor["kind"],
                **(
                    {"race_id": actor["race_id"]} if "race_id" in actor else {"vnum": actor["vnum"]}
                ),
                "name": actor.get("name"),
                "model_key": actor["model_key"],
                "source_model": actor["model"],
                "source_textures": actor["textures"],
                **({"default_hair": actor["default_hair"]} if "default_hair" in actor else {}),
                "output": actor["output"],
                "orientation": actor["orientation"],
                "motion_vector_space": "output_actor_local_godot",
                "attachment_bones": actor.get("attachment_bones", {}),
                "modes": modes,
            }
        )
    return actors, unsupported


def _normalise_items(profile: dict, archive: Archive) -> list[dict]:
    result = []
    for item in profile["items"]:
        parsed = parse_item_script(_get_text(archive, item["script"]))
        expected = archive_virtual(item["model"])
        if parsed["model"] != expected or parsed["drop_model"] != expected:
            raise ValueError(f"Item script does not select declared model for {item['id']}")
        archive.get(item["model"])
        transform = item["attachment_transform"]
        values = [*transform["translation_m"], *transform["rotation_degrees"], *transform["scale"]]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite attachment transform for {item['id']}")
        result.append(
            {
                "id": item["id"],
                "vnum": item["vnum"],
                "name": item["name"],
                "kind": item["kind"],
                "equipment_mode": item["equipment_mode"],
                "source_model": item["model"],
                "source_textures": item["textures"],
                "output": item["output"],
                "actor_attachment": item["actor_attachment"],
                "attachment_transform": transform,
            }
        )
    return result


def _source_records(archive: Archive, server_sources: list[dict]) -> list[dict]:
    records = [
        {"path": path, **metadata, "revision": METIN_COMMIT}
        for path, metadata in sorted(archive.used.items())
    ]
    records.extend(server_sources)
    return sorted(records, key=lambda entry: (entry["revision"], entry["path"]))


def compile_normalized(profile_path: Path, *, offline: bool) -> dict:
    profile = load_profile(profile_path)
    archive = source_archive(offline)
    server_sources = fetch_server_references(profile, offline=offline)
    initial_paths = set(profile["catalog_sources"])
    for actor in profile["actors"]:
        initial_paths.update({actor["race_script"], actor["model"], *actor["textures"]})
        if "default_hair" in actor:
            initial_paths.update(
                {
                    actor["default_hair"]["model"],
                    actor["default_hair"]["source_skin"],
                    actor["default_hair"]["target_skin"],
                }
            )
        if "motion_list" in actor:
            initial_paths.add(actor["motion_list"])
        initial_paths.update(
            _motion_path(actor, relative)
            for mode in actor["modes"]
            for motion in mode["motions"]
            for relative in motion["files"]
        )
    for item in profile["items"]:
        initial_paths.update({item["script"], item["model"], *item["textures"]})
    archive.fetch_many(initial_paths)
    catalog = _validate_catalogs(profile, archive)
    progression = _selected_progression(profile)
    actors, unsupported = _normalise_motions(profile, archive)
    items = _normalise_items(profile, archive)
    sources = _source_records(archive, server_sources)
    identity_input = {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "profile": profile,
        "sources": sources,
    }
    unsupported = sorted(
        unsupported,
        key=lambda entry: (entry["source"], entry["action_id"], entry["kind"]),
    )
    adapted_motion_events = []
    remaining_unsupported = []
    for entry in unsupported:
        if entry.get("action_id") == PLAYER_COMBO_ACTION_IDS[3] and entry.get("event_type") == 2:
            adapted_motion_events.append(
                {
                    **entry,
                    "parser_classification": entry["reason"],
                    "reason": "adapted by the bounded schema5 screen-wave projection",
                    "adapter": "screen-wave-schema5",
                }
            )
        else:
            remaining_unsupported.append(entry)
    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "reader_version": 1,
        "profile_id": profile["profile_id"],
        "content_hash": digest(identity_input),
        "coordinates": profile["coordinates"],
        "distribution": profile["distribution"],
        "sources": sources,
        "catalog_validation": catalog,
        "progression": progression,
        "actors": actors,
        "items": items,
        "known_exclusions": profile["known_exclusions"],
        "adapted_motion_events": adapted_motion_events,
        "unsupported": remaining_unsupported,
    }
    return result


def _events_for_server(motion: dict, configured_range: float) -> list[dict]:
    windows = []
    for event in motion["events"]:
        if event["kind"] == "attack_window" and event["start_us"] < event["end_us"]:
            windows.append(
                {
                    "start_us": event["start_us"],
                    "end_us": event["end_us"],
                    "range_m": configured_range,
                    "shape": "melee_reach",
                }
            )
    return windows


def _ordinary_hit_invulnerability(motion: dict) -> int:
    expected = ORDINARY_HIT_INVULNERABILITY_US[motion["action_id"]]
    ordinary = [event for event in motion["events"] if event.get("kind") == "attack_window"]
    if len(ordinary) != 1:
        raise ValueError(f"{motion['action_id']} requires one authored ordinary attack record")
    actual = ordinary[0].get("source_parameters", {}).get("invisible_us")
    if motion["action_id"] == PLAYER_COMBO_ACTION_IDS[3]:
        if ordinary[0].get("sample_count") != 0 or actual != 100_000:
            raise ValueError("combo_4 empty ordinary attack source evidence changed")
        return 0
    if actual != expected:
        raise ValueError(f"{motion['action_id']} ordinary hit invulnerability changed")
    return expected


def _primary_motion(actor: dict, mode_id: str, action: str) -> dict:
    modes = [mode for mode in actor["modes"] if mode["id"] == mode_id]
    if len(modes) != 1:
        raise ValueError(f"Expected exactly one mode {actor['id']}.{mode_id}")
    mode = modes[0]
    matches = [motion for motion in mode["motions"] if motion["action"] == action]
    if not matches:
        raise ValueError(f"Missing primary action {actor['id']}.{mode_id}.{action}")
    return matches[0]


def _selected_combo_prefix(player: dict) -> tuple[dict, list[dict]]:
    modes = [mode for mode in player["modes"] if mode["id"] == "onehand"]
    if len(modes) != 1:
        raise ValueError("Expected exactly one selected onehand mode")
    mode = modes[0]
    if mode.get("required_item_vnums") != [10]:
        raise ValueError("Selected onehand mode must require only Sword+0 vnum 10")
    chains = mode.get("combo_chains")
    if not isinstance(chains, list) or not chains:
        raise ValueError("Selected onehand mode requires declared combo chains")
    for chain in chains:
        if not isinstance(chain, list) or len(chain) < 3:
            raise ValueError("Every declared combo chain requires at least three actions")
        if any(type(name) is not str or not name for name in chain):
            raise ValueError("Selected combo chain action names must be nonempty strings")
    if len(chains[0]) < 4:
        raise ValueError("Selected default combo chain requires four actions")
    prefix = chains[0][:4]
    if prefix != ["combo_1", "combo_2", "combo_3", "combo_4"] or len(set(prefix)) != 4:
        raise ValueError("Selected combo prefix must be distinct combo_1 through terminal combo_4")
    if any(chain[:3] != prefix[:3] for chain in chains):
        raise ValueError("Declared combo chains disagree on the common three-action prefix")
    motions = []
    for name in prefix:
        matches = [motion for motion in mode["motions"] if motion["action"] == name]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one selected combo motion for {name}")
        motions.append(matches[0])
    if [motion.get("action_id") for motion in motions] != list(PLAYER_COMBO_ACTION_IDS):
        raise ValueError("Selected combo prefix action IDs do not match the fixed fixture")
    return mode, motions


def _checked_combo_input(value: object, duration_us: int, context: str) -> dict:
    if type(duration_us) is not int or not 0 < duration_us <= MAX_COMBO_TIME_US:
        raise ValueError(f"{context} duration must be integer microseconds in 1..=60000000")
    if not isinstance(value, dict) or set(value) != COMBO_INPUT_FIELDS:
        raise ValueError(f"{context} combo_input must contain exactly four timing fields")
    if any(type(value[field]) is not int for field in COMBO_INPUT_FIELDS):
        raise ValueError(f"{context} combo_input fields must be exact integers")
    pre = value["pre_input_us"]
    direct = value["direct_input_us"]
    limit = value["input_limit_us"]
    link = value["link_us"]
    if not 0 <= pre < direct < limit <= duration_us:
        raise ValueError(f"{context} combo input window is not strictly ordered")
    if not 0 <= link <= MAX_COMBO_TIME_US:
        raise ValueError(f"{context} combo link is outside the supported bound")
    return {field: value[field] for field in sorted(COMBO_INPUT_FIELDS)}


def _finite_number(value: object, label: str, bound: float) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if abs(result) > bound:
        raise ValueError(f"{label} exceeds the supported bound")
    return result


def _strict_json_equal(value: object, expected: object) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(
            _strict_json_equal(value[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(value) == len(expected) and all(
            _strict_json_equal(actual, wanted)
            for actual, wanted in zip(value, expected, strict=True)
        )
    return value == expected


def _finite_vector(value: object, length: int, label: str, bound: float) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} must contain exactly {length} values")
    return [_finite_number(component, label, bound) for component in value]


def _decimal_number(value: object, label: str, bound: float) -> float:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > 32:
        raise ValueError(f"{label} must be a bounded decimal string")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a finite decimal string") from error
    if not math.isfinite(number) or abs(number) > bound:
        raise ValueError(f"{label} must be a finite bounded decimal string")
    return number


def _decimal_vector(value: object, length: int, label: str, bound: float) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} must contain exactly {length} decimal strings")
    return [_decimal_number(component, label, bound) for component in value]


def _checked_root_motion(value: object, duration_us: int, context: str) -> dict:
    if not isinstance(value, dict) or set(value) != ROOT_MOTION_FIELDS:
        raise ValueError(f"{context} root_motion must contain exactly x, z, and duration")
    endpoint_x = _finite_number(
        value["endpoint_x_m"], f"{context} root_motion.endpoint_x_m", MAX_ENDPOINT_COMPONENT_M
    )
    endpoint_z = _finite_number(
        value["endpoint_z_m"], f"{context} root_motion.endpoint_z_m", MAX_ENDPOINT_COMPONENT_M
    )
    if (
        type(value["duration_us"]) is not int
        or not 0 < value["duration_us"] <= MAX_ROOT_MOTION_DURATION_US
        or value["duration_us"] != duration_us
    ):
        raise ValueError(f"{context} root_motion duration must equal the action duration")
    return {
        "duration_us": duration_us,
        "endpoint_x_m": endpoint_x,
        "endpoint_z_m": endpoint_z,
    }


def _checked_root_motion_source(
    value: object, action_id: str, action_root_motion: dict, duration_us: int
) -> dict:
    fields = {
        "action_id",
        "source_gr2",
        "source_msa",
        "carbon_reader",
        "animation_count",
        "animation_duration_s_raw_decimal",
        "animation_duration_us_rounded",
        "track_group_count",
        "track_group_name",
        "accumulation_flags",
        "loop_translation_source_cm_decimal",
        "endpoint_output_actor_local_godot_m_decimal",
        "periodic_loop",
        "root_motion",
        "initial_placement",
        "msa_accumulation_output_actor_local_godot_m_decimal",
        "msa_discrepancy_output_actor_local_godot_m_decimal",
        "msa_validation",
    }
    if not isinstance(value, dict) or set(value) != fields or value.get("action_id") != action_id:
        raise ValueError(f"{action_id} root-motion source record is malformed")
    expected = EXPECTED_ROOT_MOTION_INPUTS[action_id]
    for label, suffix in (("source_gr2", "gr2"), ("source_msa", "msa")):
        source = value[label]
        if not isinstance(source, dict) or set(source) != {"path", "sha256", "bytes"}:
            raise ValueError(f"{action_id} {label} provenance is malformed")
        if (
            source["path"] != expected[f"{suffix}_path"]
            or source["sha256"] != expected[suffix]
            or type(source["bytes"]) is not int
            or source["bytes"] != expected[f"{suffix}_bytes"]
        ):
            raise ValueError(f"{action_id} {label} provenance does not match the pin")
    carbon = value["carbon_reader"]
    if carbon != {
        "commit": "8cba23114bf1d30c9da597c1ecf49271e00b939d",
        "sha256": "c3c8698c5987b6783586cc312e291e63eb315f8a5b0968b4f556219688a0fdce",
    }:
        raise ValueError(f"{action_id} Carbon raw reader pin changed")
    if (
        type(value["animation_count"]) is not int
        or value["animation_count"] != 1
        or type(value["track_group_count"]) is not int
        or value["track_group_count"] != 1
        or value["track_group_name"] != "Bip01"
        or type(value["accumulation_flags"]) is not int
        or value["accumulation_flags"] != 3
        or value["periodic_loop"] is not None
        or value["root_motion"] is not None
    ):
        raise ValueError(f"{action_id} raw GR2 accumulation metadata is unsupported")
    raw_duration = _decimal_number(
        value["animation_duration_s_raw_decimal"],
        f"{action_id} raw animation duration",
        MAX_ROOT_MOTION_DURATION_US / 1_000_000,
    )
    if raw_duration <= 0 or round(raw_duration * 1_000_000) != duration_us:
        raise ValueError(f"{action_id} raw GR2 duration does not match the action")
    if (
        type(value["animation_duration_us_rounded"]) is not int
        or value["animation_duration_us_rounded"] != duration_us
    ):
        raise ValueError(f"{action_id} rounded raw GR2 duration is invalid")
    source_endpoint = _decimal_vector(
        value["loop_translation_source_cm_decimal"],
        3,
        f"{action_id} raw LoopTranslation",
        MAX_SOURCE_COMPONENT_CM,
    )
    expected_endpoint = source_cm_to_output_actor_local_m(source_endpoint, 180.0)
    reported_endpoint = _decimal_vector(
        value["endpoint_output_actor_local_godot_m_decimal"],
        3,
        f"{action_id} converted endpoint",
        MAX_ENDPOINT_COMPONENT_M,
    )
    if reported_endpoint != expected_endpoint or reported_endpoint[1] != 0.0:
        raise ValueError(f"{action_id} endpoint coordinate conversion is invalid")
    if (
        action_root_motion["endpoint_x_m"] != reported_endpoint[0]
        or action_root_motion["endpoint_z_m"] != reported_endpoint[2]
    ):
        raise ValueError(f"{action_id} runtime endpoint does not match raw GR2 metadata")
    msa_endpoint = _decimal_vector(
        value["msa_accumulation_output_actor_local_godot_m_decimal"],
        3,
        f"{action_id} MSA accumulation",
        MAX_ENDPOINT_COMPONENT_M,
    )
    differences = [msa_endpoint[index] - reported_endpoint[index] for index in range(3)]
    reported_difference = _decimal_vector(
        value["msa_discrepancy_output_actor_local_godot_m_decimal"],
        3,
        f"{action_id} MSA discrepancy",
        MAX_ENDPOINT_COMPONENT_M,
    )
    if reported_difference != differences:
        raise ValueError(f"{action_id} MSA discrepancy evidence changed")
    if action_id == PLAYER_COMBO_ACTION_IDS[3]:
        if (
            value["msa_validation"] != "pinned-combo4-discrepancy-exception"
            or reported_endpoint != [0.0, 0.0, -1.1964712524414062]
            or msa_endpoint != [0.1289, 0.0, -1.0552]
        ):
            raise ValueError("Pinned combo_4 MSA discrepancy exception changed")
    elif value["msa_validation"] != "strict-rounded-corroboration" or any(
        abs(component) > MSA_COMPONENT_TOLERANCE_M for component in differences
    ):
        raise ValueError(f"{action_id} MSA accumulation does not corroborate the raw endpoint")
    placement = value["initial_placement"]
    if not isinstance(placement, dict) or set(placement) != {
        "flags",
        "position_source_cm_decimal",
        "orientation_xyzw_decimal",
    }:
        raise ValueError(f"{action_id} InitialPlacement evidence is malformed")
    if type(placement["flags"]) is not int or not 0 <= placement["flags"] <= 0xFFFFFFFF:
        raise ValueError(f"{action_id} InitialPlacement flags are invalid")
    _decimal_vector(
        placement["position_source_cm_decimal"],
        3,
        f"{action_id} InitialPlacement position",
        MAX_INITIAL_PLACEMENT_COMPONENT_CM,
    )
    _decimal_vector(
        placement["orientation_xyzw_decimal"],
        4,
        f"{action_id} InitialPlacement orientation",
        2.0,
    )
    return value


def _selected_special_area(motion: dict) -> dict:
    areas = [event for event in motion["events"] if event.get("kind") == "attack_area"]
    if len(areas) != 1:
        raise ValueError("Selected combo_4 requires exactly one special area event")
    area = areas[0]
    spheres = area.get("spheres")
    if (
        area.get("start_us") != 659_316
        or area.get("end_us") != 859_316
        or area.get("attack_type") != 0
        or area.get("hitting_type") != 1
        or area.get("stiffen_us") != 0
        or area.get("invisible_us") != 300_000
        or area.get("external_force") != 17.0
        or area.get("collision_type") != 0
        or not isinstance(spheres, list)
        or len(spheres) != 1
    ):
        raise ValueError("Selected combo_4 special area source fields changed")
    sphere = spheres[0]
    center = _finite_vector(sphere.get("position_m"), 3, "combo_4 area center", 2.0)
    center = [0.0 if abs(value) < 1e-12 else value for value in center]
    if center != [0.0, 0.0, -1.2] or sphere.get("radius_m") != 1.0:
        raise ValueError("Selected combo_4 special area sphere changed")
    return {
        "authored_start_us": 659_316,
        "legacy_dispatch_frame": 39,
        "activation_offset_us": 666_667,
        "duration_us": 200_000,
        "local_center_x_m": 0.0,
        "local_center_z_m": -1.2,
        "radius_m": 1.0,
        "max_targets": 16,
        "hit_once_per_life": True,
        "hit_type": 1,
        "invulnerability_us": 300_000,
        "knockback": {
            "source_external_force": 17.0,
            "unobstructed_distance_m": 4.732,
            "duration_us": 1_000_000,
        },
    }


def _selected_screen_wave(normalized: dict, motion: dict) -> dict:
    matches = [
        event
        for event in normalized.get("adapted_motion_events", [])
        if event.get("action_id") == motion["action_id"] and event.get("event_type") == 2
    ]
    if len(matches) != 1:
        raise ValueError("Selected combo_4 requires exactly one screen-wave source event")
    event = matches[0]
    if (
        event.get("start_us") != 630_086
        or event.get("end_us") != 830_086
        or event.get("fields")
        != {
            "AffectingRange": ["200"],
            "DuringTime": ["0.200000"],
            "MotionEventType": ["2"],
            "Power": ["300"],
            "StartingTime": ["0.630086"],
        }
    ):
        raise ValueError("Selected combo_4 screen-wave source fields changed")
    return {
        "authored_start_us": 630_086,
        "legacy_dispatch_frame": 37,
        "activation_offset_us": 633_334,
        "duration_us": 200_000,
        "viewer_range_m": 2.0,
        "source_power": 300,
        "source_component_step_m": 0.001,
        "source_component_exclusive_max_m": 0.3,
    }


def _selected_defending_sphere(normalized: dict) -> dict:
    collision = normalized.get("catalog_validation", {}).get("race_collision", {}).get(MOB_ACTOR_ID)
    matches = [row for row in collision or [] if row.get("collision_type") == 3]
    if len(matches) != 1 or matches[0].get("bone") != "Bip01":
        raise ValueError("Wild Dog requires exactly one Bip01 defending collision record")
    spheres = matches[0].get("spheres")
    if not isinstance(spheres, list) or len(spheres) != 1:
        raise ValueError("Wild Dog requires exactly one defending sphere")
    sphere = spheres[0]
    if sphere != {"position_m": [0.0, 0.8, 0.1], "radius_m": 0.9}:
        raise ValueError("Wild Dog defending sphere changed from the pinned fixture")
    return {
        "local_center_x_m": 0.0,
        "local_center_y_m": 0.8,
        "local_center_z_m": 0.1,
        "radius_m": 0.9,
    }


def _selected_reactions(mob: dict) -> list[dict]:
    result = []
    for action, action_id in MOB_REACTION_IDS.items():
        motion = _primary_motion(mob, "general", action)
        if (
            motion["action_id"] != action_id
            or motion["duration_us"] != MOB_REACTION_DURATIONS_US[action]
        ):
            raise ValueError(f"Wild Dog reaction {action} changed from the pinned fixture")
        result.append({"id": action_id, "duration_us": motion["duration_us"]})
    return result


def make_server_payload(profile: dict, normalized: dict) -> dict:
    gameplay = profile["trusted_gameplay"]
    normalized_actors = normalized.get("actors")
    if not isinstance(normalized_actors, list) or any(
        not isinstance(actor, dict) for actor in normalized_actors
    ):
        raise ValueError("Normalized actors must be objects")
    players = [actor for actor in normalized_actors if actor.get("kind") == "player"]
    mobs = [actor for actor in normalized_actors if actor.get("kind") == "mob"]
    if len(players) != 1 or len(mobs) != 1:
        raise ValueError("Trusted payload requires exactly one selected player and mob")
    player, mob = players[0], mobs[0]
    if player.get("id") != PLAYER_ACTOR_ID or mob.get("id") != MOB_ACTOR_ID:
        raise ValueError("Selected trusted actors do not match the fixed profile")
    if gameplay["player"].get("primary_actions", {}).get("onehand") != "combo_1":
        raise ValueError("Selected onehand primary action must be combo_1")
    onehand_mode, combo_motions = _selected_combo_prefix(player)
    combo_by_action = {motion["action"]: motion for motion in combo_motions}
    root_motion_sources = []

    def selected_root_motion(motion: dict) -> dict:
        source = motion.get("root_motion_source")
        if not isinstance(source, dict):
            raise ValueError(
                f"Selected combo action has no raw root-motion metadata: {motion['action_id']}"
            )
        endpoint = source.get("endpoint_output_actor_local_godot_m_decimal")
        if not isinstance(endpoint, list) or len(endpoint) != 3:
            raise ValueError(
                f"Selected combo action has a malformed root endpoint: {motion['action_id']}"
            )
        endpoint = [
            _decimal_number(
                component,
                f"{motion['action_id']} root endpoint",
                MAX_ENDPOINT_COMPONENT_M,
            )
            for component in endpoint
        ]
        root_motion = _checked_root_motion(
            {
                "endpoint_x_m": endpoint[0],
                "endpoint_z_m": endpoint[2],
                "duration_us": motion["duration_us"],
            },
            motion["duration_us"],
            motion["action_id"],
        )
        root_motion_sources.append(
            _checked_root_motion_source(
                source, motion["action_id"], root_motion, motion["duration_us"]
            )
        )
        return root_motion

    actions = []
    player_primary = {}
    for mode_id, action_name in sorted(gameplay["player"]["primary_actions"].items()):
        motion = _primary_motion(player, mode_id, action_name)
        windows = _events_for_server(motion, gameplay["player"]["attack_range_m"])
        if not windows:
            raise ValueError(f"Primary player action has no hit window: {motion['action_id']}")
        player_primary[mode_id] = motion["action_id"]
        actions.append(
            {
                "id": motion["action_id"],
                "actor_id": player["id"],
                "mode": mode_id,
                "action": action_name,
                "duration_us": motion["duration_us"],
                "cooldown_us": gameplay["player"]["attack_cooldown_us"],
                "hit_windows": windows,
                "ordinary_hit_invulnerability_us": _ordinary_hit_invulnerability(motion),
                "required_item_vnums": next(
                    mode["required_item_vnums"] for mode in player["modes"] if mode["id"] == mode_id
                ),
                **(
                    {
                        "combo_input": _checked_combo_input(
                            motion.get("combo"),
                            motion["duration_us"],
                            motion["action_id"],
                        ),
                        "root_motion": selected_root_motion(motion),
                    }
                    if mode_id == "onehand"
                    else {}
                ),
            }
        )
    for action_name in ("combo_2", "combo_3", "combo_4"):
        motion = combo_by_action[action_name]
        windows = _events_for_server(motion, gameplay["player"]["attack_range_m"])
        if action_name != "combo_4" and not windows:
            raise ValueError(f"Selected combo action has no hit window: {motion['action_id']}")
        if action_name == "combo_4":
            ordinary = [event for event in motion["events"] if event.get("kind") == "attack_window"]
            if len(ordinary) != 1 or ordinary[0].get("sample_count") != 0 or windows:
                raise ValueError("Selected combo_4 must have no ordinary hit trace")
            if motion.get("combo") != {
                "pre_input_us": 1_057_692,
                "direct_input_us": 1_057_692,
                "input_limit_us": 730_769,
                "link_us": 0,
            }:
                raise ValueError("Selected terminal combo_4 timing evidence changed")
        actions.append(
            {
                "id": motion["action_id"],
                "actor_id": player["id"],
                "mode": "onehand",
                "action": action_name,
                "duration_us": motion["duration_us"],
                "cooldown_us": gameplay["player"]["attack_cooldown_us"],
                "hit_windows": windows,
                "ordinary_hit_invulnerability_us": _ordinary_hit_invulnerability(motion),
                "required_item_vnums": onehand_mode["required_item_vnums"],
                "root_motion": selected_root_motion(motion),
                **(
                    {
                        "special_area": _selected_special_area(motion),
                        "screen_wave": _selected_screen_wave(normalized, motion),
                    }
                    if action_name == "combo_4"
                    else {
                        "combo_input": _checked_combo_input(
                            motion.get("combo"), motion["duration_us"], motion["action_id"]
                        )
                    }
                ),
            }
        )
    mob_motion = _primary_motion(mob, "general", "normal_attack")
    mob_windows = _events_for_server(mob_motion, gameplay["mob"]["attack_range_m"])
    if not mob_windows:
        raise ValueError("Primary mob action has no hit window")
    actions.append(
        {
            "id": mob_motion["action_id"],
            "actor_id": mob["id"],
            "mode": "general",
            "action": "normal_attack",
            "duration_us": mob_motion["duration_us"],
            "cooldown_us": gameplay["mob"]["attack_cooldown_us"],
            "hit_windows": mob_windows,
            "ordinary_hit_invulnerability_us": _ordinary_hit_invulnerability(mob_motion),
            "required_item_vnums": [],
        }
    )
    payload = {
        "schema": SERVER_SCHEMA,
        "schema_version": SERVER_SCHEMA_VERSION,
        "profile_id": profile["profile_id"],
        "content_hash": normalized["content_hash"],
        "time_unit": "microsecond",
        "linear_unit": "meter",
        "root_motion_policy": ROOT_MOTION_POLICY,
        "root_motion_sources": root_motion_sources,
        "special_area_policy": SPECIAL_AREA_POLICY,
        "screen_wave_policy": SCREEN_WAVE_POLICY,
        "defending_sphere_policy": DEFENDING_SPHERE_POLICY,
        "actors": [
            {
                "id": player["id"],
                "race_id": player["race_id"],
                "model_key": player["model_key"],
                "base_damage": gameplay["player"]["base_damage"],
                "attack_range_m": gameplay["player"]["attack_range_m"],
                "attack_cooldown_us": gameplay["player"]["attack_cooldown_us"],
                "override_basis": gameplay["player"]["override_basis"],
                "primary_actions": player_primary,
            },
            {
                "id": mob["id"],
                **{key: value for key, value in gameplay["mob"].items() if key != "source_values"},
                "source_values": gameplay["mob"]["source_values"],
                "primary_action_id": mob_motion["action_id"],
                "defending_sphere": _selected_defending_sphere(normalized),
                "great_hit_reactions": _selected_reactions(mob),
            },
        ],
        "base_combo_prefix": list(PLAYER_COMBO_ACTION_IDS),
        "actions": sorted(actions, key=lambda action: action["id"]),
        "items": [gameplay["item"]],
        "progression": normalized["progression"],
    }
    payload["gameplay_definition_hash"] = digest(payload)
    validate_server_payload(payload, profile["profile_id"])
    return payload


def output_paths(profile_id: str) -> dict[str, Path]:
    return {
        "normalized": ROOT / ".local/content" / profile_id / "normalized-manifest.v1.json",
        "runtime_server": ROOT / "server/content" / profile_id / "actions.v1.json",
        "client": ROOT / "client/assets/imported/content" / profile_id / "manifest.v1.json",
        "report": ROOT / ".local/content" / profile_id / "report.v1.json",
        "blender_report": ROOT / ".local/content" / profile_id / "blender-report.v1.json",
        "godot_report": ROOT / ".local/content" / profile_id / "godot-report.v1.json",
    }


def write_compile_outputs(profile_path: Path, normalized: dict, server: dict) -> None:
    paths = output_paths(normalized["profile_id"])
    write_json(paths["normalized"], normalized)
    # serde_json 1.0.151 rounds this exact binary64 value upward when parsing
    # the longer Python spelling. Emit the adjacent shortest spelling that
    # parses to the source-derived binary64 in both languages; the canonical
    # hash remains over the decoded value and is independently recomputed.
    encoded_server = json.dumps(server, indent=2, sort_keys=True) + "\n"
    old = '"endpoint_z_m": -1.1964712524414063'
    new = '"endpoint_z_m": -1.1964712524414062'
    if encoded_server.count(old) != 1:
        raise ValueError("Pinned combo_4 endpoint serialization contract changed")
    target = paths["runtime_server"]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(encoded_server.replace(old, new))
    temporary.replace(target)
    write_json(
        paths["report"],
        {
            "schema_version": SCHEMA_VERSION,
            "profile_id": normalized["profile_id"],
            "profile": str(profile_path.relative_to(ROOT)),
            "content_hash": normalized["content_hash"],
            "gameplay_definition_hash": server["gameplay_definition_hash"],
            "source_count": len(normalized["sources"]),
            "motion_count": sum(
                len(mode["motions"]) for actor in normalized["actors"] for mode in actor["modes"]
            ),
            "unsupported": normalized["unsupported"],
            "adapted_motion_events": normalized["adapted_motion_events"],
            "status": "normalized",
        },
    )


def extract_actor_texture_pngs(output: Path, blender_report: dict) -> list[Path]:
    """Extract selected actor PNGs from GLBs without changing their bytes."""
    extracted = []
    for artifact in blender_report["artifacts"]:
        if artifact["type"] != "actor":
            continue
        glb_path = output / safe_path(artifact["relative_path"])
        payload = glb_path.read_bytes()
        if len(payload) < 20 or struct.unpack_from("<4sII", payload) != (
            b"glTF",
            2,
            len(payload),
        ):
            raise ValueError(f"Invalid generated actor GLB: {glb_path}")
        json_length, json_type = struct.unpack_from("<I4s", payload, 12)
        if json_type != b"JSON" or 20 + json_length > len(payload):
            raise ValueError(f"Invalid generated actor GLB JSON chunk: {glb_path}")
        document = json.loads(payload[20 : 20 + json_length])
        binary_offset = 20 + json_length
        if binary_offset + 8 > len(payload):
            raise ValueError(f"Missing generated actor GLB binary chunk: {glb_path}")
        binary_length, binary_type = struct.unpack_from("<I4s", payload, binary_offset)
        binary_start = binary_offset + 8
        if binary_type != b"BIN\x00" or binary_start + binary_length != len(payload):
            raise ValueError(f"Invalid generated actor GLB binary chunk: {glb_path}")
        buffer_views = document.get("bufferViews")
        if not isinstance(buffer_views, list):
            raise ValueError(f"Generated actor GLB has no buffer views: {glb_path}")
        for image in document.get("images", []):
            if image.get("mimeType") != "image/png" or not isinstance(image.get("name"), str):
                raise ValueError(f"Generated actor GLB has an unsupported image: {glb_path}")
            image_name = image["name"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", image_name):
                raise ValueError(f"Unsafe generated actor image name: {image_name!r}")
            index = image.get("bufferView")
            if type(index) is not int or not 0 <= index < len(buffer_views):
                raise ValueError(f"Generated actor GLB image buffer-view is invalid: {glb_path}")
            buffer_view = buffer_views[index]
            if not isinstance(buffer_view, dict):
                raise ValueError(f"Generated actor GLB image buffer-view is invalid: {glb_path}")
            offset = buffer_view.get("byteOffset", 0)
            length = buffer_view.get("byteLength")
            if type(offset) is not int or type(length) is not int or offset < 0 or length <= 0:
                raise ValueError(f"Generated actor GLB image byte range is invalid: {glb_path}")
            if buffer_view.get("buffer", 0) != 0:
                raise ValueError(f"Generated actor GLB image buffer is invalid: {glb_path}")
            start = binary_start + offset
            end = start + length
            if not binary_start <= start < end <= binary_start + binary_length:
                raise ValueError(f"Generated actor GLB image range is invalid: {glb_path}")
            target = glb_path.with_name(f"{glb_path.stem}_{image_name}.png")
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(payload[start:end])
            temporary.replace(target)
            write_actor_texture_import(target)
            extracted.append(target)
    if not extracted:
        raise ValueError("Generated profile has no selected actor PNG textures")
    return extracted


def validate_server_payload(payload: dict, profile_id: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Trusted action definitions must be an object")
    if (
        payload.get("schema") != SERVER_SCHEMA
        or payload.get("schema_version") != SERVER_SCHEMA_VERSION
    ):
        raise ValueError("Invalid trusted action schema")
    if payload.get("profile_id") != profile_id:
        raise ValueError("Trusted action profile mismatch")
    claimed = payload.get("gameplay_definition_hash")
    unhashed = {key: value for key, value in payload.items() if key != "gameplay_definition_hash"}
    if claimed != digest(unhashed):
        raise ValueError("Trusted action definition hash mismatch")
    actions = payload.get("actions")
    if not isinstance(actions, list) or len(actions) != 6:
        raise ValueError("Trusted definitions require exactly six actions")
    if any(not isinstance(action, dict) for action in actions):
        raise ValueError("Trusted actions must be objects")
    action_id_list = [action.get("id") for action in actions]
    if any(type(action_id) is not str or not action_id for action_id in action_id_list):
        raise ValueError("Trusted action IDs must be nonempty strings")
    if len(action_id_list) != len(set(action_id_list)):
        raise ValueError("Trusted action IDs must be unique")
    action_ids = set(action_id_list)
    if action_ids != EXPECTED_SERVER_ACTION_IDS:
        raise ValueError("Trusted action IDs do not match the fixed profile")
    prefix = payload.get("base_combo_prefix")
    if prefix != list(PLAYER_COMBO_ACTION_IDS):
        raise ValueError("Trusted base combo prefix is missing, reordered, or changed")
    if payload.get("root_motion_policy") != ROOT_MOTION_POLICY:
        raise ValueError("Trusted root-motion policy or limitation record changed")
    for field, expected in (
        ("special_area_policy", SPECIAL_AREA_POLICY),
        ("screen_wave_policy", SCREEN_WAVE_POLICY),
        ("defending_sphere_policy", DEFENDING_SPHERE_POLICY),
    ):
        if not _strict_json_equal(payload.get(field), expected):
            raise ValueError(f"Trusted {field} changed")
    root_sources = payload.get("root_motion_sources")
    if not isinstance(root_sources, list) or len(root_sources) != len(PLAYER_COMBO_ACTION_IDS):
        raise ValueError("Trusted definitions require exactly four root-motion source records")
    if [
        source.get("action_id") if isinstance(source, dict) else None for source in root_sources
    ] != list(PLAYER_COMBO_ACTION_IDS):
        raise ValueError("Trusted root-motion source records are missing, duplicate, or reordered")
    actors = payload.get("actors")
    if not isinstance(actors, list) or any(not isinstance(actor, dict) for actor in actors):
        raise ValueError("Trusted definitions require actors")
    player_rows = [actor for actor in actors if actor.get("id") == PLAYER_ACTOR_ID]
    if len(player_rows) != 1:
        raise ValueError("Trusted definitions require exactly one fixed player actor")
    player_primary = player_rows[0].get("primary_actions")
    if not isinstance(player_primary, dict) or player_primary.get("onehand") != prefix[0]:
        raise ValueError("Player onehand primary action must be the combo prefix head")
    mob_rows = [actor for actor in actors if actor.get("id") == MOB_ACTOR_ID]
    if len(mob_rows) != 1:
        raise ValueError("Trusted definitions require exactly one fixed mob actor")
    if not _strict_json_equal(
        mob_rows[0].get("defending_sphere"),
        {
            "local_center_x_m": 0.0,
            "local_center_y_m": 0.8,
            "local_center_z_m": 0.1,
            "radius_m": 0.9,
        },
    ):
        raise ValueError("Wild Dog defending sphere changed")
    if not _strict_json_equal(
        mob_rows[0].get("great_hit_reactions"),
        [
            {"id": MOB_REACTION_IDS[action], "duration_us": MOB_REACTION_DURATIONS_US[action]}
            for action in ("front_knockdown", "front_standup", "back_knockdown")
        ],
    ):
        raise ValueError("Wild Dog GREAT hit reaction definitions changed")
    for actor in payload["actors"]:
        primary_actions = actor.get("primary_actions", {})
        if not isinstance(primary_actions, dict):
            raise ValueError("Actor primary_actions must be an object")
        primary = list(primary_actions.values())
        if "primary_action_id" in actor:
            primary.append(actor["primary_action_id"])
        if any(type(action_id) is not str or action_id not in action_ids for action_id in primary):
            raise ValueError("Primary action refers to a missing action")
    for action in actions:
        duration_us = action.get("duration_us")
        cooldown_us = action.get("cooldown_us")
        if type(duration_us) is not int or not 0 < duration_us <= MAX_COMBO_TIME_US:
            raise ValueError("Action duration must be integer microseconds in 1..=60000000")
        if type(cooldown_us) is not int or not 0 < cooldown_us <= MAX_COMBO_TIME_US:
            raise ValueError("Action cooldown must be integer microseconds in 1..=60000000")
        hit_windows = action.get("hit_windows")
        is_terminal = action.get("id") == PLAYER_COMBO_ACTION_IDS[3]
        if (
            action.get("ordinary_hit_invulnerability_us")
            != ORDINARY_HIT_INVULNERABILITY_US[action["id"]]
        ):
            raise ValueError("Trusted ordinary hit invulnerability changed")
        if not isinstance(hit_windows, list) or len(hit_windows) != (0 if is_terminal else 1):
            raise ValueError("Trusted action has an unexpected ordinary hit-window count")
        for window in hit_windows:
            if not isinstance(window, dict):
                raise ValueError("Trusted hit window must be an object")
            if (
                type(window.get("start_us")) is not int
                or type(window.get("end_us")) is not int
                or not 0 <= window["start_us"] < window["end_us"] <= duration_us
            ):
                raise ValueError("Trusted hit window exceeds action duration")
            if (
                type(window.get("range_m")) not in {int, float}
                or not math.isfinite(window["range_m"])
                or window["range_m"] <= 0
            ):
                raise ValueError("Trusted hit window has invalid range")
            if window.get("shape") != "melee_reach":
                raise ValueError("Trusted hit window has unsupported shape")
        expected_actor = MOB_ACTOR_ID if action["id"] == MOB_ACTION_ID else PLAYER_ACTOR_ID
        expected_mode = "onehand" if action["id"] in PLAYER_COMBO_ACTION_IDS else "general"
        expected_name = (
            f"combo_{PLAYER_COMBO_ACTION_IDS.index(action['id']) + 1}"
            if action["id"] in PLAYER_COMBO_ACTION_IDS
            else "normal_attack"
        )
        expected_items = [10] if action["id"] in PLAYER_COMBO_ACTION_IDS else []
        expected_range = 1.9 if action["id"] == MOB_ACTION_ID else 2.7
        if (
            action.get("actor_id") != expected_actor
            or action.get("mode") != expected_mode
            or action.get("action") != expected_name
            or action.get("required_item_vnums") != expected_items
            or (not is_terminal and hit_windows[0]["range_m"] != expected_range)
        ):
            raise ValueError("Trusted action does not match the fixed fixture")
        if action["id"] in PLAYER_COMBO_ACTION_IDS:
            root_motion = _checked_root_motion(action.get("root_motion"), duration_us, action["id"])
            source = root_sources[PLAYER_COMBO_ACTION_IDS.index(action["id"])]
            _checked_root_motion_source(source, action["id"], root_motion, duration_us)
            if is_terminal:
                if "combo_input" in action:
                    raise ValueError("Terminal combo_4 must omit combo_input")
                if not _strict_json_equal(
                    action.get("special_area"),
                    {
                        "authored_start_us": 659_316,
                        "legacy_dispatch_frame": 39,
                        "activation_offset_us": 666_667,
                        "duration_us": 200_000,
                        "local_center_x_m": 0.0,
                        "local_center_z_m": -1.2,
                        "radius_m": 1.0,
                        "max_targets": 16,
                        "hit_once_per_life": True,
                        "hit_type": 1,
                        "invulnerability_us": 300_000,
                        "knockback": {
                            "source_external_force": 17.0,
                            "unobstructed_distance_m": 4.732,
                            "duration_us": 1_000_000,
                        },
                    },
                ):
                    raise ValueError("Terminal combo_4 special area changed")
                if not _strict_json_equal(
                    action.get("screen_wave"),
                    {
                        "authored_start_us": 630_086,
                        "legacy_dispatch_frame": 37,
                        "activation_offset_us": 633_334,
                        "duration_us": 200_000,
                        "viewer_range_m": 2.0,
                        "source_power": 300,
                        "source_component_step_m": 0.001,
                        "source_component_exclusive_max_m": 0.3,
                    },
                ):
                    raise ValueError("Terminal combo_4 screen wave changed")
            else:
                _checked_combo_input(action.get("combo_input"), duration_us, action["id"])
                if "special_area" in action or "screen_wave" in action:
                    raise ValueError("Only terminal combo_4 may define special events")
        elif "combo_input" in action:
            raise ValueError("Non-prefix actions must omit combo_input")
        elif "root_motion" in action:
            raise ValueError("Non-prefix actions must omit root_motion")
    progression = payload.get("progression")
    if not isinstance(progression, dict):
        raise ValueError("Trusted definitions require progression data")
    if progression.get("schema") != "mt2spacetime.progression-definitions":
        raise ValueError("Trusted progression schema mismatch")
    if progression.get("schema_version") != 1:
        raise ValueError("Trusted progression schema version mismatch")
    if progression.get("compiled_max_level") != 120:
        raise ValueError("Trusted progression compiled maximum mismatch")
    if progression.get("default_level_cap") != 99:
        raise ValueError("Trusted progression level cap mismatch")
    experience = progression.get("experience_to_next_level_by_current_level", [])
    if (
        len(experience) != 121
        or any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in experience)
        or experience[0] != 0
        or any(value == 0 for value in experience[1:])
    ):
        raise ValueError("Trusted progression EXP table must contain levels 0..120")
    level_delta = progression.get("normal_level_delta_percent", [])
    if len(level_delta) != 31 or any(
        type(value) is not int or not 0 <= value <= 1000 for value in level_delta
    ):
        raise ValueError("Trusted progression level-delta table must contain 31 values")
    quarters = progression.get("quarter_thresholds_by_current_level", [])
    if len(quarters) != 121:
        raise ValueError("Trusted progression quarter table must contain levels 0..120")
    for level, row in enumerate(quarters):
        expected = list(quarter_thresholds(experience[level]))
        if row != {
            "level": level,
            "next_experience": experience[level],
            "thresholds": expected,
        }:
            raise ValueError("Trusted progression quarter table violates float32 thresholds")


def _client_motion(motion: dict, trusted_action: dict | None) -> dict:
    result = {
        key: motion[key]
        for key in (
            "action_id",
            "action",
            "variant",
            "weight",
            "godot_name",
            "duration_us",
            "loop",
            "accumulation_m",
            "events",
            "combo",
            "fallback_mode",
        )
    }
    if trusted_action is not None and "screen_wave" in trusted_action:
        wave = trusted_action["screen_wave"]
        result["screen_wave"] = {
            key: wave[key] for key in ("activation_offset_us", "duration_us", "viewer_range_m")
        }
    return result


def make_client_payload(normalized: dict, server: dict, blender_report: dict) -> dict:
    if blender_report.get("status") != "converted":
        raise ValueError("Blender conversion did not complete")
    report_artifacts = {entry["id"]: entry for entry in blender_report["artifacts"]}
    expected_ids = {entry["id"] for entry in [*normalized["actors"], *normalized["items"]]}
    if set(report_artifacts) != expected_ids:
        raise ValueError("Blender report does not contain the exact profile artifacts")
    profile_id = normalized["profile_id"]
    trusted_actions = {action["id"]: action for action in server["actions"]}
    artifacts = []
    for _content_id, source in sorted(report_artifacts.items()):
        entry = {
            key: source[key]
            for key in (
                "id",
                "type",
                "sha256",
                "bytes",
                "mesh_count",
                "textured_mesh_count",
                "vertices",
                "triangles",
                "bounds_m",
            )
        }
        entry["path"] = f"res://assets/imported/content/{profile_id}/{source['relative_path']}"
        if source["type"] == "actor":
            entry.update(
                {
                    "bones": source["bones"],
                    "skeleton_signature": source["skeleton_signature"],
                }
            )
        artifacts.append(entry)
    actors = []
    for actor in normalized["actors"]:
        artifact = report_artifacts[actor["id"]]
        if set(artifact["attachment_bones"]) != set(actor["attachment_bones"]):
            raise ValueError(f"Attachment report mismatch for {actor['id']}")
        entry = {
            "id": actor["id"],
            "kind": actor["kind"],
            **({"race_id": actor["race_id"]} if "race_id" in actor else {"vnum": actor["vnum"]}),
            "name": actor["name"],
            "model_key": actor["model_key"],
            "model": {
                "artifact_id": actor["id"],
                "path": next(item["path"] for item in artifacts if item["id"] == actor["id"]),
            },
            "skeleton_signature": artifact["skeleton_signature"],
            "attachment_bones": actor["attachment_bones"],
            **(
                {"default_hair_index": actor["default_hair"]["hair_index"]}
                if "default_hair" in actor
                else {}
            ),
            "forward": actor["orientation"]["output_forward"],
            "motion_vector_space": actor["motion_vector_space"],
            "modes": [
                {
                    "id": mode["id"],
                    "required_item_vnums": mode["required_item_vnums"],
                    "combo_chains": mode["combo_chains"],
                    "motions": [
                        _client_motion(motion, trusted_actions.get(motion["action_id"]))
                        for motion in mode["motions"]
                    ],
                }
                for mode in actor["modes"]
            ],
        }
        actors.append(entry)
    items = []
    for item in normalized["items"]:
        items.append(
            {
                key: item[key]
                for key in (
                    "id",
                    "vnum",
                    "name",
                    "kind",
                    "equipment_mode",
                    "actor_attachment",
                    "attachment_transform",
                )
            }
            | {
                "model": {
                    "artifact_id": item["id"],
                    "path": next(
                        artifact["path"] for artifact in artifacts if artifact["id"] == item["id"]
                    ),
                }
            }
        )
    payload = {
        "schema": CLIENT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "content_hash": normalized["content_hash"],
        "gameplay_definition_hash": server["gameplay_definition_hash"],
        "coordinates": normalized["coordinates"],
        "converter": {
            "content_compiler": normalized["compiler_version"],
            "blender_import": blender_report["converter_version"],
            "blender": blender_report["blender_version"],
            "gr2_importer_commit": blender_report["importer_commit"],
        },
        "artifacts": artifacts,
        "actors": actors,
        "items": items,
        "unsupported": [
            {
                key: entry[key]
                for key in ("action_id", "kind", "event_type", "reason")
                if key in entry
            }
            for entry in normalized["unsupported"]
        ],
        "adapted_motion_events": [
            {
                key: entry[key]
                for key in ("action_id", "kind", "event_type", "adapter")
                if key in entry
            }
            for entry in normalized["adapted_motion_events"]
        ],
    }
    payload["presentation_output_hash"] = digest(artifacts)
    return payload


def compile_command(args: argparse.Namespace) -> None:
    profile_path = Path(args.profile).resolve()
    profile = load_profile(profile_path)
    normalized = compile_normalized(profile_path, offline=args.offline)
    server = make_server_payload(profile, normalized)
    validate_server_payload(server, profile["profile_id"])
    write_compile_outputs(profile_path, normalized, server)
    print(
        json.dumps(
            {
                "profile_id": profile["profile_id"],
                "content_hash": normalized["content_hash"],
                "gameplay_definition_hash": server["gameplay_definition_hash"],
                "unsupported": len(normalized["unsupported"]),
            },
            sort_keys=True,
        )
    )


def build_command(args: argparse.Namespace) -> None:
    profile_path = Path(args.profile).resolve()
    profile = load_profile(profile_path)
    normalized = compile_normalized(profile_path, offline=args.offline)
    server = make_server_payload(profile, normalized)
    validate_server_payload(server, profile["profile_id"])
    write_compile_outputs(profile_path, normalized, server)
    paths = output_paths(profile["profile_id"])
    staging_parent = ROOT / ".local/content" / profile["profile_id"]
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=staging_parent) as temporary:
        staging = Path(temporary)
        staging_output = staging / "output"
        staging_report = staging / "blender-report.v1.json"
        command = [
            str(Path(args.blender).resolve()),
            "--background",
            "--factory-startup",
            "-noaudio",
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "tools/import_actor_content.py"),
            "--",
            "--manifest",
            str(paths["normalized"]),
            "--source-root",
            str(ROOT / "assets/source/content" / METIN_COMMIT),
            "--output",
            str(staging_output),
            "--report",
            str(staging_report),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        blender_report = json.loads(staging_report.read_text())
        if blender_report.get("status") != "converted":
            raise ValueError("Background Blender conversion failed")
        for artifact in blender_report["artifacts"]:
            source = staging_output / safe_path(artifact["relative_path"])
            if (
                not source.is_file()
                or hashlib.sha256(source.read_bytes()).hexdigest() != artifact["sha256"]
            ):
                raise ValueError(f"Staged artifact is missing or changed: {source}")
        final_output = paths["client"].parent
        for artifact in blender_report["artifacts"]:
            source = staging_output / artifact["relative_path"]
            target = final_output / artifact["relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary_target = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(source, temporary_target)
            temporary_target.replace(target)
        extract_actor_texture_pngs(final_output, blender_report)
        write_json(paths["blender_report"], blender_report)
    client = make_client_payload(normalized, server, blender_report)
    write_json(paths["client"], client)
    report = json.loads(paths["report"].read_text())
    report.update(
        {
            "status": "built",
            "presentation_output_hash": client["presentation_output_hash"],
            "blender_version": blender_report["blender_version"],
            "artifacts": client["artifacts"],
        }
    )
    write_json(paths["report"], report)
    validate_command(argparse.Namespace(profile=str(profile_path)))


def validate_command(args: argparse.Namespace) -> None:
    profile = load_profile(Path(args.profile).resolve())
    paths = output_paths(profile["profile_id"])
    runtime = json.loads(paths["runtime_server"].read_text())
    validate_server_payload(runtime, profile["profile_id"])
    if paths["client"].exists():
        client = json.loads(paths["client"].read_text())
        if client.get("schema") != CLIENT_SCHEMA or client.get("schema_version") != 1:
            raise ValueError("Invalid presentation manifest schema")
        if client.get("gameplay_definition_hash") != runtime["gameplay_definition_hash"]:
            raise ValueError("Client/server gameplay definition hashes differ")
    print(f"Validated {profile['profile_id']} ({runtime['gameplay_definition_hash']})")


def probe_command(args: argparse.Namespace) -> None:
    profile = load_profile(Path(args.profile).resolve())
    paths = output_paths(profile["profile_id"])
    manifest = json.loads(paths["client"].read_text())
    with tempfile.TemporaryDirectory(prefix="mt2-content-godot-") as temporary:
        project = Path(temporary)
        (project / "project.godot").write_text(
            '[application]\nconfig/name="MT2 content import probe"\n[rendering]\n'
            'renderer/rendering_method="gl_compatibility"\n'
        )
        manifest_relative = paths["client"].relative_to(ROOT / "client")
        staged_manifest = project / manifest_relative
        staged_manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths["client"], staged_manifest)
        for artifact in manifest["artifacts"]:
            relative = safe_path(artifact["path"].removeprefix("res://"))
            source = ROOT / "client" / relative
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        environment = dict(os.environ)
        environment.update(
            {
                "XDG_CACHE_HOME": str(project / ".xdg/cache"),
                "XDG_CONFIG_HOME": str(project / ".xdg/config"),
                "XDG_DATA_HOME": str(project / ".xdg/data"),
            }
        )
        executable = str(Path(args.godot).resolve())
        subprocess.run(
            [executable, "--headless", "--editor", "--path", str(project), "--quit"],
            check=True,
            env=environment,
        )
        temporary_report = project / "godot-report.v1.json"
        subprocess.run(
            [
                executable,
                "--headless",
                "--path",
                str(project),
                "--script",
                str(ROOT / "tools/content_import_probe.gd"),
                "--",
                f"res://{manifest_relative.as_posix()}",
                str(temporary_report),
            ],
            check=True,
            env=environment,
        )
        report = json.loads(temporary_report.read_text())
        if report.get("status") != "imported" or report.get("profile_id") != profile["profile_id"]:
            raise ValueError("Godot content import probe did not complete")
        write_json(paths["godot_report"], report)
    print(f"Godot imported {profile['profile_id']} with {len(report['actors'])} actors")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile", help="fetch/read and normalize the profile")
    compile_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    compile_parser.add_argument("--offline", action="store_true")
    compile_parser.set_defaults(function=compile_command)
    build_parser = subparsers.add_parser("build", help="normalize and convert all profile GLBs")
    build_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    build_parser.add_argument("--offline", action="store_true")
    build_parser.add_argument("--blender", required=True)
    build_parser.set_defaults(function=build_command)
    validate_parser = subparsers.add_parser("validate", help="validate generated profile artifacts")
    validate_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    validate_parser.set_defaults(function=validate_command)
    probe_parser = subparsers.add_parser(
        "probe-godot", help="import built GLBs in an isolated temporary Godot project"
    )
    probe_parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    probe_parser.add_argument("--godot", required=True)
    probe_parser.set_defaults(function=probe_command)
    args = parser.parse_args()
    try:
        args.function(args)
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"content compiler: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
