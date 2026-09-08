#!/usr/bin/env python3
"""Inventory selected class-skill motion effects without installing or enabling skills."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import canonical_bytes, source_archive
from content_formats import parse_msa, parse_race_script
from fetch_test_assets import METIN_COMMIT
from motion_effects import motion_effect


def extract(raw: bytes) -> dict:
    parsed = parse_msa(raw.decode(), ignore_legacy_link_time=True, allow_post_clip_area=True)
    effects, rejected, remaining = [], [], []
    for event in parsed["unsupported"]:
        if event.get("event_type") != 1:
            remaining.append(event)
            continue
        try:
            effects.append(motion_effect(event, parsed["duration_us"]))
        except ValueError as error:
            rejected.append({"event": event, "reason": str(error)})
    return {
        "duration_us": parsed["duration_us"],
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "effects": effects,
        "rejected_effects": rejected,
        "remaining_unsupported": remaining,
    }


def discover(inventory: dict, profile: dict, archive) -> dict:
    if (
        inventory.get("schema") != "mt2spacetime.skill-source-inventory"
        or inventory.get("version") != 1
        or inventory.get("source_revision") != METIN_COMMIT
        or profile.get("source", {}).get("client_revision") != METIN_COMMIT
    ):
        raise ValueError("Expected pinned skill inventory and character profile")
    rows, references, identities = [], {}, set()
    for skill in inventory["skills"]:
        cls = next(c for c in profile["classes"] if c["class_id"] == skill["class_id"])
        for variant in cls["variants"]:
            actor = f"actor.player.{cls['id']}-{'male' if variant['sex'] == 0 else 'female'}"
            action = actor + ".general." + skill["motion"]
            if action in identities:
                raise ValueError("Duplicate selected skill appearance")
            identities.add(action)
            race_path = "bin/pack/root/" + variant["model_key"] + ".msm"
            race_bytes = archive.get(race_path).read_bytes()
            race = parse_race_script(race_bytes.decode())
            root = race["base_model"].rsplit("/", 1)[0]
            source = archive.resolve(root + "/" + skill["motion_file"])
            row = {
                "actor_id": actor,
                "skill_vnum": skill["vnum"],
                "action_id": action,
                "source_msa": source,
                "race_script": race_path,
                "race_sha256": hashlib.sha256(race_bytes).hexdigest(),
                **extract(archive.get(source).read_bytes()),
            }
            rows.append(row)
            for effect in row["effects"]:
                references.setdefault(effect["effect_path"], []).append(
                    {"action_id": action, "source_event": effect["source_event"]}
                )
    return {
        "schema": "mt2spacetime.skill-motion-effect-inventory",
        "version": 1,
        "source_revision": METIN_COMMIT,
        "runtime_status": "unresolved-candidate-not-installed",
        "motions": rows,
        "effect_references": references,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", type=Path, required=True)
    parser.add_argument("--characters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists")
    inputs = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.skills, args.characters]
    }
    result = discover(
        json.loads(args.skills.read_text()),
        json.loads(args.characters.read_text()),
        source_archive(args.offline),
    )
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in inputs.items()):
        raise ValueError("Selected inputs changed during discovery")
    result["inputs"] = inputs
    with args.output.open("xb") as output:
        output.write(canonical_bytes(result) + b"\n")
    print(
        json.dumps(
            {
                "motions": len(result["motions"]),
                "unique_effects": len(result["effect_references"]),
                "events": sum(len(m["effects"]) for m in result["motions"]),
                "rejected": sum(len(m["rejected_effects"]) for m in result["motions"]),
                "remaining": sum(len(m["remaining_unsupported"]) for m in result["motions"]),
            }
        )
    )


if __name__ == "__main__":
    main()
