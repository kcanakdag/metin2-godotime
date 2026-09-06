"""Run in background Blender to bake shared terrain, collision and walkable surfaces.

blender --background --factory-startup --python tools/bake_yongan.py
"""

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def validate_manifest(manifest):
    """Fail before writing data when the fixed MT2YON02 decoder would misread a map."""
    settings = manifest["settings"]
    if (
        manifest["map"] != "metin2_map_a1"
        or settings["size"] != [4, 5]
        or settings["height_scale"] != 0.5
        or settings["cell_m"] != 2.0
        or settings["chunk_m"] != 256.0
    ):
        raise ValueError("MT2YON02 requires Yongan, 4 x 5 chunks, 2 m cells and HeightScale 0.5")
    grids = [tuple(chunk["grid"]) for chunk in manifest["chunks"]]
    if len(grids) != 20 or set(grids) != {(x, z) for x in range(4) for z in range(5)}:
        raise ValueError("Yongan bake requires every chunk exactly once")
    if manifest["seam_mismatches"] != 0:
        raise ValueError("Cannot bake terrain with mismatched chunk seams")


def visible_water_cells(samples, cells, levels, scale):
    """Use the same terrain-corner visibility rule as the rendered water mesh."""
    from metin_map_data import height_at

    visible = bytearray(len(cells))
    for index, layer in enumerate(cells):
        if layer == 255:
            continue
        x, z = index % 128, index // 128
        level = levels[layer] * scale
        visible[index] = (
            min(
                height_at(samples, x + dx, z + dz, scale)
                for dx, dz in ((0, 0), (1, 0), (0, 1), (1, 1))
            )
            < level
        )
    return visible


def main():
    import metin_collision
    import metin_map_data
    from mathutils import Euler, Matrix, Quaternion, Vector

    manifest = json.loads((ROOT / ".local/map-import/metin2_map_a1/manifest.json").read_text())
    validate_manifest(manifest)
    source = ROOT / "assets/source/maps" / manifest["commit"]
    width, depth = [int(n * 256) for n in manifest["settings"]["size"]]
    hw, hd = width // 2 + 1, depth // 2 + 1
    heights = [0] * (hw * hd)
    attributes = bytearray(width * depth)
    buried_water_cells = 0
    for chunk in manifest["chunks"]:
        cx, cz = chunk["grid"]
        folder = Path(chunk["source"])
        raw = metin_map_data.heights((folder / "height.raw").read_bytes())
        attr = metin_map_data.attributes((folder / "attr.atr").read_bytes())
        water, levels = metin_map_data.water((folder / "water.wtr").read_bytes())
        wet = visible_water_cells(raw, water, levels, manifest["settings"]["height_scale"])
        buried_water_cells += sum(layer != 255 and not wet[i] for i, layer in enumerate(water))
        for z in range(129):
            for x in range(129):
                heights[(cz * 128 + z) * hw + cx * 128 + x] = raw[(z + 1) * 131 + x + 1]
        for z in range(256):
            for x in range(256):
                flags = attr[z * 256 + x] & 1
                if wet[(z // 2) * 128 + x // 2]:
                    flags |= 2
                attributes[(cz * 256 + z) * width + cx * 256 + x] = flags
    shapes = []
    floors = []
    used = {}
    conversion = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
    decoded = {}
    for crc, prop in manifest["properties"].items():
        if prop.get("attribute_source"):
            path = source / prop["attribute_source"]
            raw = path.read_bytes()
            decoded[crc] = metin_collision.decode(raw)
            used[prop["attribute_source"]] = hashlib.sha256(raw).hexdigest()
    for chunk in manifest["chunks"]:
        for record in chunk["objects"]:
            if record["crc"] not in decoded:
                continue
            yaw, pitch, roll = [math.radians(n) for n in record["rotation_ypr_deg"]]
            rotation = (
                Euler((0, yaw, 0)).to_matrix()
                @ Euler((pitch, 0, 0)).to_matrix()
                @ Euler((0, 0, roll)).to_matrix()
            )
            transform = conversion @ rotation
            origin = Vector(record["position"])

            def point(p, transform=transform, origin=origin):
                return transform @ Vector(p) * 0.01 + origin

            local_shapes, triangles = decoded[record["crc"]]
            for shape in local_shapes:
                center = point(shape["position"])
                if shape["kind"] == 0:
                    qx, qy, qz, qw = shape["quaternion"]
                    quat = Quaternion((qw, qx, qy, qz)).normalized()
                    sx, sy = [n / 2 for n in shape["size"]]
                    vertices = [
                        point(quat @ Vector((x, y, 0)) + Vector(shape["position"]))
                        for x, y in [(-sx, -sy), (sx, -sy), (sx, sy), (-sx, sy)]
                    ]
                    shapes.append(
                        [
                            0,
                            min(p.y for p in vertices),
                            max(p.y for p in vertices),
                            *[v for p in vertices for v in (p.x, p.z)],
                            0,
                            0,
                        ]
                    )
                else:
                    radius = shape["size"][0] * 0.01
                    low = center.y - radius if shape["kind"] == 2 else center.y
                    high = center.y + (radius if shape["kind"] == 2 else shape["size"][1] * 0.01)
                    shapes.append([1, low, high, center.x, center.z, 0, 0, 0, 0, 0, 0, radius, 0])
            for triangle in triangles:
                vertices = [point(p) for p in triangle]
                floors.append(
                    [
                        min(p.x for p in vertices),
                        max(p.x for p in vertices),
                        min(p.z for p in vertices),
                        max(p.z for p in vertices),
                        *[v for p in vertices for v in p],
                    ]
                )
    data = bytearray(b"MT2YON02")
    data.extend(struct.pack("<6I", hw, hd, width, depth, len(shapes), len(floors)))
    data.extend(struct.pack(f"<{len(heights)}H", *heights))
    data.extend(attributes)
    for shape in shapes:
        data.extend(struct.pack("<13f", *shape))
    for floor in floors:
        data.extend(struct.pack("<13f", *floor))
    output = ROOT / "server/content/yongan.bin"
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(data)
    client = ROOT / "client/assets/imported/maps/metin2_map_a1"
    content_hash = hashlib.sha256(data).hexdigest()
    (output.parent / "yongan.sha256").write_text(content_hash)
    (client / "collision.json").write_text(
        json.dumps({"shapes": shapes, "floors": floors, "content_sha256": content_hash})
    )
    report = {
        "version": 2,
        "commit": manifest["commit"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "height_vertices": [hw, hd],
        "attribute_cells": [width, depth],
        "shapes": len(shapes),
        "floor_triangles": len(floors),
        "buried_water_cells_2m_omitted": buried_water_cells,
        "source_sha256": used,
    }
    (output.parent / "yongan.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, indent=2))


if __name__ == "__main__":
    main()
