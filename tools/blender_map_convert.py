"""Background-only GR2 inspection and map conversion. Keeps interactive Blender untouched."""

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

import bpy


def bootstrap(root, commit):
    sys.path.insert(0, str(root / "tools"))
    source = root / ".cache" / f"tools-blender-{commit}"
    for package in (source / "packages").glob("*/src"):
        sys.path.insert(0, str(package))
    sys.path.insert(0, str(source / "addons/carbon_eve_resources"))
    from carbon_granny import reader

    reader.GR2_MAGICS["b867b0caf86db10f84728c7e5e19001e"] = 4


def material_references(mesh):
    result = []
    for binding in mesh.get("MaterialBindings", []):
        maps = (binding["Material"] or {}).get("Maps", [])
        diffuse = next((m for m in maps if m["Usage"] == "Diffuse Color"), None)
        result.append(diffuse["Map"]["Texture"]["FromFileName"] if diffuse else None)
    return result


def inspect_assets(manifest):
    import carbon_gr2
    from carbon_granny import reader

    result = {}
    for key, asset in manifest["assets"].items():
        try:
            raw = reader.read_raw(Path(asset["local"]).read_bytes()).file_info
            graph = carbon_gr2.read_gr2(asset["local"])
            refs = sorted({t for m in raw.get("Meshes", []) for t in material_references(m) if t})
            result[key] = {
                "textures": refs,
                "meshes": len(graph["meshes"]),
                "animations": len(graph.get("animations", [])),
                "models": len(graph.get("models", [])),
            }
        except Exception as error:
            result[key] = {"error": str(error), "traceback": traceback.format_exc()}
    return result


def export_glb(path):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_animations=False,
        export_skins=False,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
    )


def empty_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.data.orphans_purge(do_recursive=True)


def png(source, target):
    image = bpy.data.images.load(str(source), check_existing=False)
    if len(image.pixels) == 0:
        raise ValueError(f"Cannot decode texture: {source}")
    image.filepath_raw = str(target)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def data_png(data, size, target):
    import numpy as np

    pixels = np.ones((size, size, 4), dtype=np.float32)
    pixels[:, :, :3] = np.frombuffer(data, dtype=np.uint8).reshape(size, size, 1)[::-1] / 255
    image = bpy.data.images.new(target.stem, size, size, alpha=False)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw = str(target)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)

    # These texels are integer IDs/bit flags, not colours. GPU block compression changes
    # their values, and averaged mipmaps invent IDs. Prevent Godot's 3D auto-detection
    # from silently switching the lossless import to VRAM compression during scene loads.
    target.with_suffix(".png.import").write_text(
        '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\n\n'
        "[params]\ncompress/mode=0\nmipmaps/generate=false\n"
        "detect_3d/compress_to=0\nprocess/fix_alpha_border=false\n"
    )


def terrain_array(textures, output):
    import numpy as np

    # Godot's normal layered-texture importer works with a headless renderer.
    # Saving a GPU-created ImageTextureLayered in headless mode loses its pixels.
    target = output / "terrain-array.png"
    target.with_suffix(".png.import").write_text(
        '[remap]\nimporter="2d_array_texture"\ntype="CompressedTexture2DArray"\n\n'
        "[params]\ncompress/mode=0\nmipmaps/generate=true\nslices/horizontal=1\n"
        f"slices/vertical={len(textures)}\n"
    )
    pixels = np.empty((512 * len(textures), 512, 4), dtype=np.float32)
    for index, texture in enumerate(textures):
        image = bpy.data.images.load(str(output / f"terrain-{texture['id']:02}.png"))
        image.scale(512, 512)
        values = np.empty(512 * 512 * 4, dtype=np.float32)
        image.pixels.foreach_get(values)
        # Blender pixels are bottom-up; the array's layer zero is the top slice.
        start = (len(textures) - index - 1) * 512
        pixels[start : start + 512] = values.reshape(512, 512, 4)
        bpy.data.images.remove(image)
    image = bpy.data.images.new("TerrainArray", 512, 512 * len(textures), alpha=True)
    image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw = str(target)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def convert_model(asset, output):
    import carbon_gr2
    from carbon_granny import reader
    from gr2_importer import addon

    if "error" in asset["inspection"]:
        raise ValueError(asset["inspection"]["error"])
    graph = carbon_gr2.read_gr2(asset["local"])
    raw = reader.read_raw(Path(asset["local"]).read_bytes()).file_info
    collection = bpy.context.scene.collection
    pairs = addon.import_meshes(
        graph, collection, "Scenery", 0.01, 0.0, False, 30.0, True, False, False
    )
    if not pairs or len(pairs) != len(graph["meshes"]):
        raise ValueError("GR2 contains unconverted meshes")
    materials = {}
    for obj, mesh_entry in pairs:
        original = raw["Meshes"][obj["gr2_mesh_index"]]
        all_refs = material_references(original)
        # Carbon compacts sparse material IDs into area_N topology groups.
        # Preserve that mapping instead of indexing the sparse binding list by slot.
        refs = [
            all_refs[int(group["name"].removeprefix("area_"))] for group in mesh_entry["indices"]
        ]
        if any(ref is None for ref in refs):
            raise ValueError("A rendered topology group has no diffuse material")
        obj.data.materials.clear()
        for ref in refs:
            if ref not in materials:
                mat = bpy.data.materials.new("SceneryMaterial")
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Roughness"].default_value = 0.9
                bsdf.inputs["Specular IOR Level"].default_value = 0.0
                if ref:
                    texture_id = asset["materials"][ref]
                    image = bpy.data.images.load(str(output / "textures" / f"{texture_id}.png"))
                    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    tex.image = image
                    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
                materials[ref] = mat
            obj.data.materials.append(materials[ref])
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ v.co for obj, _ in pairs for v in obj.data.vertices]
    if not all(all(abs(c) < 10000 for c in point) for point in points):
        raise ValueError("Nonfinite or implausible model bounds")
    return {
        "meshes": len(pairs),
        "vertices": len(points),
        "bounds_m": [
            [min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)],
        ],
        "embedded_animations_omitted": asset["inspection"]["animations"],
    }


def terrain(chunk, scale, output):
    from mathutils import Vector
    from metin_map_data import attributes, height_at, heights, water

    source = Path(chunk["source"])
    samples = heights((source / "height.raw").read_bytes())
    verts = [
        (x * 2, -y * 2, height_at(samples, x, y, scale)) for y in range(129) for x in range(129)
    ]
    faces = []
    for y in range(128):
        for x in range(128):
            i = y * 129 + x
            faces.extend([(i, i + 129, i + 1), (i + 1, i + 129, i + 130)])
    mesh = bpy.data.meshes.new("Terrain")
    mesh.from_pydata(verts, [], faces)
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        poly.use_smooth = True
        for loop in poly.loop_indices:
            index = mesh.loops[loop].vertex_index
            uv.data[loop].uv = (index % 129 / 128, 1 - index // 129 / 128)
    normals = []
    for y in range(129):
        for x in range(129):
            dx = height_at(samples, x + 1, y, scale) - height_at(samples, x - 1, y, scale)
            dy = height_at(samples, x, y + 1, scale) - height_at(samples, x, y - 1, scale)
            normals.append(Vector((-dx / 4, dy / 4, 1)).normalized())
    mesh.normals_split_custom_set_from_vertices(normals)
    obj = bpy.data.objects.new("Terrain", mesh)
    bpy.context.scene.collection.objects.link(obj)
    cells, levels = water((source / "water.wtr").read_bytes())
    water_verts, water_faces = [], []
    for index, layer in enumerate(cells):
        if layer == 255:
            continue
        x, y = index % 128, index // 128
        level = levels[layer] * scale
        if (
            min(
                height_at(samples, x + dx, y + dy, scale)
                for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1))
            )
            >= level
        ):
            continue
        start = len(water_verts)
        water_verts.extend(
            [
                (x * 2, -y * 2, level),
                (x * 2, -y * 2 - 2, level),
                (x * 2 + 2, -y * 2 - 2, level),
                (x * 2 + 2, -y * 2, level),
            ]
        )
        water_faces.append(tuple(start + i for i in range(4)))
    if water_faces:
        water_mesh = bpy.data.meshes.new("Water")
        water_mesh.from_pydata(water_verts, [], water_faces)
        obj = bpy.data.objects.new("Water", water_mesh)
        bpy.context.scene.collection.objects.link(obj)
    data_png((source / "tile.raw").read_bytes(), 258, output / f"{chunk['id']}-tiles.png")
    data_png(
        attributes((source / "attr.atr").read_bytes()),
        256,
        output / f"{chunk['id']}-attributes.png",
    )
    return {"vertices": len(verts), "triangles": len(faces), "water_cells": len(water_faces)}


def convert(manifest):
    output = Path(manifest["output"])
    for directory in ("models", "textures", "terrain"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    report = {"blender": bpy.app.version_string, "assets": {}, "terrain": {}}
    for key, texture in manifest["model_textures"].items():
        png(texture["local"], output / "textures" / f"{key}.png")
    for texture in manifest["textures"]:
        png(texture["local"], output / "textures" / f"terrain-{texture['id']:02}.png")
    terrain_array(manifest["textures"], output / "textures")
    for key, asset in manifest["assets"].items():
        empty_scene()
        try:
            result = convert_model(asset, output)
            export_glb(output / "models" / f"{key}.glb")
            report["assets"][key] = {"status": "converted", **result}
        except Exception as error:
            report["assets"][key] = {
                "status": "failed",
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
    for chunk in manifest["chunks"]:
        empty_scene()
        report["terrain"][chunk["id"]] = terrain(
            chunk, manifest["settings"]["height_scale"], output / "terrain"
        )
        export_glb(output / "terrain" / f"{chunk['id']}.glb")
    return report


def main():
    if not bpy.app.background:
        raise RuntimeError("Run this converter in a separate background Blender process")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stage", choices=("inspect", "convert"), required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    manifest = json.loads(args.manifest.read_text())
    root = Path(__file__).resolve().parents[1]
    bootstrap(root, manifest["carbon_commit"])
    from metin_archive import write_json

    target = args.manifest.parent / (
        "inspection.json" if args.stage == "inspect" else "conversion.json"
    )
    fingerprint = hashlib.sha256(
        args.manifest.read_bytes()
        + Path(__file__).read_bytes()
        + (root / "tools/metin_map_data.py").read_bytes()
    ).hexdigest()
    cache = target.with_suffix(".cache.json")
    if cache.exists() and target.exists():
        previous = json.loads(cache.read_text())
        if previous["fingerprint"] == fingerprint and all(
            Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
            for p, sha in previous["outputs"].items()
        ):
            print(f"Reused verified {args.stage} output")
            return
    result = inspect_assets(manifest) if args.stage == "inspect" else convert(manifest)
    write_json(target, result)
    outputs = {str(target): hashlib.sha256(target.read_bytes()).hexdigest()}
    if args.stage == "convert":
        for path in Path(manifest["output"]).rglob("*"):
            if path.suffix in (".glb", ".png"):
                outputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(cache, {"fingerprint": fingerprint, "outputs": outputs})


if __name__ == "__main__":
    main()
