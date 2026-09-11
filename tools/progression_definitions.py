"""Extract the selected P2 progression facts from pinned C++ source text.

This module intentionally accepts source text from its caller.  It does not read
the ignored research JSON or any repository paths, so the content compiler can
own pinned-input provenance and artifact generation separately.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import TypedDict

U32_MAX = (1 << 32) - 1
I32_MAX = (1 << 31) - 1
EXP_TABLE_MAX_NAME = "PLAYER_EXP_TABLE_MAX"
NORMAL_DELTA_COUNT = 31
BOSS_DELTA_COUNT = 31
EXPECTED_COMPILED_MAX_LEVEL = 120
EXPECTED_DEFAULT_LEVEL_CAP = 99


class ProgressionDefinitionError(ValueError):
    """A selected progression fact was absent, ambiguous, or invalid."""


class WarriorInitialRecord(TypedDict):
    strength: int
    vitality: int
    dexterity: int
    intelligence: int
    base_max_hp: int
    base_max_sp: int
    hp_per_vitality: int
    sp_per_intelligence: int
    hp_per_level_inclusive: list[int]
    sp_per_level_inclusive: list[int]
    base_stamina: int
    stamina_per_vitality: int
    stamina_per_level_inclusive: list[int]
    initial_max_hp: int
    initial_max_sp: int


class QuarterThresholdRecord(TypedDict):
    level: int
    next_experience: int
    thresholds: list[int]


class ProgressionDefinitionsRecord(TypedDict):
    schema: str
    schema_version: int
    compiled_max_level: int
    default_level_cap: int
    warrior_initial: WarriorInitialRecord
    experience_to_next_level_by_current_level: list[int]
    normal_level_delta_percent: list[int]
    quarter_thresholds_by_current_level: list[QuarterThresholdRecord]


@dataclass(frozen=True)
class WarriorInitial:
    strength: int
    vitality: int
    dexterity: int
    intelligence: int
    base_max_hp: int
    base_max_sp: int
    hp_per_vitality: int
    sp_per_intelligence: int
    hp_per_level_begin: int
    hp_per_level_end: int
    sp_per_level_begin: int
    sp_per_level_end: int
    base_stamina: int
    stamina_per_vitality: int
    stamina_per_level_begin: int
    stamina_per_level_end: int

    def to_record(self) -> WarriorInitialRecord:
        return {
            "strength": self.strength,
            "vitality": self.vitality,
            "dexterity": self.dexterity,
            "intelligence": self.intelligence,
            "base_max_hp": self.base_max_hp,
            "base_max_sp": self.base_max_sp,
            "hp_per_vitality": self.hp_per_vitality,
            "sp_per_intelligence": self.sp_per_intelligence,
            "hp_per_level_inclusive": [self.hp_per_level_begin, self.hp_per_level_end],
            "sp_per_level_inclusive": [self.sp_per_level_begin, self.sp_per_level_end],
            "base_stamina": self.base_stamina,
            "stamina_per_vitality": self.stamina_per_vitality,
            "stamina_per_level_inclusive": [
                self.stamina_per_level_begin,
                self.stamina_per_level_end,
            ],
            "initial_max_hp": self.base_max_hp + self.vitality * self.hp_per_vitality,
            "initial_max_sp": self.base_max_sp + self.intelligence * self.sp_per_intelligence,
        }


@dataclass(frozen=True)
class ProgressionDefinitions:
    compiled_max_level: int
    default_level_cap: int
    warrior_initial: WarriorInitial
    experience_to_next_level: tuple[int, ...]
    normal_level_delta_percent: tuple[int, ...]
    quarter_thresholds_by_current_level: tuple[tuple[int, int, int, int], ...]

    def to_record(self) -> ProgressionDefinitionsRecord:
        return {
            "schema": "mt2spacetime.progression-definitions",
            "schema_version": 1,
            "compiled_max_level": self.compiled_max_level,
            "default_level_cap": self.default_level_cap,
            "warrior_initial": self.warrior_initial.to_record(),
            "experience_to_next_level_by_current_level": list(self.experience_to_next_level),
            "normal_level_delta_percent": list(self.normal_level_delta_percent),
            "quarter_thresholds_by_current_level": [
                {
                    "level": level,
                    "next_experience": self.experience_to_next_level[level],
                    "thresholds": list(thresholds),
                }
                for level, thresholds in enumerate(self.quarter_thresholds_by_current_level)
            ],
        }


def parse_progression_definitions(
    constants_cpp: str, length_h: str, config_cpp: str
) -> ProgressionDefinitions:
    """Return selected Warrior progression data validated from pinned C++ text."""

    warrior_initial = _parse_warrior_initial(constants_cpp)
    compiled_max_level = _parse_named_assignment(length_h, EXP_TABLE_MAX_NAME)
    if not 1 <= compiled_max_level <= 255:
        raise ProgressionDefinitionError(
            f"{EXP_TABLE_MAX_NAME} must be within 1..255, got {compiled_max_level}"
        )
    if compiled_max_level != EXPECTED_COMPILED_MAX_LEVEL:
        raise ProgressionDefinitionError(
            f"{EXP_TABLE_MAX_NAME} must be {EXPECTED_COMPILED_MAX_LEVEL}, got {compiled_max_level}"
        )

    experience_to_next_level = _parse_integer_array(constants_cpp, "exp_table")
    expected_exp_count = compiled_max_level + 1
    if len(experience_to_next_level) != expected_exp_count:
        raise ProgressionDefinitionError(
            "exp_table must contain indices 0.."
            f"{compiled_max_level} ({expected_exp_count} values), got {len(experience_to_next_level)}"
        )
    _require_u32_values("exp_table", experience_to_next_level)
    if experience_to_next_level[0] != 0:
        raise ProgressionDefinitionError("exp_table[0] must be 0")
    for level, next_experience in enumerate(experience_to_next_level[1:], start=1):
        if next_experience == 0:
            raise ProgressionDefinitionError(f"exp_table[{level}] must be positive")

    normal_level_delta_percent = _level_delta_percent(
        constants_cpp, "aiPercentByDeltaLev", NORMAL_DELTA_COUNT
    )

    default_level_cap = _parse_named_assignment(config_cpp, "gPlayerMaxLevel")
    if not 1 <= default_level_cap <= compiled_max_level:
        raise ProgressionDefinitionError(
            f"gPlayerMaxLevel must be within 1..{compiled_max_level}, got {default_level_cap}"
        )
    if default_level_cap != EXPECTED_DEFAULT_LEVEL_CAP:
        raise ProgressionDefinitionError(
            f"gPlayerMaxLevel must be {EXPECTED_DEFAULT_LEVEL_CAP}, got {default_level_cap}"
        )

    thresholds = tuple(
        quarter_thresholds(next_experience) for next_experience in experience_to_next_level
    )
    return ProgressionDefinitions(
        compiled_max_level=compiled_max_level,
        default_level_cap=default_level_cap,
        warrior_initial=warrior_initial,
        experience_to_next_level=tuple(experience_to_next_level),
        normal_level_delta_percent=tuple(normal_level_delta_percent),
        quarter_thresholds_by_current_level=thresholds,
    )


def quarter_thresholds(next_experience: int) -> tuple[int, int, int, int]:
    """Reproduce ``DWORD(next_exp / 4.0f)`` and the four authoritative steps."""

    if not isinstance(next_experience, int) or isinstance(next_experience, bool):
        raise ProgressionDefinitionError("next experience must be an integer")
    if not 0 <= next_experience <= U32_MAX:
        raise ProgressionDefinitionError(
            f"next experience must be within u32, got {next_experience}"
        )
    float32_value = struct.unpack("!f", struct.pack("!f", float(next_experience)))[0]
    quarter = int(float32_value / 4.0)
    if not 0 <= quarter <= U32_MAX:
        raise ProgressionDefinitionError("float32 quarter is outside u32")
    return quarter, quarter * 2, quarter * 3, next_experience


def _parse_warrior_initial(source: str) -> WarriorInitial:
    body = _extract_braced_initializer(source, "JobInitialPoints")
    entries = _top_level_braced_entries(body, "JobInitialPoints")
    if not entries:
        raise ProgressionDefinitionError("JobInitialPoints has no JOB_WARRIOR entry")
    values = _parse_integer_list(entries[0], "JobInitialPoints JOB_WARRIOR")
    if len(values) != 16:
        raise ProgressionDefinitionError(
            f"JobInitialPoints JOB_WARRIOR must contain 16 values, got {len(values)}"
        )
    if any(value < 0 or value > I32_MAX for value in values):
        raise ProgressionDefinitionError(
            "JobInitialPoints JOB_WARRIOR values must be within non-negative i32"
        )
    warrior = WarriorInitial(*values)
    if warrior.hp_per_level_begin > warrior.hp_per_level_end:
        raise ProgressionDefinitionError("JOB_WARRIOR HP per-level range is reversed")
    if warrior.sp_per_level_begin > warrior.sp_per_level_end:
        raise ProgressionDefinitionError("JOB_WARRIOR SP per-level range is reversed")
    if warrior.hp_per_level_begin == 0 or warrior.sp_per_level_begin == 0:
        raise ProgressionDefinitionError("JOB_WARRIOR per-level ranges must be positive")
    return warrior


def _parse_integer_array(source: str, name: str) -> list[int]:
    return _parse_integer_list(_extract_braced_initializer(source, name), name)


def _level_delta_percent(source: str, name: str, count: int) -> list[int]:
    values = _parse_integer_array(source, name)
    if len(values) != count:
        raise ProgressionDefinitionError(f"{name} must contain {count} values, got {len(values)}")
    if any(value < 0 or value > 1000 for value in values):
        raise ProgressionDefinitionError(f"{name} values must be within 0..1000")
    return values


def parse_mob_level_delta_tables(
    constants_cpp: str,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Both ``aiPercentByDeltaLev`` tables the original scales loot with.

    ``ITEM_MANAGER::GetDropPct`` selects ``aiPercentByDeltaLevForBoss`` for a
    non-stone mob of ``MOB_RANK_BOSS`` or above and ``aiPercentByDeltaLev``
    otherwise. ``tools/build_drop_catalog.py`` embeds the pair in the compiled
    drop catalog so the runtime rolls the pinned percentages instead of a copy
    that could drift from the source.
    """

    normal = _level_delta_percent(constants_cpp, "aiPercentByDeltaLev", NORMAL_DELTA_COUNT)
    boss = _level_delta_percent(constants_cpp, "aiPercentByDeltaLevForBoss", BOSS_DELTA_COUNT)
    return tuple(normal), tuple(boss)


def _parse_named_assignment(source: str, name: str) -> int:
    matches = list(
        re.finditer(rf"\b{re.escape(name)}\s*=\s*([0-9]+)\s*[,;]", _strip_comments(source))
    )
    if len(matches) != 1:
        raise ProgressionDefinitionError(
            f"{name} must have exactly one literal assignment, got {len(matches)}"
        )
    return int(matches[0].group(1))


def _extract_braced_initializer(source: str, name: str) -> str:
    clean_source = _strip_comments(source)
    declaration = re.compile(rf"\b{re.escape(name)}\b\s*(?:\[[^\]]*\])?\s*=\s*\{{", re.MULTILINE)
    matches = list(declaration.finditer(clean_source))
    if len(matches) != 1:
        raise ProgressionDefinitionError(
            f"{name} must have exactly one braced initializer, got {len(matches)}"
        )
    opening_brace = matches[0].end() - 1
    closing_brace = _matching_brace(clean_source, opening_brace, name)
    remainder = clean_source[closing_brace + 1 :].lstrip()
    if not remainder.startswith(";"):
        raise ProgressionDefinitionError(f"{name} initializer must end with a semicolon")
    return clean_source[opening_brace + 1 : closing_brace]


def _top_level_braced_entries(body: str, name: str) -> list[str]:
    entries: list[str] = []
    index = 0
    while index < len(body):
        if body[index].isspace() or body[index] == ",":
            index += 1
            continue
        if body[index] != "{":
            raise ProgressionDefinitionError(f"{name} contains unexpected text before an entry")
        end = _matching_brace(body, index, name)
        entries.append(body[index + 1 : end])
        index = end + 1
    return entries


def _matching_brace(source: str, opening_brace: int, name: str) -> int:
    depth = 0
    for index in range(opening_brace, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ProgressionDefinitionError(f"{name} has an unclosed braced initializer")


def _parse_integer_list(body: str, name: str) -> list[int]:
    values: list[int] = []
    parts = body.split(",")
    for index, raw_value in enumerate(parts):
        value = raw_value.strip()
        if not value:
            if index == len(parts) - 1:
                continue
            raise ProgressionDefinitionError(f"{name} has an empty value at index {index}")
        match = re.fullmatch(r"([0-9]+|0[xX][0-9a-fA-F]+)[uUlL]*", value)
        if match is None:
            raise ProgressionDefinitionError(
                f"{name} value at index {index} is not an integer literal"
            )
        values.append(int(match.group(1), 0))
    return values


def _require_u32_values(name: str, values: list[int]) -> None:
    for index, value in enumerate(values):
        if not 0 <= value <= U32_MAX:
            raise ProgressionDefinitionError(f"{name}[{index}] is outside u32: {value}")


def _strip_comments(source: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_block_comments)
