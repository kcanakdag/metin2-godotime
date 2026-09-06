"""Original outdoor-map parsers and coordinate conversion, independent of Blender."""

import math
import re
import struct


def lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def numbers(text, count):
    values = [float(n) for n in text.split()]
    if len(values) != count or not all(math.isfinite(n) for n in values):
        raise ValueError(f"Expected {count} finite numbers: {text!r}")
    return values


def settings(text):
    data = dict(line.split(maxsplit=1) for line in lines(text))
    if data["ScriptType"] != "MapSetting" or float(data["CellScale"]) != 200:
        raise ValueError("Only the verified 200 cm outdoor cell format is supported")
    size = numbers(data["MapSize"], 2)
    if any(int(n) != n or not 1 <= n <= 64 for n in size):
        raise ValueError("Invalid map dimensions")
    scale = numbers(data["HeightScale"], 1)[0]
    if not 0 < scale <= 100:
        raise ValueError("Invalid height scale")
    return {
        "size": [int(n) for n in size],
        "height_scale": scale,
        "base_position_cm": numbers(data["BasePosition"], 2),
        "texture_set": data["TextureSet"],
        "environment": data["Environment"],
        "cell_m": 2.0,
        "chunk_m": 256.0,
    }


def blocks(text, kind):
    pattern = rf"Start {kind}(\d+)\s*\n(.*?)\n\s*End {kind}(?:\d+)?"
    return [(int(i), lines(body)) for i, body in re.findall(pattern, text, re.S)]


def placements(text):
    records = []
    for index, body in blocks(text, "Object"):
        if len(body) < 3:
            raise ValueError(f"Truncated object {index}")
        position = numbers(body[0], 3)
        crc = int(body[1])
        if not 0 <= crc <= 0xFFFFFFFF:
            raise ValueError("Property CRC outside uint32")
        rotation = numbers(body[2].replace("#", " "), 3 if "#" in body[2] else 1)
        if len(rotation) == 1:
            rotation = [0.0, 0.0, rotation[0]]
        bias = numbers(body[3], 1)[0] if len(body) > 3 else 0.0
        records.append(
            {
                "id": index,
                "crc": str(crc),
                "source_position": position,
                "rotation_ypr_deg": rotation,
                "height_bias_cm": bias,
                "position": to_godot(position, bias),
                "extra": body[4:],
            }
        )
    count = re.search(r"^ObjectCount\s+(\d+)\s*$", text, re.M)
    if not count or int(count[1]) != len(records):
        raise ValueError("Placement count does not match ObjectCount")
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate placement IDs")
    return records


def to_godot(position, bias=0.0):
    x, y, z = position
    return [x * 0.01, (z + bias) * 0.01, -y * 0.01]


def property_data(text):
    content = lines(text)
    if content[0] != "YPRT":
        raise ValueError("Unsupported property signature")
    crc = int(content[1])
    if not 0 <= crc <= 0xFFFFFFFF:
        raise ValueError("Invalid property CRC")
    fields = {}
    for line in content[2:]:
        key, value = line.split(maxsplit=1)
        fields[key.lower()] = value.strip('"')
    return str(crc), fields


def texture_set(text):
    result = []
    for index, body in blocks(text, "Texture"):
        if len(body) != 8:
            raise ValueError(f"Unexpected texture record {index}")
        result.append(
            {
                "id": index,
                "path": body[0].strip('"'),
                "uv": numbers(" ".join(body[1:5]), 4),
                "splat": int(body[5]),
                "height_range": [int(n) for n in body[6:]],
            }
        )
    count = re.search(r"^TextureCount\s+(\d+)\s*$", text, re.M)
    if not count or int(count[1]) != len(result):
        raise ValueError("Texture count mismatch")
    if [r["id"] for r in result] != list(range(1, len(result) + 1)):
        raise ValueError("Texture IDs must be contiguous and start at 1")
    return result


def heights(data):
    if len(data) != 131 * 131 * 2:
        raise ValueError("Expected 131 x 131 little-endian uint16 height samples")
    return struct.unpack("<17161H", data)


def height_at(samples, x, y, scale):
    # The 129 x 129 visible vertices start one sample inside the 131 x 131 halo.
    return samples[(y + 1) * 131 + x + 1] * scale * 0.01


def attributes(data):
    if len(data) != 65542 or struct.unpack_from("<3H", data) != (2634, 256, 256):
        raise ValueError("Invalid terrain attribute header or dimensions")
    return data[6:]


def water(data):
    if len(data) < 16391:
        raise ValueError("Truncated water map")
    magic, width, height, count = struct.unpack_from("<3HB", data)
    if (magic, width, height) != (5426, 128, 128):
        raise ValueError("Invalid water header")
    remainder = len(data) - 16391
    if remainder == count * 4:
        levels = struct.unpack_from(f"<{count}i", data, 16391)
    elif remainder == count * 2:
        levels = struct.unpack_from(f"<{count}H", data, 16391)
    else:
        raise ValueError("Invalid water level table")
    cells = data[7:16391]
    if any(n != 255 and n >= count for n in cells):
        raise ValueError("Water cell references a missing level")
    return cells, [n * 0.01 for n in levels]


def seam_errors(chunks, scale):
    errors = []
    for (x, y), samples in sorted(chunks.items()):
        for neighbor, horizontal in (((x + 1, y), True), ((x, y + 1), False)):
            if neighbor not in chunks:
                continue
            other = chunks[neighbor]
            for i in range(129):
                a = height_at(samples, 128 if horizontal else i, i if horizontal else 128, scale)
                b = height_at(other, 0 if horizontal else i, i if horizontal else 0, scale)
                if abs(a - b) > 0.00001:
                    errors.append(
                        {
                            "chunk": [x, y],
                            "neighbor": list(neighbor),
                            "vertex": i,
                            "delta_m": abs(a - b),
                        }
                    )
    return errors
