#!/usr/bin/env python3
"""Resolve batch skill attachments against pinned source and installed GLB skeletons."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from content_compile import canonical_bytes, source_archive
from content_formats import parse_race_script
from fetch_test_assets import METIN_COMMIT
from import_target_effects import parse_glb
from metin_root_motion import _carbon_reader
from motion_effects import resolve_attachment


def joint_names(document: dict) -> set[str]:
    skins = document.get("skins", [])
    if len(skins) != 1 or not skins[0].get("joints"):
        raise ValueError("Expected one nonempty converted skeleton")
    nodes = document["nodes"]
    names = []
    for index in skins[0]["joints"]:
        if type(index) is not int or not 0 <= index < len(nodes):
            raise ValueError("Invalid converted joint index")
        name = nodes[index].get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Missing or duplicate converted bone name")
        names.append(name)
    return set(names)


def resolve_rows(rows: list, skeletons: dict) -> list:
    result = copy.deepcopy(rows)
    for row in result:
        if row.get("rejected_effects"):
            raise ValueError("Resolve rejected motion events before attachment linking")
        source, converted = skeletons[row["actor_id"]]
        row["effects"] = [resolve_attachment(e, source, converted) for e in row["effects"]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--characters", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists")
    inventory = json.loads(args.inventory.read_text())
    characters = json.loads(args.characters.read_text())
    if (
        inventory.get("schema") != "mt2spacetime.skill-motion-effect-inventory"
        or inventory.get("version") != 1
        or inventory.get("source_revision") != METIN_COMMIT
        or characters.get("schema") != "mt2spacetime.characters"
        or characters.get("version") != 1
    ):
        parser.error("Expected pinned skill inventory and converted character catalog")
    archive = source_archive(args.offline)
    reader = _carbon_reader()
    skeletons, evidence = {}, {}
    for row in inventory["motions"]:
        actor_id = row["actor_id"]
        if actor_id in skeletons:
            if row["race_sha256"] != evidence[actor_id]["race_sha256"]:
                raise ValueError("Conflicting race inputs for one appearance")
            continue
        race_bytes = archive.get(row["race_script"]).read_bytes()
        if hashlib.sha256(race_bytes).hexdigest() != row["race_sha256"]:
            raise ValueError("Race script changed since discovery")
        race = parse_race_script(race_bytes.decode())
        source_path = archive.resolve(race["base_model"])
        source_bytes = archive.get(source_path).read_bytes()
        raw = reader.read_raw(source_bytes).file_info
        if len(raw["Skeletons"]) != 1:
            raise ValueError("Expected one original skeleton")
        source = {b["Name"] for b in raw["Skeletons"][0]["Bones"]}
        if len(source) != len(raw["Skeletons"][0]["Bones"]):
            raise ValueError("Duplicate original bone names")
        actor = next(a for a in characters["actors"] if a["id"] == actor_id)
        artifact = next(
            a for a in characters["artifacts"] if a["id"] == actor["model"]["artifact_id"]
        )
        path = actor["model"]["path"]
        if not path.startswith("res://") or artifact["path"] != path:
            raise ValueError("Invalid converted model path")
        model = (args.client / path.removeprefix("res://")).resolve()
        if not model.is_relative_to(args.client.resolve()):
            raise ValueError("Converted model escapes client")
        if hashlib.sha256(model.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("Converted model hash differs from catalog")
        converted = joint_names(parse_glb(model)[0])
        skeletons[actor_id] = source, converted
        evidence[actor_id] = {
            "race_sha256": row["race_sha256"],
            "source_model": source_path,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "converted_sha256": artifact["sha256"],
            "source_bones": len(source),
            "converted_bones": len(converted),
        }
    result = {
        **inventory,
        "runtime_status": "attachments-resolved-resources-unqualified",
        "motions": resolve_rows(inventory["motions"], skeletons),
        "skeletons": evidence,
        "character_catalog_sha256": hashlib.sha256(args.characters.read_bytes()).hexdigest(),
        "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
    }
    with args.output.open("xb") as output:
        output.write(canonical_bytes(result) + b"\n")
    events = [e for row in result["motions"] for e in row["effects"]]
    print(
        json.dumps(
            {
                "actors": len(skeletons),
                "events": len(events),
                "fallbacks": sum("resolution" in e for e in events),
                "disabled": sum(not e["enabled"] for e in events),
            }
        )
    )


if __name__ == "__main__":
    main()
