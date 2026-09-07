"""Typed static NPC records and selected original point-spawn metadata."""

from __future__ import annotations

import re

from content_formats import integer, virtual_path


def material_paths(raw: dict) -> list[str]:
    paths = set()
    for mesh in raw["Meshes"]:
        bindings = mesh.get("MaterialBindings", [])
        if not bindings:
            raise ValueError("NPC mesh has no material bindings")
        for binding in bindings:
            maps = binding["Material"].get("Maps", [])
            if len(maps) != 1 or maps[0]["Usage"] != "Diffuse Color":
                raise ValueError("NPC converter currently requires one diffuse map per material")
            paths.add(virtual_path(maps[0]["Map"]["Texture"]["FromFileName"]))
    if not 1 <= len(paths) <= 32:
        raise ValueError("NPC texture dependency count is outside the supported bound")
    return sorted(paths)


def point_spawns(text: str, vnum: int) -> list[dict]:
    """Keep source heading/randomness explicit; world X/Y metres become map X/Z."""
    result = []
    for number, original in enumerate(text.splitlines(), 1):
        line = original.split("//", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 11 or fields[-1] != str(vnum):
            # Other source spawn families are outside this explicitly selected NPC.
            if fields and fields[-1] == str(vnum):
                raise ValueError(f"spawn line {number}: expected eleven fields")
            continue
        kind, x, y, radius_x, radius_y, section, direction, interval, chance, count, _ = fields
        if kind != "m" or any(integer(n) != 0 for n in (radius_x, radius_y, section)):
            raise ValueError(
                f"spawn line {number}: only point NPC spawns in section zero supported"
            )
        if integer(chance, maximum=100) != 100 or integer(count) != 1:
            raise ValueError(
                f"spawn line {number}: probabilistic or multiple NPC spawn unsupported"
            )
        match = re.fullmatch(r"([0-9]+)([hms])", interval)
        if not match:
            raise ValueError(f"spawn line {number}: unsupported regeneration interval")
        seconds = (
            integer(match[1], minimum=1, maximum=86400) * {"h": 3600, "m": 60, "s": 1}[match[2]]
        )
        if seconds > 86400:
            raise ValueError(f"spawn line {number}: regeneration interval exceeds one day")
        heading = integer(direction, maximum=8)
        result.append(
            {
                "source_line": number,
                "x_m": integer(x),
                "z_m": integer(y),
                "height_policy": "authoritative-terrain",
                "source_direction": heading,
                "heading_policy": "random-octant" if heading == 0 else "fixed-source-octant",
                "source_heading_degrees": None if heading == 0 else (heading - 1) * 45,
                "respawn_interval_us": seconds * 1_000_000,
            }
        )
    if not result:
        raise ValueError(f"No point spawn found for NPC {vnum}")
    return result


def motion_groups(rows: list[dict]) -> list[dict]:
    """Normalize idle variants while retaining every declared NPC motion/weight."""
    supported = {"wait": "wait", "wait1": "wait", "walk": "walk", "run": "run", "dead": "dead"}
    groups: dict[str, dict] = {}
    paths = set()
    for row in rows:
        action = supported.get(row["action"])
        if row["mode"] != "general" or action is None or row["path"] in paths:
            raise ValueError("Unsupported or duplicate static NPC motion")
        paths.add(row["path"])
        group = groups.setdefault(
            action, {"action": action, "files": [], "weights": [], "loop": action != "dead"}
        )
        group["files"].append(row["path"])
        group["weights"].append(row["weight"])
    if "wait" not in groups or any(sum(row["weights"]) != 100 for row in groups.values()):
        raise ValueError("NPC requires idle motion and normalized variant weights")
    return [groups[key] for key in sorted(groups)]
