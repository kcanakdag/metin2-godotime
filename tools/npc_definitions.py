"""Typed static NPC records and selected original point-spawn metadata."""

from __future__ import annotations

import re

from content_formats import integer, virtual_path


def race_paths(model_key: str, source_root: str) -> tuple[str, str]:
    root = virtual_path(source_root)
    if model_key.startswith("#"):
        registered = virtual_path(model_key[1:].rstrip("/"))
        if registered != root:
            raise ValueError("Explicit NPC registration differs from the selected source root")
        return root + "/shape.msm", root + "/motlist.txt"
    if not re.fullmatch(r"[a-z0-9_]+", model_key):
        raise ValueError("Invalid conventional NPC model key")
    return root + "/" + model_key + ".msm", root + "/motlist.txt"


def material_paths(raw: dict) -> list[str]:
    paths = set()
    for mesh in raw["Meshes"]:
        bindings = mesh.get("MaterialBindings", [])
        if not bindings:
            raise ValueError("NPC mesh has no material bindings")
        for binding in bindings:
            maps = binding["Material"].get("Maps", [])
            diffuse = [m for m in maps if m["Usage"] == "Diffuse Color"]
            opacity = [m for m in maps if m["Usage"] == "Opacity"]
            if len(diffuse) != 1 or len(opacity) > 1 or len(maps) != 1 + len(opacity):
                raise ValueError("NPC material requires diffuse and optional shared opacity")
            path = virtual_path(diffuse[0]["Map"]["Texture"]["FromFileName"])
            if opacity and virtual_path(opacity[0]["Map"]["Texture"]["FromFileName"]) != path:
                raise ValueError("Separate NPC opacity textures require another material handler")
            paths.add(path)
    if not 1 <= len(paths) <= 32:
        raise ValueError("NPC texture dependency count is outside the supported bound")
    return sorted(paths)


def material_bindings(raw: dict, model_directory: str) -> dict[str, str]:
    """Mirror CGrannyMaterial's model-local path for non-drive texture names."""
    material_paths(raw)  # Validate supported map kinds before resolving dependencies.
    result = {}
    for mesh in raw["Meshes"]:
        for binding in mesh["MaterialBindings"]:
            for entry in binding["Material"]["Maps"]:
                name = entry["Map"]["Texture"]["FromFileName"]
                reference = virtual_path(name)
                resolved = (
                    virtual_path(model_directory + "/" + reference)
                    if len(name) > 2 and name[1] != ":"
                    else reference
                )
                if reference in result and result[reference] != resolved:
                    raise ValueError("Ambiguous NPC material texture binding")
                result[reference] = resolved
    return result


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
    supported.update(
        {
            action: action
            for action in (
                "normal_attack",
                "front_damage",
                "front_damage1",
                "front_dead",
                "front_knockdown",
                "front_standup",
                "back_damage",
                "back_damage1",
                "back_knockdown",
                "back_standup",
                "back_dead",
            )
        }
    )
    supported["normal_attack1"] = "normal_attack"
    groups: dict[str, dict] = {}
    paths = set()
    for row in rows:
        action = supported.get(re.sub(r"[0-9]{1,2}$", "", row["action"]))
        if row["mode"] != "general" or action is None:
            raise ValueError("Unsupported or duplicate static NPC motion")
        group = groups.setdefault(
            action,
            {
                "action": action,
                "files": [],
                "weights": [],
                "loop": action in ("wait", "walk", "run"),
            },
        )
        # GetRandomMotionKey draws 0..99 and subtracts registration weights.
        # Registrations beyond the first 100 points are unreachable (Octavio
        # includes a repeated WAIT1; guardian damage variants also exceed 100).
        remaining = 100 - sum(group["weights"])
        if remaining == 0:
            continue
        if row["path"] in paths:
            raise ValueError("Duplicate reachable static NPC motion")
        paths.add(row["path"])
        group["files"].append(row["path"])
        group["weights"].append(min(row["weight"], remaining))
    if "wait" not in groups or any(sum(row["weights"]) != 100 for row in groups.values()):
        raise ValueError("NPC requires idle motion and normalized variant weights")
    return [groups[key] for key in sorted(groups)]
