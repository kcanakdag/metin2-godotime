#!/usr/bin/env python3
"""Link discovered class skills to converted motion metadata and shared runtime mechanics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from content_compile import canonical_bytes
from fetch_test_assets import METIN_COMMIT
from skill_formulas import rank_value
from skill_tuning import apply_tuning

RANK_POWERS = [0, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 50]


def skill_handler(source: dict) -> str:
    flags = set(source["flags"])
    if source["vnum"] == 5:
        # Pinned skill.h::IsChargeSkill / char_skill.cpp::UseSkill.
        if "ATTACK" not in flags or source["secondary_point"] != "MOV_SPEED":
            raise ValueError("Dash charge metadata differs from the supported source contract")
        return "charge"
    if "TOGGLE" in flags and "ATTACK" in flags:
        return "periodic_damage"
    if "ATTACK" not in flags:
        return "healing" if source["point"] == "HP" else "buff"
    return "damage"


def compile_catalog(inventory: dict, characters: dict) -> dict:
    if (
        inventory.get("schema") != "mt2spacetime.skill-source-inventory"
        or inventory.get("version") != 1
        or inventory.get("source_revision") != METIN_COMMIT
    ):
        raise ValueError("Expected the pinned classic skill inventory")
    skills = []
    for source in inventory["skills"]:
        client_flags = set(source["client_flags"])
        vnum = source["vnum"]
        variants = []
        cls = next(c for c in characters["classes"] if c["class_id"] == source["class_id"])
        for variant in cls["variants"]:
            actor = next(a for a in characters["actors"] if a["id"] == variant["actor_id"])
            motions = [
                m
                for mode in actor["modes"]
                for m in mode["motions"]
                if m["action"] == source["motion"]
            ]
            if len(motions) != 1:
                raise ValueError("Skill must link exactly one converted motion per appearance")
            motion = motions[0]
            duration = motion["duration_us"]
            root = motion["accumulation_m"]
            if not 0 < duration <= 3_200_000 or any(
                not math.isfinite(x) or abs(x) > 8 for x in root
            ):
                raise ValueError("Skill motion exceeds bounded runtime duration/root")
            hits = [e for e in motion["events"] if e["kind"] in ("attack_area", "attack_window")]
            fly = [
                e
                for e in characters["unsupported_motion_metadata"]
                if e.get("action_id") == motion["action_id"] and e.get("event_type") == 6
            ]
            activations = sorted({e["start_us"] for e in hits + fly})
            if vnum == 107:
                # Pinned server char_skill.cpp::UseSkill computes BYEURAK immediately.
                # Its event 10 is a target visual effect, not a client damage window.
                activations = [0]
            variants.append(
                {
                    "actor_id": actor["id"],
                    "action_id": motion["action_id"],
                    "duration_us": duration,
                    "root_m": root,
                    "activation_us": activations,
                    "hits": [
                        {k: v for k, v in hit.items() if k not in ("samples", "sample_count")}
                        for hit in hits
                    ],
                }
            )
        handler = skill_handler(source)
        if handler == "damage" and any(not v["activation_us"] for v in variants):
            raise ValueError(f"Skill {vnum} has no original damage activation metadata")
        costs = [int(rank_value(source["sp_cost"], power)) for power in RANK_POWERS]
        cooldowns = [
            int(rank_value(source["cooldown"], power) * 1_000_000) for power in RANK_POWERS
        ]
        if any(not 0 <= v <= 10_000 for v in costs) or any(
            not 0 <= v <= 600_000_000 for v in cooldowns
        ):
            raise ValueError("Skill cost/cooldown exceeds runtime bounds")
        skills.append(
            {
                **source,
                "handler": handler,
                "minimum_level": 5,
                "maximum_rank": 20,
                "rank_costs": costs,
                "rank_cooldowns_us": cooldowns,
                "target": "friendly"
                if "ONLY_FOR_ALLIANCE" in client_flags
                else ("monster" if "NEED_TARGET" in client_flags else "self"),
                "variants": variants,
            }
        )
    if len(skills) != 44 or len({s["vnum"] for s in skills}) != 44:
        raise ValueError("Full classic coverage requires 44 distinct class skills")
    return {
        "schema": "mt2spacetime.skills",
        "version": 2,
        "rank_power_percent": RANK_POWERS,
        "skills": skills,
        "tuning": inventory.get("tuning", {"schema_version": 1, "overrides": []}),
        "source_revision": METIN_COMMIT,
        "source_sha256": inventory["source_sha256"],
        "motion_content_hash": characters["content_hash"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--characters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--tuning",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "content/profiles/classic-skill-tuning.json",
    )
    args = parser.parse_args()
    catalog = compile_catalog(
        apply_tuning(json.loads(args.inventory.read_text()), json.loads(args.tuning.read_text())),
        json.loads(args.characters.read_text()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(catalog) + b"\n")
    print(
        json.dumps(
            {
                "skills": len(catalog["skills"]),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
