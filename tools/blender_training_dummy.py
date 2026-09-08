"""Generate an authored straw practice target; run in an isolated Blender process.

No original game assets or runtime Blender dependency. Dimensions and materials
come from the reviewed profile. Never run against the user's open scene.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, color):
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.95
    return value


def cylinder(name, position, radius, depth, surface, parent, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=radius, depth=depth, location=position, rotation=rotation
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(surface)
    obj.parent = parent
    return obj


def build(profile, output):
    if not bpy.app.background:
        raise RuntimeError("Use background Blender to preserve the interactive editor")
    scene = bpy.data.scenes.new("MT2 Training Dummy")
    bpy.context.window.scene = scene
    scene.render.fps = 30
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    root = bpy.data.objects.new("DummyRoot", None)
    scene.collection.objects.link(root)
    body = bpy.data.objects.new("DummySway", None)
    scene.collection.objects.link(body)
    body.parent = root
    surfaces = {name: material(name, color) for name, color in profile["colors"].items()}
    height, radius = profile["height_m"], profile["body_radius_m"]
    cylinder("Foot", (0, 0, 0.055), 0.43, 0.11, surfaces["wood"], root)
    cylinder("Post", (0, 0, height * 0.46), 0.075, height * 0.92, surfaces["wood"], body)
    cylinder("StrawTorso", (0, 0, height * 0.59), radius, height * 0.38, surfaces["straw"], body)
    cylinder(
        "Crossbar", (0, 0, height * 0.7), 0.07, 1.22, surfaces["wood"], body, (0, math.pi / 2, 0)
    )
    for side in (-1, 1):
        cylinder(
            "ArmWrap",
            (side * 0.43, 0, height * 0.7),
            0.12,
            0.29,
            surfaces["straw"],
            body,
            (0, math.pi / 2, 0),
        )
    cylinder("Head", (0, 0, height * 0.895), radius * 0.67, height * 0.19, surfaces["straw"], body)
    for index, z in enumerate((0.42, 0.49, 0.69, 0.75, 0.87, 0.92)):
        band_radius = radius * (0.68 if index >= 4 else 1.02)
        bpy.ops.mesh.primitive_torus_add(
            major_segments=24,
            minor_segments=6,
            location=(0, 0, height * z),
            major_radius=band_radius,
            minor_radius=0.018,
        )
        obj = bpy.context.object
        obj.name = "RopeBinding"
        obj.parent = body
        obj.data.materials.append(surfaces["rope"])
    # Export maps Blender +Y to Godot -Z: the red target faces the actor's front.
    cylinder(
        "Target",
        (0, radius + 0.008, height * 0.61),
        0.14,
        0.025,
        surfaces["target"],
        body,
        (math.pi / 2, 0, 0),
    )
    cylinder(
        "TargetCenter",
        (0, radius + 0.025, height * 0.61),
        0.055,
        0.016,
        surfaces["straw"],
        body,
        (math.pi / 2, 0, 0),
    )
    # Fine alternating straw ribs give readable structure without texture downloads.
    for index in range(24):
        angle = index * math.tau / 24
        cylinder(
            "StrawRib",
            (math.cos(angle) * radius, math.sin(angle) * radius, height * 0.59),
            0.011,
            height * 0.365,
            surfaces["rope" if index % 4 == 0 else "straw"],
            body,
        )
    clips = {
        "wait": [(0, 0.0), (30, 0.008), (60, 0.0)],
        "damage": [(0, 0.0), (3, -0.09), (8, 0.045), (15, 0.0)],
        "dead": [(0, 0.0), (12, -0.2), (30, -0.2)],
    }
    for name, keys in clips.items():
        body.animation_data_create()
        body.animation_data.action = None
        for frame, angle in keys:
            body.rotation_euler.x = angle
            body.keyframe_insert(data_path="rotation_euler", frame=frame)
        action = body.animation_data.action
        action.name = name
        action.use_fake_user = True
        track = body.animation_data.nla_tracks.new()
        track.name = name
        track.strips.new(name, 0, action)
    body.animation_data.action = None
    body.rotation_euler.x = 0
    scene.frame_start, scene.frame_end = 0, 60
    scene.frame_set(0)
    bpy.context.view_layer.update()
    points = [
        o.matrix_world @ Vector(corner)
        for o in scene.objects
        if o.type == "MESH"
        for corner in o.bound_box
    ]
    points = [(p.x, p.z, -p.y) for p in points]
    bounds = [[fn(p[axis] for p in points) for axis in range(3)] for fn in (min, max)]
    for obj in scene.objects:
        if obj.type == "MESH":
            obj.data.calc_loop_triangles()
    triangles = sum(len(o.data.loop_triangles) for o in scene.objects if o.type == "MESH")
    output.mkdir(parents=True, exist_ok=True)
    model = output / "training-dummy.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(model),
        export_format="GLB",
        use_active_scene=True,
        export_animations=True,
        export_animation_mode="NLA_TRACKS",
        export_force_sampling=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "training-dummy.blend"))
    actor_id = profile["id"]
    resource = "res://assets/imported/authored/training-dummy/training-dummy.glb"
    motions = [
        {
            "action_id": f"{actor_id}.general.{name}",
            "action": {"damage": "front_damage", "dead": "front_death"}.get(name, name),
            "godot_name": name,
            "duration_us": keys[-1][0] * 1_000_000 // 30,
            "weight": 100,
            "loop": name == "wait",
        }
        for name, keys in clips.items()
    ]
    manifest = {
        "schema_version": 1,
        "definition_hash": hashlib.sha256(
            json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "artifacts": [
            {
                "id": actor_id,
                "path": resource,
                "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                "bounds_m": bounds,
                "triangles": triangles,
            }
        ],
        "actors": [
            {
                "id": actor_id,
                "vnum": profile["vnum"],
                "forward": "-Z",
                "motion_vector_space": "output_actor_local_godot",
                "model": {"artifact_id": actor_id, "path": resource},
                "modes": [{"id": "general", "motions": motions}],
            }
        ],
    }
    (output / "manifest.v1.json").write_text(json.dumps(manifest, indent=2) + "\n")
    report = {
        "blender": bpy.app.version_string,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "profile_sha256": hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
        "model_sha256": manifest["artifacts"][0]["sha256"],
        "objects": len(scene.objects),
        "triangles": triangles,
        "clips": list(clips),
        "origin": "project-authored-procedural-model",
    }
    (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    build(json.loads(args.profile.read_text()), args.output.resolve())


if __name__ == "__main__":
    main()
