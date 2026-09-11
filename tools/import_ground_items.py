#!/usr/bin/env python3
"""Resolve selected original ground models and convert them with the shared Blender tool."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from content_compile import ROOT, canonical_bytes, source_archive
from fetch_test_assets import METIN_COMMIT
from metin_archive import virtual_path
from metin_root_motion import _carbon_reader
from npc_definitions import material_bindings

ITEM_LIST = "bin/pack/locale_en/locale/en/item_list.txt"
DEFAULT_MODEL = "ymir work/item/etc/item_bag.gr2"
# Yang is currency, not a drop row, but the client renders every dropped coin
# with the original ``money.gr2`` ground mesh. Every package covers it even
# when the selection only names droppable items.
YANG_VNUM = 1
# A selection names item vnums; conversion and the runtime both work per
# distinct model. 235 of the 328 droppable registry rows resolve to the shared
# ``item_bag.gr2`` fallback, so 32 models cover every reachable drop.  Bound the
# vnum selection generously and keep the model bound where it belongs.
MAX_VNUMS = 4096
MAX_MODELS = 256


def selected_models(text, vnums):
    selected = set(vnums)
    if (
        not selected
        or len(selected) > MAX_VNUMS
        or any(type(v) is not int or not 0 < v <= 0xFFFFFFFF for v in selected)
    ):
        raise ValueError(f"Select 1–{MAX_VNUMS} positive item vnums")
    result = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if not fields[0].strip().isdigit() or int(fields[0]) not in selected:
            continue
        vnum = int(fields[0])
        if vnum in result or len(fields) not in (3, 4):
            raise ValueError(f"Duplicate or malformed selected item: {vnum}")
        model = virtual_path(fields[3]) if len(fields) == 4 else DEFAULT_MODEL
        if not model.endswith(".gr2"):
            raise ValueError(f"Unsupported ground model for {vnum}")
        result[vnum] = model
    if set(result) != selected:
        raise ValueError(f"Selected item definitions missing: {sorted(selected - set(result))}")
    models = set(result.values())
    if len(models) > MAX_MODELS:
        raise ValueError(
            f"Selection resolves to {len(models)} ground models; {MAX_MODELS} is the maximum"
        )
    return dict(sorted(result.items()))


def selection_vnums(path):
    """Every vnum of a compiled item selection (``tools/build_item_selection.py``)."""
    document = json.loads(Path(path).read_text())
    if document.get("schema_version") != 1 or not isinstance(document.get("items"), list):
        raise ValueError(f"Unsupported item selection: {path}")
    vnums = set()
    for row in document["items"]:
        vnum = row.get("vnum")
        if type(vnum) is not int or not 0 < vnum <= 0xFFFFFFFF or vnum in vnums:
            raise ValueError(f"Invalid item selection row: {row!r}")
        vnums.add(vnum)
    if not vnums:
        raise ValueError(f"Empty item selection: {path}")
    return sorted(vnums)


def coverage_vnums(vnums):
    """Union a selection with the vnums the client renders outside drop rolls."""
    return sorted(set(vnums) | {YANG_VNUM})


def normalize(vnums, *, offline=False):
    archive = source_archive(offline)
    selected = selected_models(
        archive.get(ITEM_LIST).read_text(encoding="utf-8-sig"), coverage_vnums(vnums)
    )
    assets, entries = {}, []
    for vnum, virtual in selected.items():
        model = archive.resolve(virtual)
        if model not in assets:
            raw = _carbon_reader().read_raw(archive.get(model).read_bytes()).file_info
            bindings = {
                key: archive.resolve(value)
                for key, value in material_bindings(raw, "/".join(model.split("/")[3:-1])).items()
            }
            archive.fetch_many(sorted(set(bindings.values())))
            key = hashlib.sha256(model.encode()).hexdigest()[:16]
            assets[model] = {
                "id": "ground.item." + key,
                "source_model": model,
                "source_textures": sorted(set(bindings.values())),
                "material_texture_bindings": bindings,
                "output": f"models/{key}.glb",
            }
        entries.append({"vnum": vnum, "model_id": assets[model]["id"]})
    document = {
        "schema_version": 1,
        "profile_id": "selected-ground-items-v1",
        "actors": [],
        "items": sorted(assets.values(), key=lambda row: row["id"]),
        "ground_items": entries,
        "sources": [
            {"path": path, "revision": METIN_COMMIT, **record}
            for path, record in sorted(archive.used.items())
        ],
    }
    document["content_hash"] = hashlib.sha256(canonical_bytes(document)).hexdigest()
    return document, archive.sources


def preview(output, godot):
    project = output / "preview"
    project.mkdir()
    shutil.copytree(output / "generated", project / "generated")
    shutil.copy2(output / "normalized.v1.json", project / "normalized.v1.json")
    shutil.copy2(ROOT / "tools/ground_items_preview.gd", project / "ground_items_preview.gd")
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Ground Item Preview"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(output / "preview-data"),
        "XDG_CONFIG_HOME": str(output / "preview-config"),
    }
    for name, command in (
        ("import", [godot, "--headless", "--path", str(project), "--editor", "--import", "--quit"]),
        (
            "runtime",
            [
                "xvfb-run",
                "-a",
                godot,
                "--path",
                str(project),
                "--script",
                "res://ground_items_preview.gd",
            ],
        ),
    ):
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        log = result.stdout + result.stderr
        (output / f"godot-{name}.log").write_text(log)
        if result.returncode or "SCRIPT ERROR:" in log or "ERROR:" in log:
            raise ValueError(f"Ground-item {name} failed; inspect its log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vnum", type=int, action="append")
    parser.add_argument(
        "--selection",
        type=Path,
        help="Compiled item selection whose every row is selected (mutually exclusive with --vnum)",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--blender")
    parser.add_argument("--godot", help="Import and render an isolated Linux/Xvfb preview")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.godot and not args.blender:
        parser.error("--godot requires --blender")
    if args.selection and args.vnum:
        parser.error("--selection and --vnum are mutually exclusive")
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Use a fresh output directory")
    vnums = selection_vnums(args.selection) if args.selection else (args.vnum or [1, 27001, 27002])
    document, sources = normalize(vnums, offline=args.offline)
    output.mkdir(parents=True)
    manifest = output / "normalized.v1.json"
    manifest.write_text(json.dumps(document, indent=2) + "\n")
    if args.blender:
        subprocess.run(
            [
                args.blender,
                "--background",
                "--factory-startup",
                "--python",
                str(ROOT / "tools/import_actor_content.py"),
                "--",
                "--manifest",
                str(manifest),
                "--source-root",
                str(sources),
                "--output",
                str(output / "generated"),
                "--report",
                str(output / "blender-report.json"),
            ],
            check=True,
        )
        report = json.loads((output / "blender-report.json").read_text())
        if report["status"] != "converted" or {a["id"] for a in report["artifacts"]} != {
            a["id"] for a in document["items"]
        }:
            raise ValueError("Incomplete ground-item conversion")
    if args.godot:
        preview(output, args.godot)
    print(
        json.dumps(
            {
                "items": len(document["ground_items"]),
                "models": len(document["items"]),
                "content_hash": document["content_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
