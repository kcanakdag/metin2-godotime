#!/usr/bin/env python3
"""Fetch a selected outdoor map, convert through Blender, assemble a Godot scene."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

from fetch_test_assets import CARBON_COMMIT, METIN_COMMIT, ROOT
from metin_archive import Archive, virtual_path, write_json
from metin_map_data import (
    attributes,
    heights,
    placements,
    property_data,
    seam_errors,
    settings,
    texture_set,
    water,
)


def prepare(archive, name):
    candidates = [p for p in archive.entries if p.endswith(f"/{name}/setting.txt")]
    if len(candidates) != 1:
        raise ValueError(f"Expected one map setting, found {candidates}")
    source = candidates[0].rsplit("/", 1)[0]
    config = settings(archive.get(candidates[0]).read_text())
    chunk_names = [
        f"{x:03}{y:03}" for x in range(config["size"][0]) for y in range(config["size"][1])
    ]
    paths = [p for p in archive.entries if p.startswith(source + "/")]
    archive.fetch_many(paths)
    chunks = []
    samples = {}
    for section in chunk_names:
        folder = archive.sources / source / section
        x, y = int(section[:3]), int(section[3:])
        samples[x, y] = heights((folder / "height.raw").read_bytes())
        attributes((folder / "attr.atr").read_bytes())
        water((folder / "water.wtr").read_bytes())
        tiles = (folder / "tile.raw").read_bytes()
        if len(tiles) != 258 * 258:
            raise ValueError(f"Invalid tile grid: {section}")
        objects = placements((folder / "areadata.txt").read_text())
        chunks.append({"id": section, "grid": [x, y], "source": str(folder), "objects": objects})
    seams = seam_errors(samples, config["height_scale"])
    if seams:
        raise ValueError(f"Height seam mismatch: {seams[:3]}")
    print(f"Read {len(chunks)} sections; all shared terrain edges agree", flush=True)

    # CRCs cannot be inferred from filenames. Cache the small text catalog once;
    # models/textures are fetched only for the selected map's dependencies.
    catalog = [
        p
        for p in archive.entries
        if p.startswith("bin/pack/Property/")
        and p.endswith((".prb", ".prt", ".pre", ".pra", ".prd"))
    ]
    archive.fetch_many(catalog)
    properties = {}
    for path in sorted(catalog):
        crc, fields = property_data((archive.sources / path).read_text(encoding="cp1252"))
        if crc in properties and properties[crc]["fields"] != fields:
            raise ValueError(f"Ambiguous property CRC: {crc}")
        properties[crc] = {"source": path, "fields": fields}
    needed = {r["crc"] for c in chunks for r in c["objects"]}
    selected = {}
    assets = {}
    for crc in sorted(needed):
        prop = properties.get(crc, {"fields": {}}).copy()
        fields = prop["fields"]
        kind = fields.get("propertytype", "Missing")
        reference = fields.get(
            {"Building": "buildingfile", "Tree": "treefile", "Effect": "effectfile"}.get(kind, "")
        )
        prop["kind"] = kind
        prop["status"] = "unsupported"
        prop["reason"] = {
            "Tree": "SpeedTree SPT conversion is not implemented",
            "Effect": "Metin2 particle/effect conversion is not implemented",
        }.get(kind, "Unsupported property type")
        if reference:
            try:
                path = archive.resolve(reference)
                prop["asset_source"] = path
                if kind == "Building" and path.lower().endswith(".gr2"):
                    asset_id = hashlib.sha256(path.encode()).hexdigest()[:16]
                    prop.update(asset_id=asset_id, status="pending", reason="")
                    assets[asset_id] = {"source": path, "local": str(archive.sources / path)}
                    # Preserve available attribute companions; never invent server collision.
                    companion = path.rsplit(".", 1)[0] + ".mdatr"
                    if companion in archive.entries:
                        archive.get(companion)
                        prop["attribute_source"] = companion
            except (FileNotFoundError, ValueError) as error:
                prop["reason"] = str(error)
        selected[crc] = prop
    archive.fetch_many(a["source"] for a in assets.values())
    textures = texture_set(archive.get(archive.resolve(config["texture_set"])).read_text())
    for texture in textures:
        path = archive.resolve(texture["path"])
        texture["source"] = path
        texture["local"] = str(archive.get(path))
    for chunk in chunks:
        tiles = (Path(chunk["source"]) / "tile.raw").read_bytes()
        if max(tiles) > len(textures):
            raise ValueError(f"Unknown terrain texture ID in {chunk['id']}")
    return {
        "version": 1,
        "map": name,
        "commit": METIN_COMMIT,
        "carbon_commit": CARBON_COMMIT,
        "settings": config,
        "chunks": chunks,
        "properties": selected,
        "assets": assets,
        "textures": textures,
        "seam_mismatches": 0,
    }


def resolve_materials(archive, manifest, inspection):
    textures = {}
    for asset_id, data in inspection.items():
        asset = manifest["assets"][asset_id]
        asset["inspection"] = data
        asset["materials"] = {}
        for reference in data.get("textures", []):
            try:
                path = archive.resolve(reference)
            except FileNotFoundError:
                # Old GR2s also use basename-only references relative to their model.
                directory = asset["source"].split("/", 3)[3].rsplit("/", 1)[0]
                path = archive.resolve(directory + "/" + virtual_path(reference).rsplit("/", 1)[-1])
            texture_id = hashlib.sha256(path.encode()).hexdigest()[:16]
            asset["materials"][reference] = texture_id
            textures[texture_id] = {"source": path, "local": str(archive.sources / path)}
    archive.fetch_many(t["source"] for t in textures.values())
    manifest["model_textures"] = textures


def run_blender(executable, manifest_path, stage):
    log = manifest_path.parent / f"blender-{stage}.log"
    with log.open("w") as stream:
        subprocess.run(
            [
                executable,
                "--background",
                "--factory-startup",
                "-noaudio",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "tools/blender_map_convert.py"),
                "--",
                "--manifest",
                str(manifest_path),
                "--stage",
                stage,
            ],
            check=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    print(f"Blender {stage} finished: {log.relative_to(ROOT)}", flush=True)


def run_godot(executable, work, name, arguments):
    environment = dict(os.environ)
    for variable, folder in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config")):
        directory = work / "godot" / folder
        directory.mkdir(parents=True, exist_ok=True)
        environment[variable] = str(directory)
    result = subprocess.run(
        [executable, "--headless", "--path", str(ROOT / "client"), *arguments],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    log = work / f"godot-{name}.log"
    log.write_text(result.stdout)
    if result.returncode or "ERROR:" in result.stdout:
        raise RuntimeError(f"Godot {name} failed; see {log}\n{result.stdout[-2000:]}")
    print(f"Godot {name} finished: {log.relative_to(ROOT)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", default="metin2_map_a1")
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--godot", default="godot")
    parser.add_argument(
        "--offline", action="store_true", help="Require all source files to be cached"
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="Fetch and validate without conversion"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Exit 2 if any placement is unsupported"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", args.map):
        parser.error("Map names must contain lowercase letters, digits and underscores")
    archive = Archive(offline=args.offline)
    archive.inventory()
    manifest = prepare(archive, args.map)
    output = ROOT / "client/assets/imported/maps" / args.map
    work = ROOT / ".local/map-import" / args.map
    manifest.update(output=str(output), work=str(work))
    work.mkdir(parents=True, exist_ok=True)
    manifest_path = work / "manifest.json"
    write_json(manifest_path, manifest)
    write_json(work / "sources.json", {"commit": METIN_COMMIT, "files": archive.used})
    if args.prepare_only:
        print(f"Prepared {len(manifest['assets'])} unique GR2 dependencies: {manifest_path}")
        return
    if not (ROOT / ".cache" / f"tools-blender-{CARBON_COMMIT}").is_dir():
        parser.error("Pinned Carbon importer missing; run make assets first")
    run_blender(args.blender, manifest_path, "inspect")
    resolve_materials(archive, manifest, json.loads((work / "inspection.json").read_text()))
    write_json(manifest_path, manifest)
    write_json(work / "sources.json", {"commit": METIN_COMMIT, "files": archive.used})
    run_blender(args.blender, manifest_path, "convert")
    conversion = json.loads((work / "conversion.json").read_text())
    for prop in manifest["properties"].values():
        if "asset_id" in prop:
            result = conversion["assets"][prop["asset_id"]]
            prop["status"] = result["status"]
            prop["reason"] = result.get("error", "")
    counts = Counter(
        manifest["properties"][r["crc"]]["status"] for c in manifest["chunks"] for r in c["objects"]
    )
    manifest["counts"] = dict(counts)
    write_json(manifest_path, manifest)
    # Stage only converted content in the client; raw source paths/catalog stay outside it.
    scene_data = {
        k: manifest[k] for k in ("map", "settings", "counts", "chunks", "properties", "textures")
    }
    for chunk in scene_data["chunks"]:
        chunk.pop("source", None)
    for texture in scene_data["textures"]:
        texture.pop("local", None)
    write_json(output / "map.json", scene_data)
    run_godot(
        args.godot,
        work,
        "import",
        [
            "--import",
            "--recovery-mode",
            "--lsp-port",
            "0",
            "--dap-port",
            "0",
            "--debug-server",
            "tcp://127.0.0.1:0",
        ],
    )
    run_godot(
        args.godot,
        work,
        "build",
        ["--script", str(ROOT / "tools/build_metin_map.gd"), "--", args.map],
    )
    run_godot(
        args.godot,
        work,
        "check",
        ["--script", str(ROOT / "tools/check_metin_map.gd"), "--", args.map],
    )
    report = {
        "map": args.map,
        "source_commit": METIN_COMMIT,
        "sections": len(manifest["chunks"]),
        "placements": dict(counts),
        "unique_models": len(manifest["assets"]),
        "conversion": conversion,
        "unsupported": {
            k: v for k, v in manifest["properties"].items() if v["status"] != "converted"
        },
        "scene": str(output / "map.tscn"),
        "seam_mismatches": 0,
    }
    write_json(work / "report.json", report)
    print(
        f"Scene: {output / 'map.tscn'}\nPlacements: {dict(counts)}\nReport: {work / 'report.json'}"
    )
    if args.strict and any(k != "converted" for k in counts):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
