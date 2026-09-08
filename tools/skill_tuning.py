"""Apply reviewed skill tuning without changing pinned source archives or mechanics."""

from __future__ import annotations

from copy import deepcopy

from skill_formulas import compile_formula

FORMULAS = {
    "formula",
    "sp_cost",
    "duration",
    "sp_upkeep",
    "cooldown",
    "secondary_formula",
    "secondary_duration",
    "splash_scale",
}
INTEGERS = {"max_targets": (1, 32), "target_range_cm": (0, 2500), "splash_radius_cm": (0, 1000)}
TEXT = {"name": 80, "description": 1024}


def apply_tuning(inventory: dict, profile: dict) -> dict:
    if set(profile) != {"schema_version", "overrides"} or profile["schema_version"] != 1:
        raise ValueError("Unsupported skill tuning schema")
    rows = profile["overrides"]
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError("Skill tuning overrides must be a bounded list")
    result = deepcopy(inventory)
    skills = {skill["vnum"]: skill for skill in result["skills"]}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"vnum", "values"}:
            raise ValueError("A skill override needs exactly vnum and values")
        vnum, values = row["vnum"], row["values"]
        if type(vnum) is not int or vnum not in skills or vnum in seen:
            raise ValueError("Skill tuning references an unknown or duplicate ability")
        seen.add(vnum)
        if (
            not isinstance(values, dict)
            or not values
            or values.keys() - (FORMULAS | INTEGERS.keys() | TEXT.keys())
        ):
            raise ValueError(
                "Unsupported skill tuning field; new mechanics require a shared handler"
            )
        for key, value in values.items():
            if key in FORMULAS:
                skills[vnum]["programs"][key] = compile_formula(value)
            elif key in INTEGERS:
                low, high = INTEGERS[key]
                if type(value) is not int or not low <= value <= high:
                    raise ValueError("Skill tuning integer exceeds supported bounds")
            elif (
                not isinstance(value, str)
                or not value
                or len(value) > TEXT[key]
                or any(ord(c) < 32 and c != "\n" for c in value)
            ):
                raise ValueError("Invalid skill tuning text")
            skills[vnum][key] = value
    result["tuning"] = deepcopy(profile)
    return result
