"""Typed original monster records, independent of placement and runtime support."""

import csv
import io
import math
import re


def integer(row, key, low=0, high=2**32 - 1):
    text = row.get(key, "")
    if not isinstance(text, str) or not re.fullmatch(r"-?[0-9]+", text):
        raise ValueError(f"Invalid monster integer {key}")
    value = int(text)
    if not low <= value <= high:
        raise ValueError(f"Monster {key} exceeds [{low}, {high}]")
    return value


def records(text):
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Missing or duplicate monster table columns")
    result = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed monster table row")
        vnum = integer(row, "VNUM", 1)
        if vnum in result:
            raise ValueError(f"Duplicate monster vnum {vnum}")
        result[vnum] = row
    return result


def normalize(row, *, actor_id, name, model_key):
    if not re.fullmatch(r"actor\.mob\.[a-z0-9.-]+", actor_id):
        raise ValueError("Invalid monster actor ID")
    if row.get("TYPE") != "MONSTER":
        raise ValueError("Selected record is not an original monster")
    if not name or any(ord(c) < 32 for c in name) or len(name.encode()) > 160:
        raise ValueError("Invalid monster name")
    if not re.fullmatch(r"[a-z0-9_]+", model_key):
        raise ValueError("Unsupported monster model registration")
    stats = {
        key.lower(): integer(row, key, low, high)
        for key, low, high in (
            ("LEVEL", 1, 255),
            ("ST", 0, 255),
            ("DX", 0, 255),
            ("HT", 0, 255),
            ("IQ", 0, 255),
            ("DAMAGE_MIN", 0, 65535),
            ("DAMAGE_MAX", 0, 65535),
            ("MAX_HP", 1, 2**32 - 1),
            ("DEF", 0, 65535),
            ("ATTACK_SPEED", 1, 1000),
            ("MOVE_SPEED", 1, 1000),
            ("ATTACK_RANGE", 0, 10000),
            ("AGGRESSIVE_SIGHT", 0, 100000),
            ("AGGRESSIVE_HP_PCT", 0, 100),
            ("REGEN_CYCLE", 0, 65535),
            ("REGEN_PERCENT", 0, 100),
        )
    }
    if stats["damage_min"] > stats["damage_max"]:
        raise ValueError("Monster damage bounds are reversed")
    multiplier = float(row["DAM_MULTIPLY"])
    if not math.isfinite(multiplier) or not 0 < multiplier <= 100:
        raise ValueError("Invalid monster damage multiplier")
    stats["damage_multiplier"] = multiplier
    rewards = {
        key.lower(): integer(row, key) for key in ("EXP", "GOLD_MIN", "GOLD_MAX", "DROP_ITEM")
    }
    if rewards["gold_min"] > rewards["gold_max"]:
        raise ValueError("Monster gold bounds are reversed")
    flags = {}
    for key in ("AI_FLAG", "RACE_FLAG", "IMMUNE_FLAG"):
        values = row[key].split(",") if row[key] else []
        if len(set(values)) != len(values) or any(not re.fullmatch(r"[A-Z_]+", v) for v in values):
            raise ValueError(f"Malformed monster {key}")
        flags[key.lower()] = values
    # Preserve all source resistance/enchantment columns; never silently make an
    # unsupported damage type physical or erase a status mechanic.
    combat_modifiers = {
        key.lower(): integer(row, key, -100, 100)
        for key in row
        if key.startswith(("RESIST_", "ENCHANT_"))
    }
    return {
        "id": actor_id,
        "vnum": integer(row, "VNUM", 1),
        "name": name,
        "model_key": model_key,
        "source_folder": row["FOLDER"],
        "rank": row["RANK"],
        "battle_type": row["BATTLE_TYPE"],
        "size": row["SIZE"],
        "stats": stats,
        "rewards": rewards,
        "flags": flags,
        "combat_modifiers": combat_modifiers,
        "special_mechanics": {
            key.lower(): None if key.startswith("SKILL_") and row[key] == "" else integer(row, key)
            for key in row
            if key.startswith(("SKILL_", "SP_"))
            or key in ("SUMMON", "DRAIN_SP", "RESURRECTION_VNUM", "POLYMORPH_ITEM", "MOB_COLOR")
        },
    }
