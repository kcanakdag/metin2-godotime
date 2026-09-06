"""Texture, exercise, and export the objects made by blender_import_probe.py."""

import math
from pathlib import Path

import bpy
from carbon_granny import reader


def finish_import(root, imported):
    root = Path(root)
    fixture = root / "assets/source/warrior"
    output = root / "client/assets/imported"
    output.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    rig = imported["armature"]
    meshes = imported["meshes"]
    raw = reader.read_raw((fixture / "warrior_novice.gr2").read_bytes())
    materials = {}
    textures = {}
    for mesh, original in zip(meshes, raw.file_info["Meshes"], strict=True):
        mesh.data.materials.clear()
        for binding in original["MaterialBindings"]:
            maps = binding["Material"]["Maps"]
            diffuse = next(m for m in maps if m["Usage"] == "Diffuse Color")
            name = (
                diffuse["Map"]["Texture"]["FromFileName"].replace("\\", "/").split("/")[-1].lower()
            )
            if name not in materials:
                texture = bpy.data.images.load(str(fixture / name), check_existing=False)
                # Decode the DDS before changing the lazily loaded image's path.
                assert len(texture.pixels) > 0, f"Could not decode {name}"
                texture.filepath_raw = str(output / (Path(name).stem + ".png"))
                texture.file_format = "PNG"
                texture.save()
                material = bpy.data.materials.new("MT2." + Path(name).stem)
                material.use_nodes = True
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Roughness"].default_value = 0.85
                bsdf.inputs["Specular IOR Level"].default_value = 0.0
                node = material.node_tree.nodes.new("ShaderNodeTexImage")
                node.image = texture
                material.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
                materials[name] = material
            mesh.data.materials.append(materials[name])
            textures[mesh.name] = name

    samples = {}
    scene.render.fps = 30
    for action in imported["actions"]:
        rig.animation_data.action = action
        rig.animation_data.action_slot = action.slots[0]
        positions = []
        for frame in (0, int(action.frame_range.y / 2)):
            scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            coords = []
            for mesh in meshes:
                evaluated = mesh.evaluated_get(depsgraph)
                coords.extend(
                    [tuple(evaluated.matrix_world @ v.co) for v in evaluated.data.vertices]
                )
            assert all(math.isfinite(v) for point in coords for v in point), action.name
            positions.append(coords)
        max_delta = max(math.dist(a, b) for a, b in zip(*positions, strict=True))
        assert max_delta > 0.00001, f"No visible deformation in {action.name}"
        samples[action.name] = {"max_vertex_delta_m": max_delta, "vertices": len(positions[0])}

    rig.animation_data.action = next(a for a in imported["actions"] if a.name.endswith(".wait"))
    rig.animation_data.action_slot = rig.animation_data.action.slots[0]
    scene.frame_set(0)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [rig, *meshes]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = rig
    path = output / "warrior.glb"
    for mesh in meshes:
        world = mesh.matrix_world.copy()
        mesh.parent = rig
        mesh.matrix_world = world
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_skins=True,
        export_yup=True,
        export_force_sampling=True,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(root / ".local/warrior.blend"), copy=True)
    return {
        "textures": textures,
        "animation_samples": samples,
        "glb": str(path),
        "bytes": path.stat().st_size,
    }
