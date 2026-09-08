#!/usr/bin/env python3
"""Inventory the full pinned classic skill set and generate its actor-import selection."""

import argparse
import hashlib
import json
from pathlib import Path

from content_compile import ROOT, canonical_bytes, source_archive
from fetch_test_assets import METIN_COMMIT
from skill_definitions import discover_skills
from skill_formulas import compile_formula


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--character-profile", type=Path)
    options = parser.parse_args()
    archive = source_archive(options.offline)
    paths = [
        "bin/pack/root/playersettingmodule.py",
        "bin/pack/locale_en/locale/en/skilltable.txt",
        "bin/pack/locale_en/locale/en/skilldesc.txt",
    ]
    skills = discover_skills(*(archive.get(path).read_text(errors="replace") for path in paths))
    for skill in skills:
        skill["programs"] = {
            key: compile_formula(skill[key])
            for key in (
                "formula",
                "sp_cost",
                "duration",
                "sp_upkeep",
                "cooldown",
                "secondary_formula",
                "secondary_duration",
                "splash_scale",
            )
        }
    document = {
        "schema": "mt2spacetime.skill-source-inventory",
        "version": 1,
        "source_revision": METIN_COMMIT,
        "source_sha256": {path: archive.used[path]["sha256"] for path in paths},
        "skills": skills,
    }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_bytes(canonical_bytes(document) + b"\n")
    if options.character_profile:
        profile = json.loads((ROOT / "content/profiles/classic-characters.json").read_text())
        profile["skill_motions"] = [
            {"class_id": skill["class_id"], "action": skill["motion"], "file": skill["motion_file"]}
            for skill in skills
        ]
        options.character_profile.parent.mkdir(parents=True, exist_ok=True)
        options.character_profile.write_text(json.dumps(profile, indent=2) + "\n")
    print(
        json.dumps(
            {
                "skills": len(skills),
                "classes": 4,
                "trees": 8,
                "sha256": hashlib.sha256(options.output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
