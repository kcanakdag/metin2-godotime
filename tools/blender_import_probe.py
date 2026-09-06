"""Run in Blender via MCP or: blender --background --python tools/blender_import_probe.py.

Creates a separate scene. Does not register a global add-on or replace existing scenes.
"""

import json
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_test_assets import CARBON_COMMIT

source = ROOT / ".cache" / f"tools-blender-{CARBON_COMMIT}"
for package in (source / "packages").glob("*/src"):
    sys.path.insert(0, str(package))
sys.path.insert(0, str(source / "addons/carbon_eve_resources"))

import carbon_gr2
from carbon_granny import reader
from gr2_importer import addon
from metin_gr2_adapter import adapt_legacy_animation, adapt_model_placement

fixture = ROOT / "assets/source/warrior"
output = ROOT / ".local"
output.mkdir(exist_ok=True)
report = {
    "blender": bpy.app.version_string,
    "importer_commit": CARBON_COMMIT,
    "unmodified_importer": {},
    "adapted_reader": {},
    "status": "failed",
}

try:
    reader.GR2_MAGICS.pop("b867b0caf86db10f84728c7e5e19001e", None)
    for path in sorted(fixture.rglob("*.gr2")):
        try:
            report["unmodified_importer"][str(path.relative_to(fixture))] = carbon_gr2.inspect(path)
        except Exception as error:
            report["unmodified_importer"][str(path.relative_to(fixture))] = {"error": str(error)}

    # Metin2's older little-endian 32-bit Granny signature. No input bytes are changed.
    reader.GR2_MAGICS["b867b0caf86db10f84728c7e5e19001e"] = 4
    graph = carbon_gr2.read_gr2(fixture / "warrior_novice.gr2")
    adapt_model_placement(fixture / "warrior_novice.gr2", graph)
    for name in ("wait", "walk", "run", "attack"):
        path = fixture / "general" / f"{name}.gr2"
        parsed = carbon_gr2.read_gr2(path)
        adapt_legacy_animation(path, parsed)
        for animation in parsed["animations"]:
            animation["name"] = name
        graph["animations"].extend(parsed["animations"])
        report["adapted_reader"][name] = carbon_gr2.inspect(path)

    scene = bpy.data.scenes.new("MT2 Import Test")
    bpy.context.window.scene = scene
    imported = addon.import_gr2_json(
        graph,
        "Warrior",
        apply_skinning_flag=True,
        import_anims_flag=True,
        scale=0.01,
        rot_x_deg=0.0,
        flip_uv_v=True,
        use_smoothing_groups=False,
        smoothing_angle_deg=30.0,
        skip_lods=True,
        try_unpack_tangents=False,
        resample_anims=True,
        max_keys_per_bone=4096,
        action_length_mode="DURATION",
        clamp_keys_to_duration=True,
        action_end_padding_frames=0,
        bone_tail_mode="AUTO",
        collection_prefix="MT2",
    )
    armature = imported["armature"]
    report["scene"] = scene.name
    report["meshes"] = [
        {
            "name": m.name,
            "vertices": len(m.data.vertices),
            "polygons": len(m.data.polygons),
            "vertex_groups": len(m.vertex_groups),
            "materials": [s.material.name if s.material else None for s in m.material_slots],
        }
        for m in imported["meshes"]
    ]
    report["bones"] = len(armature.data.bones) if armature else 0
    report["animations"] = [
        {"name": a.name, "frames": list(a.frame_range)} for a in imported["actions"]
    ]
    from blender_finish_import import finish_import

    report["export"] = finish_import(ROOT, imported)
    for entry, mesh in zip(report["meshes"], imported["meshes"], strict=True):
        entry["materials"] = [m.name for m in mesh.data.materials]
    report["status"] = "exported"
    globals()["MT2_IMPORTED"] = imported
except Exception as error:
    report["error"] = str(error)
    report["traceback"] = traceback.format_exc()

(output / "blender-import-report.json").write_text(json.dumps(report, indent=2) + "\n")
result = report
if __name__ == "__main__" and report["status"] == "failed":
    raise RuntimeError(report.get("error", "Import failed"))
