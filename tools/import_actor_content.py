"""Background Blender conversion for the explicit actor/equipment content profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from pathlib import Path

import bpy

CONVERTER_VERSION = "actor-content-converter-v1.2.0"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def bootstrap(root: Path) -> str:
    sys.path.insert(0, str(root / "tools"))
    from fetch_test_assets import CARBON_COMMIT

    source = root / ".cache" / f"tools-blender-{CARBON_COMMIT}"
    for package in (source / "packages").glob("*/src"):
        sys.path.insert(0, str(package))
    sys.path.insert(0, str(source / "addons/carbon_eve_resources"))
    from carbon_granny import reader

    reader.GR2_MAGICS["b867b0caf86db10f84728c7e5e19001e"] = 4
    return CARBON_COMMIT


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def virtual_path(value: str) -> str:
    value = value.replace("\\", "/")
    if len(value) >= 3 and value[1:3] == ":/":
        value = value[3:]
    return value.lower()


def material_references(mesh: dict) -> list[str]:
    result = []
    for binding in mesh.get("MaterialBindings", []):
        maps = (binding.get("Material") or {}).get("Maps", [])
        diffuse = next((entry for entry in maps if entry["Usage"] == "Diffuse Color"), None)
        if diffuse is None:
            raise ValueError("Rendered material binding has no diffuse texture")
        result.append(virtual_path(diffuse["Map"]["Texture"]["FromFileName"]))
    return result


def texture_map(asset: dict, source_root: Path) -> dict[str, Path]:
    bindings = asset.get("material_texture_bindings")
    if bindings is not None:
        if set(bindings.values()) != set(asset["source_textures"]):
            raise ValueError("NPC material bindings differ from declared texture dependencies")
        return {name: source_root / path for name, path in bindings.items()}
    result = {}
    for source in asset["source_textures"]:
        parts = Path(source).parts
        result[virtual_path("/".join(parts[3:]))] = source_root / source
    hair = asset.get("default_hair")
    if hair is not None:
        source_parts = Path(hair["source_skin"]).parts
        result[virtual_path("/".join(source_parts[3:]))] = source_root / hair["target_skin"]
    return result


def skin_rest_matrices(bones: list[dict]) -> dict:
    from gr2_importer import addon

    names = set()
    for index, bone in enumerate(bones):
        parent = bone.get("parentIndex")
        if bone["name"] in names or type(parent) is not int or not -1 <= parent < index:
            raise ValueError("Skin skeleton has duplicate names or unordered/cyclic parents")
        names.add(bone["name"])
        for field, length in (("position", 3), ("orientation", 4), ("scaleShear", 9)):
            values = bone.get(field)
            if values is not None and (
                len(values) != length
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
            ):
                raise ValueError("Skin skeleton has an invalid rest transform")
    _, matrices = addon._compute_rest_matrices(bones)
    return {
        bone["name"]: [list(row) for row in matrix]
        for bone, matrix in zip(bones, matrices, strict=True)
    }


def merge_default_hair(
    graph: dict, actor: dict, source_root: Path
) -> tuple[dict, list[dict], dict | None]:
    """Merge the race script's selected skinned hair onto the base actor rig."""
    import carbon_gr2
    from carbon_granny import reader
    from gr2_bindings import validate_shared_skin_bones
    from metin_gr2_adapter import adapt_model_placement

    selected = actor.get("default_hair")
    if selected is None:
        return graph, [], None
    hair_path = source_root / selected["model"]
    hair_graph = carbon_gr2.read_gr2(hair_path)
    adapt_model_placement(hair_path, hair_graph)
    if (
        len(graph.get("models", [])) != 1
        or len(graph.get("skeletons", [])) != 1
        or len(hair_graph.get("models", [])) != 1
        or len(hair_graph.get("skeletons", [])) != 1
        or len(hair_graph.get("meshes", [])) != 1
        or hair_graph.get("animations")
        or hair_graph["models"][0].get("meshBindings") != [0]
    ):
        raise ValueError("Selected default hair does not have the expected single skinned mesh")
    hair_bones = {bone["name"] for bone in hair_graph["skeletons"][0]["bones"]}
    mesh = hair_graph["meshes"][0]
    bindings = mesh.get("boneBindings", [])
    binding_names = [binding.get("name") for binding in bindings]
    indices = mesh.get("vertex", {}).get("blendIndice", [])
    weights = mesh.get("vertex", {}).get("blendWeight", [])
    positions = mesh.get("vertex", {}).get("position", [])
    if (
        not hair_bones
        or len(indices) != len(weights)
        or len(indices) % 4 != 0
        or len(positions) != len(indices) // 4 * 3
    ):
        raise ValueError("Selected default hair skeleton is incompatible with the actor")
    weighted_bones = set()
    for offset in range(0, len(indices), 4):
        vertex_weights = weights[offset : offset + 4]
        if (
            any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
                for value in vertex_weights
            )
            or abs(sum(vertex_weights) - 1.0) > 1e-6
        ):
            raise ValueError("Selected default hair has invalid skin weights")
        for index, weight in zip(indices[offset : offset + 4], vertex_weights, strict=True):
            if not isinstance(index, (int, float)) or not float(index).is_integer():
                raise ValueError("Selected default hair has an invalid binding index")
            binding_index = int(index)
            if not 0 <= binding_index < len(binding_names):
                raise ValueError("Selected default hair binding index is out of range")
            if weight > 0.0:
                weighted_bones.add(binding_names[binding_index])
    shared_skin = validate_shared_skin_bones(
        skin_rest_matrices(graph["skeletons"][0]["bones"]),
        skin_rest_matrices(hair_graph["skeletons"][0]["bones"]),
        weighted_bones,
    )
    mesh_index = len(graph["meshes"])
    graph["meshes"].extend(hair_graph["meshes"])
    graph["models"][0]["meshBindings"].append(mesh_index)
    return (
        graph,
        reader.read_raw(hair_path.read_bytes()).file_info["Meshes"],
        {
            "hair_index": selected["hair_index"],
            "source_model": selected["model"],
            "source_skin": selected["source_skin"],
            "target_skin": selected["target_skin"],
            "mesh": mesh["name"],
            "vertices": len(positions) // 3,
            "weighted_bones": sorted(weighted_bones),
            "linked_skeleton_part": "main",
            **shared_skin,
        },
    )


def assign_materials(meshes: list, raw_meshes: list[dict], textures: dict[str, Path]) -> int:
    from pathlib import PurePosixPath

    from gr2_bindings import material_slots

    materials = {}
    textured_meshes = 0
    for mesh, original in zip(meshes, raw_meshes, strict=True):
        refs = material_references(original)
        if not refs:
            continue
        slots = material_slots(original, [face.material_index for face in mesh.data.polygons])
        mesh.data.materials.clear()
        for index, reference in enumerate(refs):
            maps = original["MaterialBindings"][index]["Material"].get("Maps", [])
            opacity = any(entry["Usage"] == "Opacity" for entry in maps)
            key = (reference, opacity)
            if reference not in textures:
                raise ValueError(f"Undeclared material dependency: {reference}")
            if key not in materials:
                material = bpy.data.materials.new("MT2." + PurePosixPath(reference).stem)
                material.use_nodes = True
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Roughness"].default_value = 0.85
                bsdf.inputs["Specular IOR Level"].default_value = 0.0
                image = bpy.data.images.load(str(textures[reference]), check_existing=True)
                if len(image.pixels) == 0:
                    raise ValueError(f"Could not decode texture: {textures[reference]}")
                node = material.node_tree.nodes.new("ShaderNodeTexImage")
                node.image = image
                material.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
                if opacity:
                    # Original BeginOpacityRender accepts byte alpha > 0. A half
                    # byte cutoff preserves that boundary in glTF's >= MASK test.
                    cutoff = material.node_tree.nodes.new("ShaderNodeMath")
                    cutoff.operation = "GREATER_THAN"
                    cutoff.inputs[1].default_value = 0.5 / 255.0
                    material.node_tree.links.new(node.outputs["Alpha"], cutoff.inputs[0])
                    material.node_tree.links.new(cutoff.outputs[0], bsdf.inputs["Alpha"])
                materials[key] = material
            mesh.data.materials.append(materials[key])
        for face, slot in zip(mesh.data.polygons, slots, strict=True):
            face.material_index = slot
        textured_meshes += 1
    if {key[0] for key in materials} != set(textures):
        raise ValueError(
            f"Declared texture set differs from GR2 bindings: declared={sorted(textures)}, "
            f"used={sorted(materials)}"
        )
    return textured_meshes


def empty_scene(name: str) -> None:
    old = bpy.context.scene
    scene = bpy.data.scenes.new(name)
    bpy.context.window.scene = scene
    if old and old.users == 0:
        bpy.data.scenes.remove(old)
    bpy.data.orphans_purge(do_recursive=True)
    # The glTF ACTIONS exporter considers every action datablock, including
    # actions whose armature was removed between profile actors.  Remove them
    # explicitly so an action from one skeleton can never leak into another
    # actor's GLB as an unresolved track.
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action, do_unlink=True)


def action_fcurves(action) -> list:
    if not action.layers or not action.slots:
        return []
    strip = action.layers[0].strips[0]
    channelbag = strip.channelbag(action.slots[0], ensure=False)
    return list(channelbag.fcurves) if channelbag is not None else []


def scale_action_locations(actions: list, factor: float) -> None:
    for action in actions:
        for curve in action_fcurves(action):
            if not curve.data_path.endswith(".location"):
                continue
            for key in curve.keyframe_points:
                key.co.y *= factor
                key.handle_left.y *= factor
                key.handle_right.y *= factor


def analyze_root_motion(actions: list, motions: list[dict], root_bone: str) -> list[dict]:
    path = f'pose.bones["{root_bone}"].location'
    result = []
    for action, motion in zip(actions, motions, strict=True):
        object_curves = [curve for curve in action_fcurves(action) if curve.data_path == "location"]
        if object_curves:
            raise ValueError(f"Armature node translation track in {motion['action_id']}")
        curves = [curve for curve in action_fcurves(action) if curve.data_path == path]
        displacement = [0.0, 0.0, 0.0]
        for curve in curves:
            values = [point.co.y for point in curve.keyframe_points]
            if not values:
                continue
            displacement[curve.array_index] = values[-1] - values[0]
        # The MSA Accumulation value is applied by the original actor controller
        # and is not baked into these locomotion clips.  Allow small resampling
        # drift while rejecting a second copy of authored horizontal travel.
        horizontal_displacement = math.hypot(displacement[0], displacement[1])
        if motion["action"] in {"walk", "run"} and horizontal_displacement > 0.05:
            raise ValueError(
                f"Locomotion root translates {horizontal_displacement}m in {motion['action_id']}"
            )
        result.append(
            {
                "action_id": motion["action_id"],
                "root_bone": root_bone,
                "root_bone_pose_displacement_blender_m": displacement,
                "armature_node_translation_tracks": 0,
                "source_accumulation_godot_m": motion["accumulation_m"],
                "source_accumulation_applied_to_clip": False,
            }
        )
    return result


def vertex_samples(scene, rig, meshes, actions: list) -> list[list[tuple[float, float, float]]]:
    result = []
    for action in actions or [None]:
        rig.animation_data_create()
        rig.animation_data.action = action
        if action is not None and action.slots:
            rig.animation_data.action_slot = action.slots[0]
        frame = int((action.frame_range.x + action.frame_range.y) / 2) if action else 0
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        result.append(
            [
                tuple(mesh.evaluated_get(depsgraph).matrix_world @ vertex.co)
                for mesh in meshes
                for vertex in mesh.evaluated_get(depsgraph).data.vertices
            ]
        )
    return result


def apply_scale(objects: list) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for obj in objects:
        if any(abs(value - 1.0) > 1e-6 for value in obj.scale):
            raise ValueError(f"Unbaked object scale on {obj.name}: {tuple(obj.scale)}")


def bounds(meshes: list) -> tuple[list[list[float]], int, int]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    vertices = triangles = 0
    for mesh in meshes:
        evaluated = mesh.evaluated_get(depsgraph)
        points.extend(evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices)
        vertices += len(evaluated.data.vertices)
        triangles += sum(len(polygon.vertices) - 2 for polygon in evaluated.data.polygons)
    if not points or not all(math.isfinite(value) for point in points for value in point):
        raise ValueError("Model has empty or nonfinite bounds")
    result = [
        [min(point[axis] for point in points) for axis in range(3)],
        [max(point[axis] for point in points) for axis in range(3)],
    ]
    if max(abs(value) for corner in result for value in corner) > 100:
        raise ValueError(f"Implausible meter-space model bounds: {result}")
    # Blender and source use Z-up; glTF/Godot import maps (x, y, z) to
    # (x, z, -y).  Report bounds in the same Godot coordinate space declared
    # by the profile manifest.
    godot_result = [
        [result[0][0], result[0][2], -result[1][1]],
        [result[1][0], result[1][2], -result[0][1]],
    ]
    return godot_result, vertices, triangles


def skeleton_signature(armature) -> tuple[str, list[dict]]:
    bones = list(armature.data.bones)
    indices = {bone.name: index for index, bone in enumerate(bones)}
    records = []
    for bone in bones:
        matrix = [round(value, 9) for row in bone.matrix_local for value in row]
        records.append(
            {
                "name": bone.name,
                "parent": indices[bone.parent.name] if bone.parent else -1,
                "matrix_local_m": matrix,
            }
        )
    return hashlib.sha256(canonical_bytes(records)).hexdigest(), records


def exercise_actions(scene, rig, meshes, motions: list[dict], actions: list) -> list[dict]:
    if len(motions) != len(actions):
        raise ValueError(f"Imported {len(actions)} actions for {len(motions)} motions")
    results = []
    scene.render.fps = 30
    for motion, action in zip(motions, actions, strict=True):
        action.name = motion["godot_name"]
        rig.animation_data.action = action
        if action.slots:
            rig.animation_data.action_slot = action.slots[0]
        frames = [int(action.frame_range.x), int((action.frame_range.x + action.frame_range.y) / 2)]
        samples = []
        for frame in frames:
            scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            samples.append(
                [
                    tuple(mesh.evaluated_get(depsgraph).matrix_world @ vertex.co)
                    for mesh in meshes
                    for vertex in mesh.evaluated_get(depsgraph).data.vertices
                ]
            )
        delta = max(math.dist(before, after) for before, after in zip(*samples, strict=True))
        if not math.isfinite(delta) or delta <= 1e-7:
            raise ValueError(f"No visible deformation in {motion['action_id']}")
        results.append(
            {
                "action_id": motion["action_id"],
                "godot_name": motion["godot_name"],
                "duration_us": motion["duration_us"],
                "max_vertex_delta_m": delta,
            }
        )
    return results


def export_glb(path: Path, objects: list, *, animations: bool, skins: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_animations=animations,
        export_animation_mode="ACTIONS" if animations else "ACTIVE_ACTIONS",
        export_skins=skins,
        export_yup=True,
        export_force_sampling=animations,
        export_cameras=False,
        export_lights=False,
    )


def convert_actor(actor: dict, source_root: Path, output: Path) -> dict:
    import carbon_gr2
    from carbon_granny import reader
    from gr2_bindings import normalize_rigid_bindings
    from gr2_importer import addon
    from metin_gr2_adapter import adapt_legacy_animation, adapt_model_placement

    empty_scene("Content " + actor["id"])
    model_path = source_root / actor["source_model"]
    graph = carbon_gr2.read_gr2(model_path)
    adapt_model_placement(model_path, graph)
    graph, hair_raw_meshes, hair_report = merge_default_hair(graph, actor, source_root)
    rigid_bindings = normalize_rigid_bindings(graph)
    motions = [motion for mode in actor["modes"] for motion in mode["motions"]]
    if not motions and actor.get("presentation") != "static":
        raise ValueError("Only explicitly static NPCs may omit animations")
    for motion in motions:
        path = source_root / motion["source_gr2"]
        animation_graph = carbon_gr2.read_gr2(path)
        adapt_legacy_animation(path, animation_graph)
        for animation in animation_graph["animations"]:
            animation["name"] = motion["godot_name"]
        if len(animation_graph["animations"]) != 1:
            raise ValueError(f"Expected one animation in {motion['source_gr2']}")
        graph["animations"].extend(animation_graph["animations"])
    imported = addon.import_gr2_json(
        graph,
        actor["id"],
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
    rig, meshes = imported["armature"], imported["meshes"]
    if rig is None or not meshes:
        raise ValueError(f"Actor import incomplete: {actor['id']}")
    raw = reader.read_raw(model_path.read_bytes()).file_info
    raw_meshes = [*raw["Meshes"], *hair_raw_meshes]
    textured_meshes = assign_materials(meshes, raw_meshes, texture_map(actor, source_root))
    samples_before_scale = vertex_samples(bpy.context.scene, rig, meshes, imported["actions"])
    apply_scale([rig, *meshes])
    scale_action_locations(imported["actions"], 0.01)
    samples_after_scale = vertex_samples(bpy.context.scene, rig, meshes, imported["actions"])
    scale_bake_error = max(
        math.dist(before, after)
        for before_action, after_action in zip(
            samples_before_scale, samples_after_scale, strict=True
        )
        for before, after in zip(before_action, after_action, strict=True)
    )
    if scale_bake_error > 1e-4:
        raise ValueError(f"Scale bake changed animated deformation by {scale_bake_error}m")
    root_bones = [bone.name for bone in rig.data.bones if bone.parent is None]
    if len(root_bones) != 1:
        raise ValueError(f"Expected one skeleton root, found {root_bones}")
    root_motion = analyze_root_motion(imported["actions"], motions, root_bones[0])
    for mesh in meshes:
        world = mesh.matrix_world.copy()
        mesh.parent = rig
        mesh.matrix_world = world
    rig.rotation_euler.z += math.radians(actor["orientation"]["yaw_correction_degrees"])
    bpy.context.view_layer.update()
    signature, bone_records = skeleton_signature(rig)
    attachment_report = {}
    for purpose, name in actor["attachment_bones"].items():
        bone = rig.data.bones.get(name)
        if bone is None:
            raise ValueError(f"Missing attachment bone {name!r} in {actor['id']}")
        attachment_report[purpose] = {
            "bone": name,
            "head_m": list(bone.head_local),
            "tail_m": list(bone.tail_local),
        }
    action_report = exercise_actions(bpy.context.scene, rig, meshes, motions, imported["actions"])
    rig.animation_data.action = imported["actions"][0] if imported["actions"] else None
    if rig.animation_data.action is not None and rig.animation_data.action.slots:
        rig.animation_data.action_slot = rig.animation_data.action.slots[0]
    bpy.context.scene.frame_set(0)
    model_bounds, vertices, triangles = bounds(meshes)
    target = output / actor["output"]
    export_glb(target, [rig, *meshes], animations=bool(motions), skins=True)
    return {
        "id": actor["id"],
        "type": "actor",
        "relative_path": actor["output"],
        "sha256": file_sha256(target),
        "bytes": target.stat().st_size,
        "mesh_count": len(meshes),
        "textured_mesh_count": textured_meshes,
        "vertices": vertices,
        "triangles": triangles,
        "bones": len(bone_records),
        "skeleton_signature": signature,
        "bounds_m": model_bounds,
        "forward": actor["orientation"]["output_forward"],
        "yaw_correction_degrees": actor["orientation"]["yaw_correction_degrees"],
        "attachment_bones": attachment_report,
        "motions": action_report,
        "root_motion": root_motion,
        "scale_bake_max_error_m": scale_bake_error,
        "rigid_bindings": rigid_bindings,
        **({"default_hair": hair_report} if hair_report is not None else {}),
    }


def convert_item(item: dict, source_root: Path, output: Path) -> dict:
    import carbon_gr2
    from carbon_granny import reader
    from gr2_importer import addon

    empty_scene("Content " + item["id"])
    model_path = source_root / item["source_model"]
    graph = carbon_gr2.read_gr2(model_path)
    raw = reader.read_raw(model_path.read_bytes()).file_info
    pairs = addon.import_meshes(
        graph, bpy.context.scene.collection, item["id"], 0.01, 0.0, False, 30.0, True, False, False
    )
    meshes = [pair[0] for pair in pairs]
    if not meshes or len(meshes) != len(graph["meshes"]):
        raise ValueError(f"Item import incomplete: {item['id']}")
    textured_meshes = assign_materials(meshes, raw["Meshes"], texture_map(item, source_root))
    apply_scale(meshes)
    model_bounds, vertices, triangles = bounds(meshes)
    target = output / item["output"]
    export_glb(target, meshes, animations=False, skins=False)
    return {
        "id": item["id"],
        "type": "item",
        "relative_path": item["output"],
        "sha256": file_sha256(target),
        "bytes": target.stat().st_size,
        "mesh_count": len(meshes),
        "textured_mesh_count": textured_meshes,
        "vertices": vertices,
        "triangles": triangles,
        "bounds_m": model_bounds,
    }


def main() -> None:
    args = arguments()
    root = Path(__file__).resolve().parents[1]
    importer_commit = bootstrap(root)
    manifest = json.loads(Path(args.manifest).read_text())
    source_root = Path(args.source_root)
    output = Path(args.output)
    report_path = Path(args.report)
    report = {
        "schema_version": 1,
        "profile_id": manifest["profile_id"],
        "converter_version": CONVERTER_VERSION,
        "blender_version": bpy.app.version_string,
        "importer_commit": importer_commit,
        "artifacts": [],
        "status": "failed",
    }
    try:
        for actor in manifest["actors"]:
            report["artifacts"].append(convert_actor(actor, source_root, output))
        for item in manifest["items"]:
            report["artifacts"].append(convert_item(item, source_root, output))
        report["artifacts"].sort(key=lambda artifact: artifact["id"])
        report["status"] = "converted"
    except Exception as error:
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["status"] != "converted":
        raise RuntimeError(report["error"])


if __name__ == "__main__":
    main()
