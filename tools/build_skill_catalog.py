#!/usr/bin/env python3
"""Compile selected original skill data; formulas become bounded coefficients, never scripts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path

from content_compile import ROOT, canonical_bytes, source_archive
from fetch_test_assets import METIN_COMMIT

PROFILE = ROOT / "content/profiles/classic-skills.json"
OUTPUT = ROOT / "client/assets/imported/skills/catalog.v1.json"
TERMS = [(), ("atk",), ("atk", "k"), ("k", "str"), ("dex", "k"), ("con", "k")]


def polynomial(text: str) -> dict[tuple[str, ...], float]:
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not -10000 <= node.value <= 10000:
                raise ValueError("Formula constant exceeds bounds")
            return {(): float(node.value)}
        if isinstance(node, ast.Name) and node.id in {"atk", "str", "dex", "con", "k"}:
            return {(node.id,): 1.0}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            sign = -1 if isinstance(node.op, ast.USub) else 1
            return {term: sign * value for term, value in visit(node.operand).items()}
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            a, b = visit(node.left), visit(node.right)
            result = dict(a) if not isinstance(node.op, ast.Mult) else {}
            if isinstance(node.op, ast.Mult):
                for x, value in a.items():
                    for y, other in b.items():
                        term = tuple(sorted(x + y))
                        if len(term) > 2:
                            raise ValueError("Unsupported polynomial degree")
                        result[term] = result.get(term, 0) + value * other
            else:
                sign = -1 if isinstance(node.op, ast.Sub) else 1
                for term, value in b.items():
                    result[term] = result.get(term, 0) + sign * value
            return result
        raise ValueError("Unsupported skill formula syntax")

    if len(text) > 256:
        raise ValueError("Skill formula is too long")
    return visit(ast.parse(text, mode="eval").body)


def compile_catalog(profile: dict, *, offline: bool) -> dict:
    if set(profile) != {"schema_version", "skills"} or profile["schema_version"] != 1:
        raise ValueError("Invalid skill profile")
    if not isinstance(profile["skills"], list) or not 1 <= len(profile["skills"]) <= 64:
        raise ValueError("Select between 1 and 64 skills")
    archive = source_archive(offline)
    paths = {
        "table": "bin/pack/locale_en/locale/en/skilltable.txt",
        "description": "bin/pack/locale_en/locale/en/skilldesc.txt",
        "powers": "src/UserInterface/Locale.cpp",
    }
    source = {key: archive.get(path).read_text(errors="replace") for key, path in paths.items()}
    power_match = re.search(
        r"INTERNATIONAL_SKILL_POWERS\[SKILL_POWER_NUM\]\s*=\s*\{(.*?)\}", source["powers"], re.S
    )
    if not power_match:
        raise ValueError("Missing international skill power table")
    power_text = re.sub(r"//[^\n]*", "", power_match[1])
    powers = [int(value) for value in re.findall(r"\d+", power_text)][:21]
    if len(powers) != 21 or powers[0] != 0 or powers != sorted(set(powers)) or powers[-1] > 100:
        raise ValueError("Unsupported normal/master skill power table")
    base = json.loads(
        (ROOT / "client/assets/imported/content/p0-warrior-dog/manifest.v1.json").read_text()
    )
    characters = json.loads(
        (ROOT / "client/assets/imported/characters/catalog.v1.json").read_text()
    )
    actors = {actor["id"]: actor for actor in characters["actors"]}
    actors.update({actor["id"]: actor for actor in base["actors"]})
    skills, seen, names = [], set(), set()
    for selected in profile["skills"]:
        fields = {
            "id",
            "vnum",
            "class_id",
            "minimum_level",
            "maximum_rank",
            "handler",
            "motion",
            "weapon_class",
        }
        if (
            set(selected) != fields
            or selected["handler"] != "physical_splash_v1"
            or selected["weapon_class"] != "sword"
        ):
            raise ValueError("Unsupported skill selection or handler")
        for key, lo, hi in [
            ("vnum", 1, 255),
            ("class_id", 0, 3),
            ("minimum_level", 5, 99),
            ("maximum_rank", 1, 20),
        ]:
            if type(selected[key]) is not int or not lo <= selected[key] <= hi:
                raise ValueError("Invalid skill selection " + key)
        if (
            not re.fullmatch(r"skill\.[a-z0-9.-]+", selected["id"])
            or selected["vnum"] in seen
            or selected["id"] in names
            or selected["motion"] != f"skill_{selected['vnum']}"
        ):
            raise ValueError("Duplicate or invalid skill ID")
        seen.add(selected["vnum"])
        names.add(selected["id"])
        rows = {}
        for key in ("table", "description"):
            matches = [
                line.split("\t")
                for line in source[key].splitlines()
                if line.split("\t")[0] == str(selected["vnum"])
            ]
            if len(matches) != 1:
                raise ValueError("Skill source row is missing or ambiguous")
            rows[key] = matches[0]
        row, desc = rows["table"], rows["description"]
        if (
            len(row) != 27
            or int(row[2]) != selected["class_id"] + 1
            or row[6] != "HP"
            or row[14] != "ATTACK,USE_MELEE_DAMAGE"
            or row[22] != "MELEE"
        ):
            raise ValueError("Unsupported source skill mechanic")
        damage = {term: -value for term, value in polynomial(row[7]).items()}
        if set(damage) - set(TERMS) or any(not 0 <= value <= 1000 for value in damage.values()):
            raise ValueError("Unsupported damage coefficients")
        cost = polynomial(row[8])
        if set(cost) - {(), ("k",)} or any(not 0 <= value <= 1000 for value in cost.values()):
            raise ValueError("Unsupported SP cost formula")
        variants = []
        cls = next(c for c in characters["classes"] if c["class_id"] == selected["class_id"])
        for variant in cls["variants"]:
            actor = actors[variant["actor_id"]]
            matches = [
                m
                for mode in actor["modes"]
                for m in mode["motions"]
                if m["action"] == selected["motion"]
            ]
            if len(matches) != 1:
                raise ValueError("Import each selected skill motion before compiling skills")
            motion = matches[0]
            hits = [e for e in motion["events"] if e["kind"] == "attack_window"]
            if (
                len(hits) != 1
                or not 0 < hits[0]["start_us"] < hits[0]["end_us"] <= motion["duration_us"]
            ):
                raise ValueError("Skill requires one bounded hit window")
            root = motion["accumulation_m"]
            if (
                len(root) != 3
                or any(not math.isfinite(v) or abs(v) > 4 for v in root)
                or abs(root[1]) > 0.01
            ):
                raise ValueError("Unsupported skill root endpoint")
            variants.append(
                {
                    "actor_id": actor["id"],
                    "action_id": motion["action_id"],
                    "duration_us": motion["duration_us"],
                    "hit_start_us": hits[0]["start_us"],
                    "hit_end_us": hits[0]["end_us"],
                    "root_x_m": root[0],
                    "root_z_m": root[2],
                }
            )
        cooldown = int(row[11]) * 1_000_000
        radius = int(row[26]) / 100
        targets = int(row[23])
        if (
            not 1_000_000 <= cooldown <= 300_000_000
            or not 0 < radius <= 10
            or not 1 <= targets <= 32
        ):
            raise ValueError("Invalid cooldown/range/target count")
        skills.append(
            {
                **selected,
                "name": desc[2],
                "description": desc[5],
                "icon": "skill/warrior/" + desc[12] + "_01",
                "cooldown_us": cooldown,
                "radius_m": radius,
                "max_targets": targets,
                "sp_base": int(cost.get((), 0)),
                "sp_per_power": int(cost.get(("k",), 0)),
                "damage_milli": [round(damage.get(term, 0) * 1000) for term in TERMS],
                "variants": variants,
            }
        )
    return {
        "schema": "mt2spacetime.skills",
        "version": 1,
        "rank_power_percent": powers,
        "skills": sorted(skills, key=lambda row: row["vnum"]),
        "source_revision": METIN_COMMIT,
        "source_sha256": {path: archive.used[path]["sha256"] for path in paths.values()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=PROFILE)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    catalog = compile_catalog(json.loads(args.profile.read_text()), offline=args.offline)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(canonical_bytes(catalog) + b"\n")
    print(
        json.dumps(
            {
                "skills": len(catalog["skills"]),
                "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
