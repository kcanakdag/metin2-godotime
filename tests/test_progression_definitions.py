"""Focused fixtures for the pure P2 progression-definition parser."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from progression_definitions import (  # noqa: E402
    BOSS_DELTA_COUNT,
    NORMAL_DELTA_COUNT,
    ProgressionDefinitionError,
    parse_mob_level_delta_tables,
    parse_progression_definitions,
    quarter_thresholds,
)

WARRIOR_VALUES = "6, 4, 3, 3, 600, 200, 40, 20, 36, 44, 18, 22, 800, 5, 1, 3"
EXPERIENCE_VALUES = [0, 300, *range(800, 800 + 119)]
DELTA_VALUES = [
    1,
    5,
    10,
    20,
    30,
    50,
    70,
    80,
    85,
    90,
    92,
    94,
    96,
    98,
    100,
    100,
    105,
    110,
    115,
    120,
    125,
    130,
    135,
    140,
    145,
    150,
    155,
    160,
    165,
    170,
    180,
]


def source_fixture(
    *,
    warrior_values: str = WARRIOR_VALUES,
    experience_values: list[int] | None = None,
    delta_values: list[int] | None = None,
    compiled_max: int = 120,
    default_cap: int = 99,
) -> tuple[str, str, str]:
    experience_values = EXPERIENCE_VALUES if experience_values is None else experience_values
    delta_values = DELTA_VALUES if delta_values is None else delta_values
    constants = f"""
        TJobInitialPoints JobInitialPoints[JOB_MAX_NUM] = {{
            {{ {warrior_values} }}, // JOB_WARRIOR
        }};
        const DWORD exp_table[PLAYER_EXP_TABLE_MAX + 1] = {{
            {", ".join(map(str, experience_values))},
        }};
        const int aiPercentByDeltaLev[MAX_EXP_DELTA_OF_LEV] = {{
            {", ".join(map(str, delta_values))},
        }};
    """
    length = f"enum {{ PLAYER_EXP_TABLE_MAX = {compiled_max}, }};"
    config = f"int gPlayerMaxLevel = {default_cap};"
    return constants, length, config


def definitions_fixture(**changes):
    return parse_progression_definitions(*source_fixture(**changes))


# ``aiPercentByDeltaLevForBoss`` from ``src/game/src/constants.cpp``: equal to
# the normal table up to index 14, then the boss curve ``GetDropPct`` selects
# for a ranked mob.
BOSS_DELTA_VALUES = [
    1,
    3,
    5,
    7,
    15,
    30,
    60,
    90,
    91,
    92,
    93,
    94,
    95,
    97,
    99,
    100,
    105,
    110,
    115,
    120,
    125,
    130,
    135,
    140,
    145,
    150,
    155,
    160,
    165,
    170,
    180,
]


def mob_level_delta_fixture() -> str:
    """The two level-delta declarations as the pinned ``constants.cpp`` has them."""
    normal = ", ".join(map(str, DELTA_VALUES))
    boss = ", ".join(map(str, BOSS_DELTA_VALUES))
    return (
        "const int aiPercentByDeltaLev[MAX_EXP_DELTA_OF_LEV] = "
        f"{{ {normal} }};\n"
        "const int aiPercentByDeltaLevForBoss[MAX_EXP_DELTA_OF_LEV] = "
        f"{{ {boss} }};\n"
    )


class ProgressionDefinitionsTests(unittest.TestCase):
    def assert_definition_error(self, message: str, operation) -> None:
        with self.assertRaisesRegex(ProgressionDefinitionError, re.escape(message)):
            operation()

    def test_mob_level_delta_tables_are_parsed_from_the_constants_shape(self) -> None:
        normal, boss = parse_mob_level_delta_tables(mob_level_delta_fixture())
        self.assertEqual(len(normal), NORMAL_DELTA_COUNT)
        self.assertEqual(len(boss), BOSS_DELTA_COUNT)
        self.assertEqual(normal, tuple(DELTA_VALUES))
        self.assertEqual(boss, tuple(BOSS_DELTA_VALUES))
        self.assertEqual(normal[0], 1)
        self.assertEqual(normal[-1], 180)
        self.assertEqual((boss[0], boss[-1]), (1, 180))

    def test_the_boss_table_is_required_and_checked(self) -> None:
        constants, _, _ = source_fixture()
        boss_body = ", ".join(map(str, DELTA_VALUES))
        with_boss = (
            constants + f"\nconst int aiPercentByDeltaLevForBoss[MAX_EXP_DELTA_OF_LEV] = "
            f"{{ {boss_body} }};\n"
        )
        _, boss = parse_mob_level_delta_tables(with_boss)
        self.assertEqual(boss, tuple(DELTA_VALUES))

        self.assert_definition_error(
            "aiPercentByDeltaLevForBoss must contain 31 values",
            lambda: parse_mob_level_delta_tables(
                constants + "\nconst int aiPercentByDeltaLevForBoss[MAX_EXP_DELTA_OF_LEV] = "
                f"{{ {', '.join(map(str, DELTA_VALUES[:-1]))} }};\n"
            ),
        )
        self.assert_definition_error(
            "aiPercentByDeltaLevForBoss values must be within 0..1000",
            lambda: parse_mob_level_delta_tables(
                constants + "\nconst int aiPercentByDeltaLevForBoss[MAX_EXP_DELTA_OF_LEV] = "
                f"{{ {', '.join(map(str, [*DELTA_VALUES[:-1], 1001]))} }};\n"
            ),
        )
        self.assert_definition_error(
            "aiPercentByDeltaLevForBoss must have exactly one braced initializer",
            lambda: parse_mob_level_delta_tables(constants),
        )
        self.assert_definition_error(
            "aiPercentByDeltaLev must contain 31 values",
            lambda: parse_mob_level_delta_tables(
                "const int aiPercentByDeltaLev[MAX_EXP_DELTA_OF_LEV] = "
                f"{{ {', '.join(map(str, DELTA_VALUES[:-1]))} }};\n"
                "const int aiPercentByDeltaLevForBoss[MAX_EXP_DELTA_OF_LEV] = "
                f"{{ {boss_body} }};\n"
            ),
        )

    def test_known_warrior_and_dog_progression_inputs(self) -> None:
        definitions = definitions_fixture()
        warrior = definitions.warrior_initial
        self.assertEqual(
            (warrior.strength, warrior.vitality, warrior.dexterity, warrior.intelligence),
            (6, 4, 3, 3),
        )
        self.assertEqual(warrior.base_max_hp + warrior.vitality * warrior.hp_per_vitality, 760)
        self.assertEqual(
            warrior.base_max_sp + warrior.intelligence * warrior.sp_per_intelligence, 260
        )
        self.assertEqual(definitions.experience_to_next_level[1], 300)
        self.assertEqual(definitions.normal_level_delta_percent[15], 100)
        self.assertEqual(definitions.normal_level_delta_percent[14], 100)
        self.assertEqual(definitions.normal_level_delta_percent[13], 98)
        self.assertEqual((15 * definitions.normal_level_delta_percent[15]) // 100, 15)
        self.assertEqual((15 * definitions.normal_level_delta_percent[13]) // 100, 14)
        self.assertEqual((definitions.default_level_cap, definitions.compiled_max_level), (99, 120))

    def test_record_is_json_compatible_and_precomputes_quarters(self) -> None:
        record = definitions_fixture().to_record()
        self.assertEqual(record["schema"], "mt2spacetime.progression-definitions")
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["warrior_initial"]["initial_max_hp"], 760)
        self.assertEqual(record["warrior_initial"]["initial_max_sp"], 260)
        self.assertEqual(
            record["quarter_thresholds_by_current_level"][1],
            {"level": 1, "next_experience": 300, "thresholds": [75, 150, 225, 300]},
        )

    def test_float32_quarter_differs_from_integer_division_at_high_level(self) -> None:
        thresholds = quarter_thresholds(346_970_000)
        self.assertEqual(thresholds, (86_742_496, 173_484_992, 260_227_488, 346_970_000))
        self.assertNotEqual(thresholds[0], 346_970_000 // 4)

    def test_rejects_malformed_and_missing_declarations(self) -> None:
        constants, length, config = source_fixture()
        self.assert_definition_error(
            "initializer must end with a semicolon",
            lambda: parse_progression_definitions(constants.replace("};", "}", 1), length, config),
        )
        self.assert_definition_error(
            "gPlayerMaxLevel must have exactly one literal assignment",
            lambda: parse_progression_definitions(constants, length, "int another_value = 99;"),
        )
        self.assert_definition_error(
            "PLAYER_EXP_TABLE_MAX must have exactly one literal assignment",
            lambda: parse_progression_definitions(constants, "enum { UNUSED = 120, };", config),
        )

    def test_rejects_duplicate_declarations_and_bad_ranges(self) -> None:
        constants, length, config = source_fixture()
        duplicate_constants = constants + constants
        self.assert_definition_error(
            "JobInitialPoints must have exactly one braced initializer",
            lambda: parse_progression_definitions(duplicate_constants, length, config),
        )
        self.assert_definition_error(
            "HP per-level range is reversed",
            lambda: definitions_fixture(warrior_values=WARRIOR_VALUES.replace("36, 44", "44, 36")),
        )
        self.assert_definition_error(
            "gPlayerMaxLevel must be within 1..120", lambda: definitions_fixture(default_cap=121)
        )
        self.assert_definition_error(
            "PLAYER_EXP_TABLE_MAX must be 120", lambda: definitions_fixture(compiled_max=119)
        )
        self.assert_definition_error(
            "gPlayerMaxLevel must be 99", lambda: definitions_fixture(default_cap=98)
        )

    def test_rejects_out_of_range_and_wrong_table_sizes(self) -> None:
        bad_experience = [*EXPERIENCE_VALUES]
        bad_experience[12] = 1 << 32
        self.assert_definition_error(
            "exp_table[12] is outside u32",
            lambda: definitions_fixture(experience_values=bad_experience),
        )
        self.assert_definition_error(
            "aiPercentByDeltaLev must contain 31 values",
            lambda: definitions_fixture(delta_values=DELTA_VALUES[:-1]),
        )
        self.assert_definition_error(
            "exp_table must contain indices 0..120",
            lambda: definitions_fixture(experience_values=EXPERIENCE_VALUES[:-1]),
        )
        zero_entry = [*EXPERIENCE_VALUES]
        zero_entry[77] = 0
        self.assert_definition_error(
            "exp_table[77] must be positive",
            lambda: definitions_fixture(experience_values=zero_entry),
        )
        self.assert_definition_error(
            "values must be within non-negative i32",
            lambda: definitions_fixture(warrior_values=WARRIOR_VALUES.replace("600", str(1 << 31))),
        )

    def test_quarter_threshold_input_is_checked(self) -> None:
        self.assert_definition_error(
            "next experience must be within u32", lambda: quarter_thresholds(-1)
        )
        self.assert_definition_error(
            "next experience must be an integer", lambda: quarter_thresholds(1.5)
        )
