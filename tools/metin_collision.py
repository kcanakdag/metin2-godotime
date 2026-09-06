"""Decode the pinned AttributeData binary format; no reference implementation code copied."""

import math
import struct


def decode(data):
    if data[:14] != b"AttributeData\0":
        raise ValueError("Invalid AttributeData signature")
    if len(data) < 22:
        raise ValueError("Truncated AttributeData header")
    count, height_count = struct.unpack_from("<II", data, 14)
    if count > 10000 or height_count > 10000:
        raise ValueError("Unreasonable attribute counts")
    offset = 22

    def read(format_string):
        nonlocal offset
        size = struct.calcsize("<" + format_string)
        if offset + size > len(data):
            raise ValueError(f"Truncated AttributeData record at byte {offset}")
        values = struct.unpack_from("<" + format_string, data, offset)
        offset += size
        return values

    shapes = []
    for _ in range(count):
        (kind,) = read("I")
        if kind not in {0, 2, 3}:
            raise ValueError(f"Collision kind {kind} is outside the verified fixture")
        (name,) = read("32s")
        position = read("3f")
        size = read("f" if kind == 2 else "2f")
        quaternion = read("4f")
        if not all(math.isfinite(v) for v in (*position, *size, *quaternion)):
            raise ValueError("Nonfinite collision data")
        if any(v <= 0 for v in size):
            raise ValueError("Collision dimensions must be positive")
        if kind == 0 and not 0.999 <= sum(v * v for v in quaternion) <= 1.001:
            raise ValueError("Plane collision quaternion must be normalized")
        shapes.append(
            {
                "kind": kind,
                "name": name.rstrip(b"\0").decode("latin1"),
                "position": position,
                "size": size,
                "quaternion": quaternion,
            }
        )
    surfaces = []
    for _ in range(height_count):
        read("32s")
        (count,) = read("I")
        if count > 1000000 or count % 3:
            raise ValueError("Invalid triangle-list height data")
        if count * 12 > len(data) - offset:
            raise ValueError("Truncated height triangle list")
        vertices = [read("3f") for _ in range(count)]
        if not all(math.isfinite(v) for point in vertices for v in point):
            raise ValueError("Nonfinite surface data")
        surfaces.extend(vertices[i : i + 3] for i in range(0, count, 3))
    if offset != len(data):
        raise ValueError("Unexpected trailing attribute bytes")
    return shapes, surfaces
