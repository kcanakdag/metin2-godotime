"""Build the two bounded target-effect GLBs in an isolated background Blender."""

import argparse
import json
import math
import os
import sys
from fractions import Fraction
from pathlib import Path

import bpy


def empty_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.data.orphans_purge(do_recursive=True)


def source_to_blender(values):
    """Keep source XYZ in Blender's Z-up space; glTF export performs Y-up conversion."""
    x, y, z = values
    return (x / 100.0, y / 100.0, z / 100.0)


def make_material(name, texture):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    principled.inputs["Roughness"].default_value = 1.0
    principled.inputs["Specular IOR Level"].default_value = 0.0
    image = bpy.data.images.load(str(texture), check_existing=False)
    image.colorspace_settings.name = "sRGB"
    texture_node = nodes.new("ShaderNodeTexImage")
    texture_node.image = image
    links.new(texture_node.outputs["Color"], principled.inputs["Base Color"])
    links.new(texture_node.outputs["Alpha"], principled.inputs["Alpha"])
    # This makes embedded textures import as transparent. Exact unshaded tint,
    # alpha quantization, depth-write, culling and additive mode live in sidecars.
    material.surface_render_method = "DITHERED"
    return material


def build_mesh(asset, output):
    frames = asset["frames"]
    geometries = asset["geometries"]
    frame_count = len(frames)
    vertices = []
    frame_vertices = [[] for _ in range(frame_count)]
    faces = []
    uvs = []
    material_indices = []
    geometry_report = []
    vertex_offset = 0
    element_position = source_to_blender(asset["position_cm"])
    for geometry_index, geometry in enumerate(geometries):
        first = geometry["frames"][0]
        corner_count = len(first["position_indices"])
        if corner_count % 3:
            raise ValueError(f"{geometry['name']} is not a triangle list")
        for frame_index, source_frame in enumerate(geometry["frames"]):
            converted = frame_vertices[frame_index]
            for position_index in source_frame["position_indices"]:
                point = source_to_blender(source_frame["positions"][position_index])
                converted.append(tuple(point[axis] + element_position[axis] for axis in range(3)))
        vertices.extend(frame_vertices[0][vertex_offset : vertex_offset + corner_count])
        for corner in range(corner_count):
            source_uv = first["texture_coordinates"][first["texture_indices"][corner]]
            # Assign the raw MDE UV to Blender. Blender's glTF exporter performs
            # its single required V transform, yielding the source renderer's -V
            # modulo repeat; import_target_effects.py audits the GLB accessor.
            uvs.append(source_uv)
        first_face = len(faces)
        faces.extend(
            (vertex_offset + index, vertex_offset + index + 1, vertex_offset + index + 2)
            for index in range(0, corner_count, 3)
        )
        material_indices.extend([geometry_index] * (corner_count // 3))
        geometry_report.append(
            {
                "name": geometry["name"],
                "material_slot": geometry_index,
                "first_vertex": vertex_offset,
                "vertex_count": corner_count,
                "first_triangle": first_face,
                "triangle_count": corner_count // 3,
            }
        )
        vertex_offset += corner_count

    mesh = bpy.data.meshes.new(asset["id"])
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=True, clean_customdata=False)
    obj = bpy.data.objects.new(asset["id"], mesh)
    bpy.context.scene.collection.objects.link(obj)
    for geometry in geometries:
        obj.data.materials.append(
            make_material(
                f"{asset['id']}.{geometry['name']}", output / geometry["texture_resource"]
            )
        )
    for polygon, material_index in zip(mesh.polygons, material_indices, strict=True):
        polygon.material_index = material_index
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            uv_layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]

    obj.shape_key_add(name="Basis")
    for frame_index in range(1, frame_count):
        key = obj.shape_key_add(name=f"Frame_{frame_index:02}")
        for point_index, point in enumerate(frame_vertices[frame_index]):
            key.data[point_index].co = point
    keys = obj.data.shape_keys.key_blocks
    frame_delay = asset.get("frame_delay", 0.02)
    if (
        not isinstance(frame_delay, (int, float))
        or not math.isfinite(frame_delay)
        or not 0.000001 <= frame_delay <= 60
    ):
        raise ValueError("Invalid mesh animation frame delay")
    interval = Fraction(str(frame_delay)).limit_denominator(32767)
    if abs(float(interval) - frame_delay) > 1e-9:
        raise ValueError("Mesh frame delay cannot be represented by the bounded Blender timeline")
    for timeline_frame in range(frame_count + 1):
        active_frame = timeline_frame if timeline_frame < frame_count else 0
        for source_frame, key in enumerate(keys[1:], 1):
            key.value = 1.0 if source_frame == active_frame else 0.0
            key.keyframe_insert(
                data_path="value", frame=timeline_frame * interval.numerator, group="MeshFrames"
            )
    action = obj.data.shape_keys.animation_data.action
    action.name = "loop-loop"
    for layer in action.layers:
        for strip in layer.strips:
            for channel_bag in strip.channelbags:
                for curve in channel_bag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "CONSTANT"

    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = frame_count * interval.numerator
    bpy.context.scene.render.fps = interval.denominator
    bpy.context.scene.render.fps_base = 1.0
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    path = output / "models" / f"{asset['id']}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_animations=True,
        export_frame_range=True,
        export_force_sampling=False,
        export_skins=False,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_morph=True,
        export_morph_normal=False,
        export_morph_tangent=False,
    )
    return {
        "asset_id": asset["id"],
        "glb": str(path),
        "animation": action.name,
        "timeline_frames": [0, frame_count],
        "frame_count": frame_count,
        "vertices": len(vertices),
        "triangles": len(faces),
        "morph_targets": frame_count - 1,
        "geometries": geometry_report,
    }


def main():
    if not bpy.app.background:
        raise RuntimeError("Run this helper in a separate background Blender process")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    source = json.loads(args.input.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "models").mkdir(exist_ok=True)
    results = []
    for asset in source["assets"]:
        empty_scene()
        results.append(build_mesh(asset, args.output))
    report = {"blender_version": bpy.app.version_string, "assets": results}
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
    # Blender 5.2 can finish both GLB writes and then stall in audio teardown in
    # restricted background sessions. This helper owns a disposable process, and
    # every output/report write above is already closed, so bypass global teardown.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
