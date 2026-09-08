"""Compile source-linked wildlife motion mechanics without species-specific defaults."""

import copy
import hashlib
import math

from content_compile import canonical_bytes

SERVER_REVISION = "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318"


def validate_actor_reports(actors, artifacts):
    expected = {actor["id"]: actor for actor in actors}
    if len(artifacts) != len(expected) or {a["id"] for a in artifacts} != set(expected):
        raise ValueError("Blender report does not cover exact actor identities")
    for artifact in artifacts:
        actor = expected[artifact["id"]]
        if artifact["relative_path"] != actor["output"]:
            raise ValueError("Blender actor model path differs from normalized content")
        source = {
            (m["action_id"], m["godot_name"], m["duration_us"])
            for mode in actor["modes"]
            for m in mode["motions"]
        }
        reported = artifact["motions"]
        actual = {(m["action_id"], m["godot_name"], m["duration_us"]) for m in reported}
        if source != actual or len(actual) != len(reported):
            raise ValueError("Blender report motions differ from gameplay source timings")


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Invalid {label}: expected integer {low}..{high}")
    return value


def number(value, low, high, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Invalid finite {label}")
    return value


def legacy_duration(speed, duration):
    """Pinned server CalculateDuration; its slow branch is not 100/speed."""
    integer(speed, 1, 200, "mob speed")
    integer(duration, 1, 60_000_000, "source duration")
    factor = 200 - speed if speed < 100 else 10000 // speed
    return duration * factor // 100


def playback_duration(speed, duration):
    integer(speed, 1, 200, "playback speed")
    integer(duration, 0, 60_000_000, "motion timestamp")
    return (duration * 100 + speed - 1) // speed


def motion_record(motion, actor_id):
    action_id = motion.get("action_id")
    if not isinstance(action_id, str) or not action_id.startswith(actor_id + ".general."):
        raise ValueError("Motion does not belong to its actor/general mode")
    duration = integer(motion.get("duration_us"), 1, 60_000_000, "motion duration")
    weight = integer(motion.get("weight"), 1, 100, "motion weight")
    if not isinstance(motion.get("godot_name"), str) or not motion["godot_name"]:
        raise ValueError("Missing converted animation name")
    return {
        "id": action_id,
        "godot_name": motion["godot_name"],
        "duration_us": duration,
        "weight": weight,
        "source_msa": motion["source_msa"],
        "source_gr2": motion["source_gr2"],
    }


def compile_mob(source, actor):
    actor_id = source["id"]
    if (actor["id"], actor["vnum"], actor["kind"], actor["model_key"]) != (
        actor_id,
        source["vnum"],
        "mob",
        source["model_key"],
    ):
        raise ValueError("Mob and converted actor identities differ")
    if actor["orientation"] != {"output_forward": "-Z", "yaw_correction_degrees": 180.0}:
        raise ValueError("Unsupported wildlife motion orientation")
    modes = actor["modes"]
    if len(modes) != 1 or modes[0]["id"] != "general":
        raise ValueError("Wildlife requires one general motion mode")
    motions = modes[0]["motions"]
    ids = [m["action_id"] for m in motions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate converted motion identity")

    def group(action):
        rows = [m for m in motions if m["action"] == action]
        if not rows or sum(integer(m["weight"], 1, 100, "weight") for m in rows) != 100:
            raise ValueError(f"Missing or invalid weighted {action} group for {actor_id}")
        return rows

    stats = source["stats"]
    speed = integer(stats["attack_speed"], 1, 200, "attack speed")
    move_speed = integer(stats["move_speed"], 1, 200, "move speed")
    attacks = []
    for motion in group("normal_attack"):
        record = motion_record(motion, actor_id)
        if motion["loop"] or motion["combo"] is not None:
            raise ValueError("Ordinary mob attack must be a nonlooping independent motion")
        events = motion["events"]
        if not events or any(e["kind"] != "attack_window" for e in events):
            raise ValueError("Mob attack requires supported explicit hit windows")
        windows = []
        for event in events:
            start = integer(event["start_us"], 0, record["duration_us"], "hit start")
            end = integer(event["end_us"], start, record["duration_us"], "hit end")
            if end == start or event["coordinate_space"] != "output_actor_local_godot":
                raise ValueError("Invalid hit window interval or coordinate space")
            samples = event["samples"]
            if not samples or len(samples) != event["sample_count"]:
                raise ValueError("Missing or inconsistent hit samples")
            previous = -1
            for sample in samples:
                timestamp = integer(sample["time_us"], start, end, "hit sample timestamp")
                if timestamp <= previous:
                    raise ValueError("Hit sample times must increase")
                previous = timestamp
                for key in ("start_m", "end_m"):
                    if len(sample[key]) != 3:
                        raise ValueError("Hit sample must have three coordinates")
                    for value in sample[key]:
                        number(value, -50, 50, "hit coordinate")
            windows.append(
                {
                    **copy.deepcopy(event),
                    "playback_start_us": playback_duration(speed, start),
                    "playback_end_us": playback_duration(speed, end),
                }
            )
        attacks.append(
            {
                **record,
                "attack_speed_percent": speed,
                "playback_duration_us": playback_duration(speed, record["duration_us"]),
                "server_cooldown_us": legacy_duration(speed, 2_000_000),
                "windows": windows,
            }
        )
    runs = group("run")
    if len(runs) != 1:
        raise ValueError("Multiple run motions need explicit movement policy")
    run = runs[0]
    run_record = motion_record(run, actor_id)
    vector = run["accumulation_m"]
    if len(vector) != 3:
        raise ValueError("Invalid run accumulation")
    for value in vector:
        number(value, -50, 50, "run accumulation")
    if abs(vector[0]) > 1e-5 or abs(vector[1]) > 1e-5 or vector[2] >= 0:
        raise ValueError("Run motion must advance along converted -Z")
    base_speed = -vector[2] * 1_000_000 / run_record["duration_us"]
    movement = {
        **run_record,
        "source_accumulation_m": list(vector),
        "base_speed_mps": base_speed,
        "move_speed_percent": move_speed,
        "server_speed_mps": base_speed * 10000 / legacy_duration(move_speed, 10000),
    }
    reactions = {}
    for action in ("front_knockdown", "front_standup", "back_knockdown"):
        rows = group(action)
        if len(rows) != 1 or rows[0]["loop"] or rows[0]["events"]:
            raise ValueError("Reaction needs one nonlooping motion without deferred events")
        reactions[action] = motion_record(rows[0], actor_id)
    collisions = [r for r in source["assets"]["source_collision"] if r["collision_type"] == 3]
    if len(collisions) != 1 or collisions[0]["bone"] != "Bip01":
        raise ValueError("Unsupported defending collision attachment")
    spheres = collisions[0]["spheres"]
    if len(spheres) != 1:
        raise ValueError("Multiple defending spheres need runtime support")
    sphere = spheres[0]
    number(sphere["radius_m"], 0.01, 10, "defending radius")
    if len(sphere["position_m"]) != 3:
        raise ValueError("Invalid defending sphere center")
    for value in sphere["position_m"]:
        number(value, -10, 10, "defending center")
    return {
        "id": actor_id,
        "vnum": integer(source["vnum"], 1, 2**32 - 1, "mob vnum"),
        "model_key": source["model_key"],
        "name": source["name"],
        "health": integer(stats["max_hp"], 1, 65535, "runtime health"),
        "level": integer(stats["level"], 1, 99, "runtime level"),
        "attack_range_m": integer(stats["attack_range"], 1, 10000, "attack range") / 100,
        "attacks": attacks,
        "movement": movement,
        "reactions": reactions,
        "defending_sphere": copy.deepcopy(sphere),
        "source_definition": copy.deepcopy(source),
    }


def compile_catalog(normalized):
    if (
        normalized.get("schema_version") != 1
        or normalized.get("compiler_version") != "mob-content-v1"
    ):
        raise ValueError("Expected normalized mob content")
    if normalized.get("inventory", {}).get("server_revision") != SERVER_REVISION:
        raise ValueError("Gameplay timing requires the reviewed server revision")
    payload = {k: v for k, v in normalized.items() if k != "content_hash"}
    if hashlib.sha256(canonical_bytes(payload)).hexdigest() != normalized.get("content_hash"):
        raise ValueError("Normalized content hash does not match payload")
    if normalized["deferred_motion_events"]:
        raise ValueError("Resolve deferred motion events before compiling gameplay")
    actors = normalized["actors"]
    sources = normalized["mob_catalog"]
    if not 1 <= len(sources) <= 128 or len(sources) != len(actors):
        raise ValueError("Expected matching bounded mob and actor catalogs")
    for key in ("id", "vnum"):
        if len({r[key] for r in sources}) != len(sources):
            raise ValueError("Duplicate mob identity")
        if len({a[key] for a in actors}) != len(actors):
            raise ValueError("Duplicate converted actor identity")
    indexed = {a["id"]: a for a in actors}
    if set(indexed) != {r["id"] for r in sources}:
        raise ValueError("Converted actor catalog differs from mob catalog")
    rows = [compile_mob(source, indexed[source["id"]]) for source in sources]
    result = {
        "schema": "mt2spacetime.mob-gameplay-candidate",
        "version": 1,
        "source_content_hash": normalized["content_hash"],
        "runtime_status": "candidate-not-installed",
        "timing_policy": "original-server-cadence-and-precise-client-playback-v1",
        "server_rules": {
            "revision": SERVER_REVISION,
            "references": [
                "src/game/src/utils.cpp:CalculateDuration",
                "src/game/src/char.cpp:CHARACTER::GetMoveMotionSpeed",
                "src/game/src/char.cpp:CHARACTER::GetMoveSpeed",
                "src/game/src/char_state.cpp:CHARACTER::StateBattle",
            ],
        },
        "mobs": rows,
    }
    result["content_hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    return result
