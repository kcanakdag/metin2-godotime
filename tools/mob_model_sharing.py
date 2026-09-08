"""Share only identical normalized mob render inputs; keep every gameplay identity."""

import copy
import hashlib

from content_compile import canonical_bytes

IDENTITY_FIELDS = {"id", "vnum", "name", "model_key", "output", "shared_model_actor_id"}


def render_fingerprint(actor):
    data = copy.deepcopy({k: v for k, v in actor.items() if k not in IDENTITY_FIELDS})
    for mode in data["modes"]:
        for motion in mode["motions"]:
            motion.pop("action_id")
            motion.pop("godot_name")
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def motions(actor):
    return [motion for mode in actor["modes"] for motion in mode["motions"]]


def share_models(actors):
    if len({a["id"] for a in actors}) != len(actors):
        raise ValueError("Duplicate actor identity before model sharing")
    owners, result = {}, []
    for source in sorted(actors, key=lambda a: (a["vnum"], a["id"])):
        actor = copy.deepcopy(source)
        if actor["kind"] != "mob":
            raise ValueError("Mob model sharing cannot rewrite other actor types")
        key = render_fingerprint(actor)
        owner = owners.setdefault(key, actor)
        actor["shared_model_actor_id"] = owner["id"]
        actor["output"] = owner["output"]
        for motion, original in zip(motions(actor), motions(owner), strict=True):
            motion["godot_name"] = original["godot_name"]
        result.append(actor)
    # Preserve caller's definition ordering; owner choice is independent of it.
    indexed = {a["id"]: a for a in result}
    return [indexed[a["id"]] for a in actors]


def unique_actors(actors):
    indexed = {a["id"]: a for a in actors}
    if len(indexed) != len(actors):
        raise ValueError("Duplicate shared actor identity")
    result = []
    for actor in actors:
        owner = indexed.get(actor["shared_model_actor_id"])
        if owner is None or owner["shared_model_actor_id"] != owner["id"]:
            raise ValueError("Missing or chained shared model owner")
        if actor["output"] != owner["output"] or render_fingerprint(actor) != render_fingerprint(
            owner
        ):
            raise ValueError("Shared model does not have identical render inputs")
        if any(
            m["godot_name"] != original["godot_name"]
            for m, original in zip(motions(actor), motions(owner), strict=True)
        ):
            raise ValueError("Shared actor clip mapping differs from model owner")
        if actor["id"] == owner["id"]:
            result.append(actor)
    if len({a["output"] for a in result}) != len(result):
        raise ValueError("Different model owners have conflicting output paths")
    return result


def expand_report(actors, report):
    owners = unique_actors(actors)
    artifacts = report["artifacts"]
    indexed = {a["id"]: a for a in artifacts}
    if (
        report.get("status") != "converted"
        or len(indexed) != len(artifacts)
        or set(indexed) != {a["id"] for a in owners}
    ):
        raise ValueError("Blender report does not cover exactly the unique models")
    expanded = []
    for actor in actors:
        owner_id = actor["shared_model_actor_id"]
        artifact = copy.deepcopy(indexed[owner_id])
        reported = {m["godot_name"]: m for m in artifact["motions"]}
        required = motions(actor)
        if (
            artifact["relative_path"] != actor["output"]
            or len(reported) != len(artifact["motions"])
            or set(reported) != {m["godot_name"] for m in required}
        ):
            raise ValueError("Shared GLB clip set or model path differs from actor")
        expanded_motions = []
        for motion in required:
            evidence = reported[motion["godot_name"]]
            if evidence["duration_us"] != motion["duration_us"]:
                raise ValueError("Shared clip duration differs from Blender evidence")
            expanded_motions.append({**evidence, "action_id": motion["action_id"]})
        artifact.update(id=actor["id"], shared_model_actor_id=owner_id, motions=expanded_motions)
        expanded.append(artifact)
    return {
        **report,
        "artifacts": expanded,
        "alias_expander_version": "mob-model-sharing-v1",
        "unique_model_count": len(owners),
    }
