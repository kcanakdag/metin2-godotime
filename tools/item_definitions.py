"""Typed item records compiled from explicitly selected, hash-checked proto rows.

The source adapter selects shared mechanics, never executable scripts. Registry
validation is independent of the selected vnums so new rows reuse the handlers.
"""

from __future__ import annotations

import re

SCHEMA_VERSION = 3
RECOVERY_POLICY = {
    "id": "item.recovery.pool.v1",
    "interval_us": 1_000_000,
    "maximum_percent_per_tick": 7,
    "potion_bonus_percent": 0,
    "offline_policy": "discard-on-leave",
    "late_tick_policy": "one-step-no-catchup",
}
FIELDS = {
    "id",
    "revision",
    "vnum",
    "name",
    "icon",
    "height",
    "stack_limit",
    "minimum_level",
    "allowed_classes",
    "allowed_sexes",
    "attack_speed_bonus",
    "kind",
    "weapon",
    "recovery",
    "armor",
    "source",
}

ARMOR_CATEGORIES = {
    "ARMOR_BODY": "body",
    "ARMOR_WRIST": "wrist",
    "ARMOR_NECK": "neck",
    "ARMOR_EAR": "ear",
    "ARMOR_HEAD": "head",
    "ARMOR_FOOT": "foot",
    "ARMOR_HAND": "hand",
    "ARMOR_SHIELD": "shield",
}
ARMOR_POSITIONS = {
    "WEAR_BODY": "body",
    "WEAR_WRIST": "wrist",
    "WEAR_NECK": "neck",
    "WEAR_EAR": "ear",
    "WEAR_HEAD": "head",
    "WEAR_FOOT": "foot",
    "WEAR_HAND": "hand",
    "WEAR_SHIELD": "shield",
}


def integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def _object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} has missing or unsupported fields")
    return value


def validate_catalog(catalog: object) -> None:
    catalog = _object(catalog, {"schema_version", "recovery_policy", "items"}, "item catalog")
    integer(catalog["schema_version"], "item catalog schema", SCHEMA_VERSION, SCHEMA_VERSION)
    policy = _object(catalog["recovery_policy"], set(RECOVERY_POLICY), "recovery policy")
    if any(type(policy[k]) is not type(v) or policy[k] != v for k, v in RECOVERY_POLICY.items()):
        raise ValueError("Unsupported recovery policy")
    items = catalog["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 65535:
        raise ValueError("Item catalog must contain 1..65535 records")
    ids, vnums = set(), set()
    previous_vnum = 0
    for item in items:
        item = _object(item, FIELDS, "item definition")
        content_id = item["id"]
        if not isinstance(content_id, str) or not re.fullmatch(
            r"item\.[a-z0-9][a-z0-9._-]{0,119}", content_id
        ):
            raise ValueError("Item ID must be a stable namespaced identifier")
        vnum = integer(item["vnum"], content_id + " vnum", 1, 2**32 - 1)
        if content_id in ids or vnum in vnums or vnum <= previous_vnum:
            raise ValueError("Item IDs/vnums must be unique and rows sorted by vnum")
        ids.add(content_id)
        vnums.add(vnum)
        previous_vnum = vnum
        integer(item["revision"], content_id + " revision", 1, 65535)
        integer(item["attack_speed_bonus"], content_id + " attack speed", 0, 1000)
        integer(item["height"], content_id + " height", 1, 9)
        integer(item["stack_limit"], content_id + " stack", 1, 200)
        integer(item["minimum_level"], content_id + " level", 0, 255)
        integer(item["allowed_classes"], content_id + " class mask", 1, 15)
        integer(item["allowed_sexes"], content_id + " sex mask", 1, 3)
        if (
            not isinstance(item["name"], str)
            or not 1 <= len(item["name"]) <= 80
            or any(ord(c) < 32 for c in item["name"])
        ):
            raise ValueError("Invalid item display name")
        if not isinstance(item["icon"], str) or not re.fullmatch(
            r"icon/item/[0-9]{5,10}", item["icon"]
        ):
            raise ValueError("Invalid item icon reference")
        source = _object(
            item["source"], {"path", "revision", "git_sha", "sha256", "row_number"}, "item source"
        )
        if source["path"] != "gamefiles/conf/item_proto.txt":
            raise ValueError("Unsupported item source path")
        for key, length in (("revision", 40), ("git_sha", 40), ("sha256", 64)):
            if not isinstance(source[key], str) or not re.fullmatch(
                r"[0-9a-f]{%d}" % length, source[key]
            ):
                raise ValueError("Invalid item source identity")
        integer(source["row_number"], "item source row", 2, 2**32 - 1)
        if item["kind"] == "weapon":
            weapon = _object(
                item["weapon"], {"class", "power_min", "power_max", "refine_attack"}, "item weapon"
            )
            if (
                weapon["class"] not in {"sword", "fan"}
                or item["recovery"] is not None
                or item["stack_limit"] != 1
            ):
                raise ValueError("Unsupported weapon mechanic or stack")
            for key in ("power_min", "power_max", "refine_attack"):
                integer(weapon[key], "weapon " + key, 0, 65535)
            if (
                weapon["power_min"] > weapon["power_max"]
                or weapon["power_max"] + weapon["refine_attack"] > 65535
            ):
                raise ValueError("Invalid weapon power range")
            if item["armor"] is not None:
                raise ValueError("Weapons must not declare armor fields")
        elif item["kind"] == "recovery":
            effect = _object(item["recovery"], {"handler", "hp", "sp"}, "item recovery")
            if (
                item["weapon"] is not None
                or item["armor"] is not None
                or effect["handler"] != RECOVERY_POLICY["id"]
            ):
                raise ValueError("Unsupported item recovery handler")
            for key in ("hp", "sp"):
                integer(effect[key], "recovery " + key, 0, 65535)
            if effect["hp"] + effect["sp"] == 0:
                raise ValueError("Recovery effect must restore HP or SP")
        elif item["kind"] == "armor":
            armor = _object(item["armor"], {"category", "position"}, "item armor")
            if (
                armor["category"] not in set(ARMOR_CATEGORIES.values())
                or armor["position"] not in set(ARMOR_POSITIONS.values())
                or item["weapon"] is not None
                or item["recovery"] is not None
            ):
                raise ValueError("Unsupported armor mechanic")
        elif item["kind"] == "narrative":
            if any(item[key] is not None for key in ("weapon", "recovery", "armor")):
                raise ValueError("Narrative items must not declare a mechanic")
        else:
            raise ValueError("Unsupported item kind")


def compile_catalog(selection: dict, proto_text: str, names_text: str, source: dict) -> dict:
    _object(selection, {"schema_version", "items"}, "item selection")
    integer(selection["schema_version"], "item selection schema", 1, 1)
    if not isinstance(selection["items"], list) or not selection["items"]:
        raise ValueError("An explicit item selection is required")
    rows: dict[int, list[tuple[int, list[str]]]] = {}
    for number, line in enumerate(proto_text.splitlines()[1:], 2):
        columns = line.split("\t")
        if columns and columns[0].isdecimal():
            rows.setdefault(int(columns[0]), []).append((number, columns))
    names: dict[int, list[str]] = {}
    for line in names_text.splitlines():
        fields = line.split("\t")
        if len(fields) == 2 and fields[0].isdecimal():
            names.setdefault(int(fields[0]), []).append(fields[1])
    compiled = []
    for selected in selection["items"]:
        _object(selected, {"id", "revision", "vnum", "icon"}, "selected item")
        vnum = integer(selected["vnum"], "selected vnum", 1, 2**32 - 1)
        matches = rows.get(vnum, [])
        if len(matches) != 1 or len(matches[0][1]) != 33 or len(names.get(vnum, [])) != 1:
            raise ValueError(f"Item {vnum} needs exactly one complete proto and name row")
        number, row = matches[0]
        flags = set(row[5].split(" | ")) - {"NONE"}
        class_flags = {"ANTI_MUSA": 0, "ANTI_ASSASSIN": 1, "ANTI_SURA": 2, "ANTI_MUDANG": 3}
        sex_flags = {"ANTI_MALE": 0, "ANTI_FEMALE": 1}
        if flags - class_flags.keys() - sex_flags.keys():
            raise ValueError(f"Item {vnum} has unsupported anti-flags: {sorted(flags)}")
        level = 0
        for limit_type, value in ((row[14], row[15]), (row[16], row[17])):
            if limit_type == "LEVEL":
                level = max(level, int(value))
            elif limit_type != "LIMIT_NONE" or int(value) != 0:
                raise ValueError(f"Item {vnum} has an unsupported limit")
        item = {
            **selected,
            "name": names[vnum][0].replace("(", " ("),
            "height": int(row[4]),
            "stack_limit": 200 if "ITEM_STACKABLE" in row[6].split(" | ") else 1,
            "minimum_level": level,
            "allowed_classes": 15
            - sum(1 << index for flag, index in class_flags.items() if flag in flags),
            "allowed_sexes": 3
            - sum(1 << index for flag, index in sex_flags.items() if flag in flags),
            "attack_speed_bonus": 0,
            "weapon": None,
            "recovery": None,
            "armor": None,
            "source": {**source, "row_number": number},
        }
        if (
            row[2] == "ITEM_WEAPON"
            and row[3] in {"WEAPON_SWORD", "WEAPON_FAN"}
            and row[7] == "WEAR_WEAPON"
        ):
            for apply_type, apply_value in zip(row[18:24:2], row[19:24:2], strict=True):
                if apply_type == "APPLY_ATT_SPEED":
                    item["attack_speed_bonus"] += int(apply_value)
                elif apply_type != "APPLY_NONE" or int(apply_value) != 0:
                    raise ValueError(f"Item {vnum} has an unsupported weapon apply")
            item["kind"] = "weapon"
            item["weapon"] = {
                "class": {"WEAPON_SWORD": "sword", "WEAPON_FAN": "fan"}[row[3]],
                "power_min": int(row[27]),
                "power_max": int(row[28]),
                "refine_attack": int(row[29]),
            }
        elif row[2:4] == ["ITEM_USE", "USE_POTION"] and row[7] == "NONE":
            if any(int(value) != 0 for value in row[26:30]):
                raise ValueError(f"Item {vnum} has unsupported potion values")
            item["kind"] = "recovery"
            item["recovery"] = {
                "handler": RECOVERY_POLICY["id"],
                "hp": int(row[24]),
                "sp": int(row[25]),
            }
        elif row[2] == "ITEM_ARMOR" and row[3] in ARMOR_CATEGORIES and row[7] in ARMOR_POSITIONS:
            applied = [
                (apply_type, int(apply_value))
                for apply_type, apply_value in zip(row[18:24:2], row[19:24:2], strict=True)
                if apply_type != "APPLY_NONE" or int(apply_value) != 0
            ]
            # The selected opening rewards carry small static bonuses. They are
            # preserved as provenance only until equipment stats are modelled.
            supported = {
                "APPLY_ATT_SPEED",
                "APPLY_MAX_STAMINA",
                "APPLY_CAST_SPEED",
                "APPLY_RESIST_FIRE",
                "APPLY_DEX",
            }
            if any(apply_type not in supported for apply_type, _ in applied):
                raise ValueError(f"Item {vnum} has an unsupported armor apply")
            item["kind"] = "armor"
            item["armor"] = {
                "category": ARMOR_CATEGORIES[row[3]],
                "position": ARMOR_POSITIONS[row[7]],
            }
        elif row[2] == "ITEM_NONE":
            # `ITEM_NONE` rows carry prose-only or unimplemented mechanics
            # (shield skills, refine data). Keeping the row preserves the name
            # and icon without claiming an executable effect.
            item["kind"] = "narrative"
        else:
            raise ValueError(f"Item {vnum} uses an unsupported type/subtype")
        compiled.append(item)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "recovery_policy": dict(RECOVERY_POLICY),
        "items": sorted(compiled, key=lambda item: item["vnum"]),
    }
    validate_catalog(catalog)
    return catalog


def public_catalog(catalog: dict) -> dict:
    validate_catalog(catalog)
    return {
        "schema_version": SCHEMA_VERSION,
        "items": [
            {key: value for key, value in item.items() if key != "source"}
            for item in catalog["items"]
        ],
    }
