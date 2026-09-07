"""Read selected classic player registrations as data; never execute source scripts."""

from __future__ import annotations

import re

ACTIONS = {
    "WAIT": "wait",
    "WALK": "walk",
    "RUN": "run",
    "DAMAGE": "front_damage",
    "DAMAGE_BACK": "back_damage",
    "DEAD": "death",
    "INTRO_WAIT": "wait",
    "INTRO_SELECTED": "selected",
    "INTRO_NOT_SELECTED": "not_selected",
    **{f"COMBO_ATTACK_{i}": f"combo_{i}" for i in range(1, 8)},
}


def function_body(text: str, name: str) -> str:
    match = re.search(
        r"^def " + re.escape(name) + r"\([^\n]*\):\s*\n(.*?)(?=^def |\Z)", text, re.M | re.S
    )
    if not match:
        raise ValueError(f"Missing player registration function {name}")
    return "\n".join(line.split("#", 1)[0] for line in match[1].splitlines())


def registered_motions(text: str, source_class: str) -> tuple[list[dict], dict]:
    """Select general, intro and first melee weapon modes from literal registrations."""
    body = function_body(text, f"__LoadGame{source_class}Ex")
    weapon = "FAN" if source_class == "Shaman" else "ONEHAND_SWORD"
    modes = {"GENERAL": "general", weapon: "fan" if weapon == "FAN" else "onehand"}
    declarations: dict[str, dict[str, dict]] = {mode: {} for mode in modes.values()}
    declarations["intro"] = {}

    def add(mode: str, motion: str, file: str, weight: int, folder: str) -> None:
        if motion not in ACTIONS:
            return
        action = ACTIONS[motion]
        if mode == "general" and motion == "COMBO_ATTACK_1":
            action = "normal_attack"
        group = declarations[mode].setdefault(
            action,
            {
                "action": action,
                "files": [],
                "weights": [],
                "loop": action in {"wait", "walk", "run"},
            },
        )
        relative = folder + file
        # Sura registers damage.msa twice with different weights. Preserve
        # registration order and relative weights instead of inventing a variant.
        group["files"].append(relative)
        group["weights"].append(weight)

    literal = re.compile(
        r"chrmgr\.RegisterCacheMotionData\(\s*(mode|chr\.MOTION_MODE_\w+)\s*,\s*"
        r'chr\.MOTION_(\w+)\s*,\s*"([\w.]+\.msa)"\s*(?:,\s*(\d+))?\s*\)'
    )
    for helper, mode, folder in [
        ("SetGeneralMotions", "general", "general/"),
        ("SetIntroMotions", "intro", "intro/"),
    ]:
        for match in literal.finditer(function_body(text, helper)):
            add(mode, match[2], match[3], int(match[4] or 100), folder)
    token = re.compile(
        r'SetGeneralMotions\(chr\.MOTION_MODE_GENERAL,\s*path\s*\+\s*"([\w/]+)"\)'
        r'|chrmgr\.SetPathName\(path\s*\+\s*"([\w/]+)"\)'
        r"|chrmgr\.(?:RegisterCacheMotionData|SetMotionRandomWeight)\([^\n]+\)"
    )
    folder = ""
    for match in token.finditer(body):
        if match[1] or match[2]:
            folder = match[1] or match[2]
            continue
        registration = literal.fullmatch(match[0])
        if registration:
            mode = modes.get(registration[1].removeprefix("chr.MOTION_MODE_"))
            if mode:
                add(mode, registration[2], registration[3], int(registration[4] or 100), folder)
            continue
        weight = re.fullmatch(
            r"chrmgr\.SetMotionRandomWeight\(chr\.MOTION_MODE_(\w+),\s*chr\.MOTION_(\w+),\s*(\d+),\s*(\d+)\)",
            match[0],
        )
        if weight and weight[1] in modes and weight[2] in ACTIONS:
            declarations[modes[weight[1]]][ACTIONS[weight[2]]]["weights"][int(weight[3])] = int(
                weight[4]
            )
    result = []
    for mode, groups in declarations.items():
        required = (
            {"wait", "walk", "run", "front_damage", "back_damage"}
            if mode != "intro"
            else {"wait", "selected", "not_selected"}
        )
        required |= {"normal_attack", "death"} if mode == "general" else set()
        required |= (
            {"combo_1", "combo_2", "combo_3", "combo_4"}
            if mode not in {"intro", "general"}
            else set()
        )
        if not required <= groups.keys() or any(
            not row["weights"] or any(not 0 < weight <= 100 for weight in row["weights"])
            for row in groups.values()
        ):
            raise ValueError(f"Incomplete motions or invalid weights for {source_class}/{mode}")
        if mode not in {"intro", "general"}:
            groups["death"] = {**declarations["general"]["death"], "fallback_mode": "general"}
        result.append({"id": mode, "motions": list(groups.values())})
    bones = dict(
        re.findall(
            r'chrmgr\.RegisterAttachingBoneName\(chr\.PART_(WEAPON(?:_LEFT)?),\s*"(\w+)"\)', body
        )
    )
    if "WEAPON" not in bones:
        raise ValueError("Missing original weapon attachment")
    return result, {
        "weapon_left" if part == "WEAPON_LEFT" else "weapon_right": bone
        for part, bone in bones.items()
    }


def registered_combo_chains(text: str, source_class: str, mode: str) -> list[list[str]]:
    """Read ordered literal registrations; unknown/missing steps cannot become a chain."""
    body = function_body(text, f"__LoadGame{source_class}Ex")
    source_mode = {"onehand": "ONEHAND_SWORD", "fan": "FAN"}[mode]
    prefix = rf"chr\.MOTION_MODE_{source_mode},\s*COMBO_TYPE_(\d+),\s*"
    capacities = re.findall(r"chrmgr\.ReserveComboAttackNew\(" + prefix + r"(\d+)\)", body)
    entries = re.findall(
        r"chrmgr\.RegisterComboAttackNew\("
        + prefix
        + r"COMBO_INDEX_(\d+),\s*chr\.MOTION_COMBO_ATTACK_(\d+)\)",
        body,
    )
    chains = []
    for chain_id, count in capacities:
        steps = [(int(index), int(motion)) for group, index, motion in entries if group == chain_id]
        if len(steps) != int(count) or [step[0] for step in steps] != list(
            range(1, int(count) + 1)
        ):
            raise ValueError("Incomplete or unordered original combo registration")
        if any(not 1 <= motion <= 7 for _, motion in steps):
            raise ValueError("Unknown original combo motion")
        chains.append([f"combo_{motion}" for _, motion in steps])
    if len(chains) != len({group for group, _ in capacities}) or not chains:
        raise ValueError("Missing or duplicate original combo chains")
    return chains


def initial_points(text: str) -> list[dict]:
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    match = re.search(
        r"TJobInitialPoints\s+JobInitialPoints\[JOB_MAX_NUM\]\s*=\s*\{(.*?)\};", source, re.S
    )
    if not match:
        raise ValueError("Missing original class initial points")
    rows = re.findall(r"\{([^{}]+)\}", match[1])
    fields = "strength vitality dexterity intelligence base_hp base_sp hp_per_vitality sp_per_intelligence hp_gain_min hp_gain_max sp_gain_min sp_gain_max stamina stamina_per_vitality stamina_gain_min stamina_gain_max".split()
    result = []
    for row in rows:
        values = [int(value.strip()) for value in row.split(",") if value.strip()]
        if len(values) != len(fields) or any(not 0 < value < 10000 for value in values):
            raise ValueError("Invalid original class initial points")
        result.append(dict(zip(fields, values, strict=True)))
    if len(result) != 4:
        raise ValueError("Expected four original classes")
    return result
