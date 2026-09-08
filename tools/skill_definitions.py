"""Read classic class skills as pinned data; never execute the legacy client."""

from __future__ import annotations

import re

from character_definitions import function_body

CLASSES = ("Warrior", "Assassin", "Sura", "Shaman")
CLASS_NAMES = ("warrior", "ninja", "sura", "shaman")
GROUP_NAMES = (
    ("Body", "Mental"),
    ("Blade", "Archery"),
    ("Weaponry", "Black Magic"),
    ("Dragon", "Healing"),
)

# The pinned registration names have no matching MSA in either Shaman pack.
# These explicit self-cast files exist for both appearances; targeted variants
# are separate source motions and must not silently replace these registrations.
SELF_CAST_MOTIONS = {
    94: "hosin",
    95: "boho",
    96: "gicheon",
    109: "jeongeop",
    110: "kwaesok",
}


def classic_skill_ids(class_id: int) -> list[int]:
    if type(class_id) is not int or class_id not in range(4):
        raise ValueError("Unknown classic class")
    count = 5 if class_id < 2 else 6
    return [class_id * 30 + group * 15 + slot for group in range(2) for slot in range(1, count + 1)]


def registered_skills(settings: str, class_id: int) -> dict[int, str]:
    """Match only literal normal-grade registrations within the selected class."""
    expected = classic_skill_ids(class_id)
    body = function_body(settings, f"__LoadGame{CLASSES[class_id]}Ex")
    body = re.sub(r"#[^\n]*", "", body)
    matches = re.findall(
        r"chrmgr\.RegisterCacheMotionData\(chr\.MOTION_MODE_GENERAL,\s*"
        r"chr\.MOTION_SKILL\+\(i\*skill\.SKILL_GRADEGAP\)\+(\d+),\s*"
        r'"([a-z0-9_]+)"\s*\+\s*END_STRING\s*\+\s*"\.msa"\)',
        body,
    )
    result = {}
    for offset, stem in matches:
        vnum = class_id * 30 + int(offset)
        if vnum not in expected:
            continue  # Locale-specific sixth Warrior/Ninja skills are not in this classic set.
        if vnum in result:
            raise ValueError("Ambiguous skill motion registration")
        result[vnum] = f"skill/{stem}.msa"
    if set(result) != set(expected):
        raise ValueError("Incomplete classic skill motion registrations")
    return result


def source_rows(text: str) -> dict[int, list[str]]:
    rows = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if not fields[0].isdigit():
            continue
        vnum = int(fields[0])
        if vnum in rows:
            raise ValueError("Duplicate source skill row")
        rows[vnum] = fields
    return rows


def discover_skills(settings: str, table: str, descriptions: str) -> list[dict]:
    """Describe complete classic coverage independently of implemented runtime handlers."""
    rows, descs = source_rows(table), source_rows(descriptions)
    result = []
    for class_id, name in enumerate(CLASS_NAMES):
        motions = registered_skills(settings, class_id)
        for vnum in classic_skill_ids(class_id):
            row, desc = rows.get(vnum, []), descs.get(vnum, [])
            if len(row) != 27 or len(desc) < 13 or int(row[2]) != class_id + 1:
                raise ValueError(f"Missing or incompatible skill source row {vnum}")
            if not re.fullmatch(r"[a-z0-9_]+", desc[12]):
                raise ValueError("Unsafe skill icon stem")
            flags = [flag for flag in row[14].split(",") if flag and flag != "0"]
            group = 1 if (vnum - class_id * 30) < 15 else 2
            motion_file = motions[vnum]
            if vnum in SELF_CAST_MOTIONS:
                stem = SELF_CAST_MOTIONS[vnum]
                if motion_file != f"skill/{stem}.msa":
                    raise ValueError(
                        "Shaman motion repair no longer matches the pinned registration"
                    )
                motion_file = f"skill/{stem}_me.msa"
            result.append(
                {
                    "vnum": vnum,
                    "class_id": class_id,
                    "class": name,
                    "group": group,
                    "group_name": GROUP_NAMES[class_id][group - 1],
                    "name": desc[2].strip(),
                    "description": desc[5].strip(),
                    "motion": f"skill_{vnum}",
                    "registered_motion_file": motions[vnum],
                    "motion_file": motion_file,
                    "icon": f"skill/{name if name != 'ninja' else 'assassin'}/{desc[12]}_01",
                    "point": row[6],
                    "formula": row[7],
                    "sp_cost": row[8],
                    "duration": row[9],
                    "sp_upkeep": row[10],
                    "cooldown": row[11],
                    "flags": flags,
                    "client_flags": [flag for flag in desc[10].split("|") if flag],
                    "weapon_limits": [weapon for weapon in desc[11].split("|") if weapon],
                    "affect": row[15],
                    "secondary_point": row[16],
                    "secondary_formula": row[17],
                    "secondary_duration": row[18],
                    "secondary_affect": row[19],
                    "attribute": row[22],
                    "max_targets": int(row[23]),
                    "splash_scale": row[24],
                    "target_range_cm": int(row[25]),
                    "splash_radius_cm": int(row[26]),
                    "requirements": [
                        "damage"
                        if "ATTACK" in flags
                        else ("healing" if row[6] == "HP" else "buff"),
                        *flags,
                    ],
                }
            )
    return result
