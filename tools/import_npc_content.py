#!/usr/bin/env python3
"""Compile selected static NPCs and reuse the pinned Blender actor converter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from content_compile import (
    ROOT,
    _normalise_motions,
    canonical_bytes,
    fetch_server_references,
    source_archive,
)
from content_formats import parse_motion_list, parse_race_script
from fetch_test_assets import METIN_COMMIT
from metin_archive import safe_path
from metin_root_motion import _carbon_reader
from npc_definitions import material_paths, motion_groups, point_spawns

DEFAULT_PROFILE = ROOT / "content/profiles/yongan-city-guard.json"


def conversion_inputs(profile: Path, normalized: Path) -> dict[str, str]:
    files = [profile.resolve(), normalized.resolve()]
    files.extend(
        ROOT / "tools" / name
        for name in (
            "import_npc_content.py",
            "npc_definitions.py",
            "import_actor_content.py",
            "gr2_bindings.py",
            "metin_gr2_adapter.py",
            "content_compile.py",
            "content_formats.py",
        )
    )
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def compile_profile(path: Path, *, offline: bool) -> dict:
    profile = json.loads(path.read_text())
    if (
        type(profile["schema_version"]) is not int
        or profile["schema_version"] != 1
        or profile["source"]["client_revision"] != METIN_COMMIT
    ):
        raise ValueError("Unsupported NPC profile schema or client revision")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", profile["profile_id"]):
        raise ValueError("Invalid NPC profile identity")
    if not 1 <= len(profile["npcs"]) <= 128 or not 1 <= len(profile["spawns"]) <= 4096:
        raise ValueError("NPC profile exceeds supported content bounds")
    archive = source_archive(offline)
    references = fetch_server_references(profile, offline=offline)
    source = (
        ROOT / "assets/source/content/server" / profile["source"]["server_reference"]["revision"]
    )
    proto = list(
        csv.DictReader(
            (source / "gamefiles/conf/mob_proto.txt").read_text(errors="replace").splitlines(),
            delimiter="\t",
        )
    )
    names = dict(
        line.split("\t", 1)
        for line in (source / "gamefiles/conf/mob_names_en.txt")
        .read_text(encoding="latin-1")
        .splitlines()
        if "\t" in line
    )
    npc_list = [
        line.split()
        for line in archive.get("bin/pack/root/npclist.txt")
        .read_text(errors="replace")
        .splitlines()
    ]
    declarations = []
    catalog = []
    ids, vnums, outputs = set(), set(), set()
    for selected in profile["npcs"]:
        actor_id, vnum = selected["id"], selected["vnum"]
        if (
            not re.fullmatch(r"actor\.npc\.[a-z0-9.-]+", actor_id)
            or actor_id in ids
            or type(vnum) is not int
            or not 0 < vnum <= 2**32 - 1
            or vnum in vnums
        ):
            raise ValueError("Invalid or duplicate NPC identity")
        ids.add(actor_id)
        vnums.add(vnum)
        records = [row for row in proto if row.get("VNUM") == str(vnum)]
        mapping = [row for row in npc_list if row and row[0] == str(vnum)]
        if (
            len(records) != 1
            or records[0].get("TYPE") != "NPC"
            or "NOMOVE" not in records[0].get("AI_FLAG", "").split(",")
        ):
            raise ValueError(f"NPC {vnum} is not a source stationary NPC")
        if len(mapping) != 1 or mapping[0][1] != selected["model_key"] or str(vnum) not in names:
            raise ValueError(f"NPC {vnum} has inconsistent client/name catalogs")
        root = safe_path(selected["source_root"])
        msm = archive.resolve(root + "/" + selected["model_key"] + ".msm")
        race = parse_race_script(archive.get(msm).read_text())
        model = archive.resolve(race["base_model"])
        if not model.lower().endswith(".gr2"):
            raise ValueError("NPC model must resolve to GR2")
        motlist = archive.resolve(root + "/motlist.txt")
        motions = motion_groups(parse_motion_list(archive.get(motlist).read_text()))
        raw_model = _carbon_reader().read_raw(archive.get(model).read_bytes()).file_info
        textures = [archive.resolve(name) for name in material_paths(raw_model)]
        archive.fetch_many(textures)
        yaw = selected["yaw_correction_degrees"]
        if type(yaw) not in (int, float) or not math.isfinite(yaw) or abs(yaw) > 360:
            raise ValueError("Invalid NPC orientation")
        output = safe_path(selected["output"])
        if not output.endswith(".glb") or output in outputs:
            raise ValueError("NPC output must be a unique GLB path")
        outputs.add(output)
        declarations.append(
            {
                "id": actor_id,
                "kind": "npc",
                "vnum": vnum,
                "name": names[str(vnum)],
                "model_key": selected["model_key"],
                "race_script": msm,
                "motion_root": model.rsplit("/", 1)[0],
                "model": model,
                "textures": textures,
                "output": output,
                "attachment_bones": {},
                "orientation": {"output_forward": "-Z", "yaw_correction_degrees": yaw},
                "modes": [{"id": "general", "motions": motions}],
            }
        )
        catalog.append(
            {
                "id": actor_id,
                "vnum": vnum,
                "name": names[str(vnum)],
                "kind": "stationary-npc",
                "model_key": selected["model_key"],
                "source_collision": race["collision"],
            }
        )
    actors, unsupported = _normalise_motions({"actors": declarations}, archive)
    for actor in actors:
        for mode in actor["modes"]:
            for motion in mode["motions"]:
                animation = (
                    _carbon_reader()
                    .read_raw(archive.get(motion["source_gr2"]).read_bytes())
                    .file_info["Animations"]
                )
                if len(animation) != 1:
                    raise ValueError("NPC motion must contain one original animation")
                duration = float(animation[0]["Duration"])
                if not math.isfinite(duration) or not 0 < duration <= 60:
                    raise ValueError("NPC animation duration is outside supported bounds")
                clip_us = round(duration * 1_000_000)
                if abs(clip_us - motion["duration_us"]) > 1:
                    if motion["events"]:
                        raise ValueError("NPC event timing differs from its original GR2 clip")
                    # ActorInstance::GetMotionDuration uses the Granny animation,
                    # not the MSA Duration field. Soon's idle differs by 0.5 s.
                    motion["source_msa_duration_us"] = motion["duration_us"]
                    motion["duration_us"] = clip_us
    deferred = profile.get("deferred_motion_events", [])
    actual = [
        {"action_id": entry["action_id"], "event_type": entry.get("event_type")}
        for entry in unsupported
    ]
    if actual != deferred or any(".normal_attack" not in e["action_id"] for e in actual):
        raise ValueError(f"NPC motion metadata has unsupported records: {unsupported}")
    spawns = []
    spawn_ids = set()
    for selected in profile["spawns"]:
        spawn_id = selected["id"]
        if not re.fullmatch(r"spawn\.[a-z0-9.-]+", spawn_id) or spawn_id in spawn_ids:
            raise ValueError("Invalid or duplicate spawn identity")
        spawn_ids.add(spawn_id)
        if not re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", selected["map_id"]):
            raise ValueError("Invalid spawn map identity")
        matches = [npc for npc in catalog if npc["id"] == selected["actor_id"]]
        if len(matches) != 1:
            raise ValueError("Spawn refers to an unselected NPC")
        relative = safe_path(selected["source"])
        if relative not in {record["path"] for record in references}:
            raise ValueError("Spawn source is not pinned")
        rows = point_spawns((source / relative).read_text(encoding="latin-1"), matches[0]["vnum"])
        occurrence = selected["occurrence"]
        if type(occurrence) is not int or not 0 <= occurrence < len(rows):
            raise ValueError("Spawn occurrence is out of bounds")
        spawns.append(
            {
                "id": spawn_id,
                "actor_id": selected["actor_id"],
                "map_id": selected["map_id"],
                "source": relative,
                **rows[occurrence],
            }
        )
    sources = [
        {"path": path, "revision": METIN_COMMIT, **record}
        for path, record in sorted(archive.used.items())
    ] + references
    payload = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "compiler_version": "npc-content-v1.0.0",
        "actors": actors,
        "items": [],
        "npc_catalog": catalog,
        "deferred_motion_events": unsupported,
        "spawns": spawns,
        "sources": sources,
        "distribution": profile["distribution"],
    }
    payload["content_hash"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--blender", help="Also run the existing background actor converter")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/p3-npcs/city-guard")
    args = parser.parse_args()
    manifest = compile_profile(args.profile, offline=args.offline)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    normalized = output / "normalized.v1.json"
    normalized.write_text(json.dumps(manifest, indent=2) + "\n")
    if args.blender:
        frozen = conversion_inputs(args.profile, normalized)
        (output / "conversion-receipt.json").write_text(
            json.dumps({"status": "started", "inputs": frozen}, indent=2) + "\n"
        )
        command = [
            args.blender,
            "--background",
            "--factory-startup",
            "-noaudio",
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "tools/import_actor_content.py"),
            "--",
            "--manifest",
            str(normalized),
            "--source-root",
            str(ROOT / "assets/source/content" / METIN_COMMIT),
            "--output",
            str(output / "generated"),
            "--report",
            str(output / "blender-report.json"),
        ]
        with (output / "blender.log").open("w") as log:
            result = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False
            )
        if result.returncode:
            raise RuntimeError(f"NPC conversion failed; see {output / 'blender.log'}")
        if conversion_inputs(args.profile, normalized) != frozen:
            raise RuntimeError("NPC conversion inputs changed during the run")
        report = json.loads((output / "blender-report.json").read_text())
        if report.get("status") != "converted":
            raise RuntimeError("NPC converter did not produce a successful report")
        for artifact in report["artifacts"]:
            path = output / "generated" / safe_path(artifact["relative_path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                raise RuntimeError("NPC artifact differs from its conversion report")
        (output / "conversion-receipt.json").write_text(
            json.dumps(
                {
                    "status": "converted",
                    "inputs": frozen,
                    "content_hash": manifest["content_hash"],
                    "report_sha256": hashlib.sha256(
                        (output / "blender-report.json").read_bytes()
                    ).hexdigest(),
                },
                indent=2,
            )
            + "\n"
        )
    print(
        json.dumps(
            {
                "content_hash": manifest["content_hash"],
                "npcs": len(manifest["actors"]),
                "motions": sum(
                    len(mode["motions"]) for actor in manifest["actors"] for mode in actor["modes"]
                ),
                "spawns": manifest["spawns"],
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
