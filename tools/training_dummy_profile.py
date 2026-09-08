"""Validate authored training-target data before starting an asset build."""

import math
import re
import unicodedata

INTEGER_BOUNDS = {
    "schema_version": (1, 1),
    "vnum": (900_000, 999_999),
    "health": (1, 65_535),
    "level": (1, 99),
    "vitality": (0, 90),
    "dexterity": (0, 90),
    "defense": (0, 10_000),
    "sword_resistance_percent": (0, 100),
    "fan_resistance_percent": (0, 100),
    "respawn_ms": (100, 60_000),
}
DIMENSION_BOUNDS = {
    "hit_radius_m": (0.01, 4.0),
    "hit_center_y_m": (0.01, 4.0),
    "height_m": (0.5, 3.5),
    "body_radius_m": (0.1, 0.8),
}


def finite(value, low, high, field):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{field} must be a finite number in [{low}, {high}]")


def validate_profile(profile):
    fields = set(INTEGER_BOUNDS) | set(DIMENSION_BOUNDS) | {"id", "name", "colors", "placements"}
    if not isinstance(profile, dict) or set(profile) != fields:
        raise ValueError("Training profile must contain exactly the documented fields")
    for field, (low, high) in INTEGER_BOUNDS.items():
        value = profile[field]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{field} must be an integer in [{low}, {high}]")
    actor = profile["id"]
    if (
        not isinstance(actor, str)
        or len(actor) > 100
        or not re.fullmatch(r"actor\.training\.[a-z0-9.-]+", actor)
    ):
        raise ValueError("Invalid training actor ID")
    name = profile["name"]
    if (
        not isinstance(name, str)
        or not 1 <= len(name.encode("utf-8")) <= 64
        or any(unicodedata.category(char) == "Cc" for char in name)
    ):
        raise ValueError("Training name must be 1–64 UTF-8 bytes without control characters")
    for field, (low, high) in DIMENSION_BOUNDS.items():
        finite(profile[field], low, high, field)
    colors = profile["colors"]
    if not isinstance(colors, dict) or set(colors) != {"wood", "straw", "rope", "target"}:
        raise ValueError("Training colors must define wood, straw, rope and target")
    for material, color in colors.items():
        if not isinstance(color, list) or len(color) != 4:
            raise ValueError(f"{material} must contain four RGBA channels")
        for channel in color:
            finite(channel, 0, 1, f"{material} color channel")
    placements = profile["placements"]
    if not isinstance(placements, list) or not 1 <= len(placements) <= 32:
        raise ValueError("Training profile requires 1–32 placements")
    ids = set()
    for row in placements:
        if not isinstance(row, dict) or set(row) != {"id", "map_id", "home_x", "home_z"}:
            raise ValueError("Invalid training placement fields")
        if row["map_id"] not in ("training", "metin2_map_a1"):
            raise ValueError("Unsupported training target map")
        if type(row["id"]) is not int or not 900_000 <= row["id"] <= 999_999:
            raise ValueError("Training placement ID must be an integer in [900000, 999999]")
        key = (row["map_id"], row["id"])
        if key in ids:
            raise ValueError("Duplicate training target placement")
        ids.add(key)
        for coordinate in ("home_x", "home_z"):
            finite(row[coordinate], -1024, 1024, coordinate)
