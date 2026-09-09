"""Selected self-buff source adapter for the live skill catalog compiler."""

from skill_formulas import compile_formula, rank_value


def berserk_metadata(row: list[str], powers: list[int]) -> dict:
    expected = {
        0: "3",
        2: "1",
        6: "ATT_SPEED",
        10: "",
        14: "SELFONLY",
        15: "14",
        16: "MOV_SPEED",
        19: "14",
        22: "NORMAL",
        23: "1",
        25: "0",
        26: "0",
    }
    if len(row) != 27 or any(row[index] != value for index, value in expected.items()):
        raise ValueError("Unsupported Berserk source mechanics")

    def program(text):
        result = compile_formula(text)
        if any(op["op"] == "number" for op in result):
            raise ValueError("Random self-buff formulas require an evaluation-order policy")
        return result

    def ranks(text, low, high):
        values = [rank_value(text, power, source_float_power=True) for power in powers]
        if any(not low <= value <= high for value in values):
            raise ValueError("Self-buff rank values exceed runtime bounds")
        return [int(value) for value in values]

    costs = ranks(row[8], 0, 10_000)
    cooldowns = [value * 1_000_000 for value in ranks(row[11], 1, 600)]
    modifiers = []
    for point, value, duration in [
        ("attack_speed", row[7], row[9]),
        ("movement_speed", row[17], row[18]),
    ]:
        ranks(value, -100_000, 100_000)
        ranks(duration, 1, 86_400)
        modifiers.append({"point": point, "value": program(value), "duration": program(duration)})
    # char_battle.cpp uses integer GetSkillPower, not the floating formula k.
    modifiers.append(
        {
            "point": "normal_damage_taken_percent",
            "power_percent_factor": 25,
            "duration": program(row[9]),
        }
    )
    return {
        # Pinned uiaffectshower.py selects the active-affect icon, not rank-one skill art.
        "buff_icon": "skill/warrior/jeongwi_03",
        "buff": {"sp_cost": program(row[8]), "cooldown": program(row[11]), "modifiers": modifiers},
        "rank_costs": costs,
        "rank_cooldowns_us": cooldowns,
        "cooldown_us": cooldowns[1],
        "requires_target": False,
        "target_range_m": 0.0,
        "radius_m": 0.0,
        "max_targets": 1,
    }


def aura_of_the_sword_metadata(row: list[str], powers: list[int]) -> dict:
    """Warrior Aura of the Sword: attack grade and duration from the source row."""
    expected = {
        0: "4",
        2: "1",
        6: "ATT_GRADE",
        10: "",
        14: "SELFONLY",
        15: "15",
        16: "NONE",
        19: "15",
        22: "NORMAL",
        23: "1",
        25: "0",
        26: "0",
    }
    if len(row) != 27 or any(row[index] != value for index, value in expected.items()):
        raise ValueError("Unsupported Aura of the Sword source mechanics")

    def program(text):
        result = compile_formula(text)
        if any(op["op"] == "number" for op in result):
            raise ValueError("Random self-buff formulas require an evaluation-order policy")
        return result

    def ranks(text, low, high):
        values = [rank_value(text, power, source_float_power=True) for power in powers]
        if any(not low <= value <= high for value in values):
            raise ValueError("Self-buff rank values exceed runtime bounds")
        return [int(value) for value in values]

    costs = ranks(row[8], 0, 10_000)
    cooldowns = [value * 1_000_000 for value in ranks(row[11], 1, 600)]
    # Modifier values may depend on live stats, so validate their bounded
    # program shape here and enforce the runtime value range during capture.
    program(row[7])
    program(row[9])
    return {
        "buff_icon": "skill/warrior/geomgyeong_03",
        "buff": {
            "sp_cost": program(row[8]),
            "cooldown": program(row[11]),
            "modifiers": [
                {
                    "point": "attack_grade",
                    "value": program(row[7]),
                    "duration": program(row[9]),
                }
            ],
        },
        "rank_costs": costs,
        "rank_cooldowns_us": cooldowns,
        "cooldown_us": cooldowns[1],
        "requires_target": False,
        "target_range_m": 0.0,
        "radius_m": 0.0,
        "max_targets": 1,
    }


def strong_body_metadata(row: list[str], powers: list[int]) -> dict:
    """Warrior Strong Body: defense grade plus its original movement penalty."""
    expected = {
        0: "19",
        2: "1",
        6: "DEF_GRADE",
        10: "",
        14: "SELFONLY",
        15: "16",
        16: "MOV_SPEED",
        19: "16",
        22: "NORMAL",
        23: "1",
        25: "0",
        26: "0",
    }
    if len(row) != 27 or any(row[index] != value for index, value in expected.items()):
        raise ValueError("Unsupported Strong Body source mechanics")

    def program(text):
        result = compile_formula(text)
        if any(op["op"] == "number" for op in result):
            raise ValueError("Random self-buff formulas require an evaluation-order policy")
        return result

    def ranks(text, low, high):
        values = [rank_value(text, power, source_float_power=True) for power in powers]
        if any(not low <= value <= high for value in values):
            raise ValueError("Self-buff rank values exceed runtime bounds")
        return [int(value) for value in values]

    costs = ranks(row[8], 0, 10_000)
    cooldowns = [value * 1_000_000 for value in ranks(row[11], 1, 600)]
    # Modifier values may depend on live stats, so validate their bounded
    # program shape here and enforce the runtime value range during capture.
    program(row[7])
    program(row[9])
    program(row[17])
    program(row[18])
    return {
        "buff_icon": "skill/warrior/cheongeun_03",
        "buff": {
            "sp_cost": program(row[8]),
            "cooldown": program(row[11]),
            "modifiers": [
                {
                    "point": "defense_grade",
                    "value": program(row[7]),
                    "duration": program(row[9]),
                },
                {
                    "point": "movement_speed",
                    "value": program(row[17]),
                    "duration": program(row[18]),
                },
            ],
        },
        "rank_costs": costs,
        "rank_cooldowns_us": cooldowns,
        "cooldown_us": cooldowns[1],
        "requires_target": False,
        "target_range_m": 0.0,
        "radius_m": 0.0,
        "max_targets": 1,
    }


def self_buff_metadata(row: list[str], powers: list[int]) -> dict:
    """Dispatch the supported original Warrior self-buff rows."""
    if not row:
        raise ValueError("Missing self-buff source row")
    if row[0] == "3":
        return berserk_metadata(row, powers)
    if row[0] == "4":
        return aura_of_the_sword_metadata(row, powers)
    if row[0] == "19":
        return strong_body_metadata(row, powers)
    raise ValueError("Unsupported self-buff skill vnum")
