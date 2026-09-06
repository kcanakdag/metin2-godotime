"""Pure readers for the selected legacy Metin2 content metadata.

The readers are deliberately independent of Blender and preserve unsupported
motion-event records in their result.  Callers decide whether a profile permits
reported omissions; no unknown event is converted to a guessed default.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import PurePosixPath

TOKEN_RE = re.compile(r'"([^"\r\n]*)"|([^\s]+)')
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass
class LegacyNode:
    kind: str
    name: str
    fields: dict[str, list[str]] = field(default_factory=dict)
    groups: list["LegacyNode"] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def group(self, name: str) -> "LegacyNode | None":
        matches = [entry for entry in self.groups if entry.name == name]
        if len(matches) > 1:
            raise ValueError(f"Duplicate group {name!r} in {self.name or '<root>'}")
        return matches[0] if matches else None

    def groups_with_prefix(self, prefix: str) -> list["LegacyNode"]:
        return [entry for entry in self.groups if entry.name.startswith(prefix)]


def _tokens(line: str) -> list[str]:
    return [
        match.group(1) if match.group(1) is not None else match.group(2)
        for match in TOKEN_RE.finditer(line)
    ]


def _strip_comment(line: str) -> str:
    quoted = False
    for index, character in enumerate(line):
        if character == '"':
            quoted = not quoted
        elif character == "#" and not quoted:
            return line[:index]
    return line


def parse_legacy_script(text: str) -> LegacyNode:
    """Parse brace-based MSM/MSA metadata without executing it."""
    root = LegacyNode("root", "")
    stack = [root]
    pending: LegacyNode | None = None
    for number, original in enumerate(text.splitlines(), 1):
        line = _strip_comment(original).strip()
        if not line:
            continue
        if line == "{":
            if pending is None:
                raise ValueError(f"Line {number}: opening brace without Group/List")
            stack.append(pending)
            pending = None
            continue
        if line == "}":
            if pending is not None or len(stack) == 1:
                raise ValueError(f"Line {number}: unmatched closing brace")
            stack.pop()
            continue
        tokens = _tokens(line)
        if not tokens:
            continue
        if tokens[0] in {"Group", "List"}:
            if len(tokens) not in {2, 3} or (len(tokens) == 3 and tokens[2] != "{"):
                raise ValueError(f"Line {number}: malformed {tokens[0]} declaration")
            if pending is not None:
                raise ValueError(f"Line {number}: missing opening brace")
            node = LegacyNode(tokens[0].lower(), tokens[1])
            stack[-1].groups.append(node)
            if len(tokens) == 3:
                stack.append(node)
            else:
                pending = node
            continue
        if pending is not None:
            raise ValueError(f"Line {number}: expected opening brace")
        current = stack[-1]
        if current.kind == "list":
            current.rows.append(tokens)
            continue
        if len(tokens) < 2:
            raise ValueError(f"Line {number}: field {tokens[0]!r} has no value")
        if tokens[0] in current.fields:
            raise ValueError(f"Line {number}: duplicate field {tokens[0]!r}")
        current.fields[tokens[0]] = tokens[1:]
    if pending is not None or len(stack) != 1:
        raise ValueError("Unclosed legacy metadata block")
    return root


def one(node: LegacyNode, name: str, *, required: bool = True) -> str | None:
    values = node.fields.get(name)
    if values is None:
        if required:
            raise ValueError(f"Missing {name!r} in {node.name or '<root>'}")
        return None
    if len(values) != 1:
        raise ValueError(f"{name!r} must contain one value")
    return values[0]


def finite_number(token: str, *, minimum: float | None = None) -> float:
    try:
        value = float(token)
    except ValueError as error:
        raise ValueError(f"Invalid number {token!r}") from error
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f"Out-of-range number {token!r}")
    return value


def integer(token: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if not re.fullmatch(r"-?[0-9]+", token):
        raise ValueError(f"Invalid integer {token!r}")
    value = int(token)
    if not minimum <= value <= maximum:
        raise ValueError(f"Out-of-range integer {token!r}")
    return value


def seconds_to_us(token: str) -> int:
    try:
        value = Decimal(token)
    except InvalidOperation as error:
        raise ValueError(f"Invalid seconds value {token!r}") from error
    if not value.is_finite() or value < 0 or value > 3600:
        raise ValueError(f"Out-of-range seconds value {token!r}")
    return int((value * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def virtual_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    normalized = re.sub(r"^[A-Za-z]:/", "", normalized).lower()
    if normalized.startswith("/") or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError(f"Unsafe virtual path {value!r}")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise ValueError(f"Unsafe virtual path {value!r}")
    return str(path)


def parse_motion_list(text: str) -> list[dict]:
    result = []
    for number, original in enumerate(text.splitlines(), 1):
        line = _strip_comment(original).strip()
        if not line:
            continue
        values = _tokens(line)
        if len(values) != 4:
            raise ValueError(f"Line {number}: motion-list row must have four fields")
        mode, action, path, weight = values
        if not IDENTIFIER_RE.fullmatch(mode.lower()) or not IDENTIFIER_RE.fullmatch(action.lower()):
            raise ValueError(f"Line {number}: invalid mode/action")
        result.append(
            {
                "mode": mode.lower(),
                "action": action.lower(),
                "path": virtual_path(path),
                "weight": integer(weight, minimum=1, maximum=100),
            }
        )
    if not result:
        raise ValueError("Empty motion list")
    return result


def _vector(tokens: list[str], count: int) -> list[float]:
    if len(tokens) != count:
        raise ValueError(f"Expected {count} vector values, got {len(tokens)}")
    return [finite_number(token) for token in tokens]


def _source_to_godot_m(values: list[float]) -> list[float]:
    x, y, z = values
    return [x / 100.0, z / 100.0, -y / 100.0]


def _attack_windows(group: LegacyNode, duration_us: int) -> list[dict]:
    records = group.groups_with_prefix("HitData") or [group]
    declared_count = one(group, "HitDataCount", required=False)
    if declared_count is not None and integer(declared_count) != len(records):
        raise ValueError(f"HitDataCount says {declared_count}, found {len(records)}")
    source_parameters = {
        "attack_type": integer(
            one(group, "AttackType", required=False)
            or one(group, "AttackingType", required=False)
            or "0"
        ),
        "hitting_type": integer(one(group, "HittingType", required=False) or "0"),
        "stiffen_us": seconds_to_us(one(group, "StiffenTime", required=False) or "0"),
        "invisible_us": seconds_to_us(one(group, "InvisibleTime", required=False) or "0"),
        "external_force": finite_number(one(group, "ExternalForce", required=False) or "0"),
        "hit_limit_count": integer(one(group, "HitLimitCount", required=False) or "0"),
        "motion_type": integer(one(group, "MotionType", required=False) or "0"),
    }
    windows = []
    for record in records:
        start = one(record, "AttackingStartTime", required=False)
        end = one(record, "AttackingEndTime", required=False)
        if start is None and end is None:
            continue
        if start is None or end is None:
            raise ValueError("Attack window has only one endpoint")
        start_us, end_us = seconds_to_us(start), seconds_to_us(end)
        if not 0 <= start_us <= end_us <= duration_us:
            raise ValueError(f"Attack window {start_us}..{end_us} exceeds clip {duration_us}")
        positions = record.group("HitPosition")
        samples = []
        if positions is not None:
            for row in positions.rows:
                if len(row) != 7:
                    raise ValueError("HitPosition must contain time and two 3D points")
                if not start_us <= seconds_to_us(row[0]) <= end_us:
                    raise ValueError("HitPosition time lies outside attack window")
                points = _vector(row[1:], 6)
                samples.append(
                    {
                        "time_us": seconds_to_us(row[0]),
                        "start_m": _source_to_godot_m(points[:3]),
                        "end_m": _source_to_godot_m(points[3:]),
                    }
                )
        windows.append(
            {
                "start_us": start_us,
                "end_us": end_us,
                "bone": one(record, "AttackingBone", required=False) or "",
                "weapon_length_m": finite_number(
                    one(record, "WeaponLength", required=False) or "0", minimum=0
                )
                / 100.0,
                "sample_count": len(samples),
                "samples": samples,
                "source_parameters": source_parameters,
            }
        )
    return windows


def _motion_events(group: LegacyNode, duration_us: int) -> tuple[list[dict], list[dict]]:
    count = integer(one(group, "MotionEventDataCount") or "0")
    records = group.groups_with_prefix("Event")
    if len(records) != count:
        raise ValueError(f"MotionEventDataCount says {count}, found {len(records)}")
    events, unsupported = [], []
    for record in records:
        event_type = integer(one(record, "MotionEventType") or "")
        start_us = seconds_to_us(one(record, "StartingTime") or "")
        during = one(record, "DuringTime", required=False)
        end_us = start_us + (seconds_to_us(during) if during is not None else 0)
        if start_us > duration_us or end_us > duration_us:
            raise ValueError(f"Motion event {record.name} exceeds clip duration")
        if event_type == 4:
            spheres = []
            expected = integer(one(record, "SphereDataCount") or "0")
            for sphere in record.groups_with_prefix("SphereData"):
                position = sphere.fields.get("Position")
                spheres.append(
                    {
                        "radius_m": finite_number(one(sphere, "Radius") or "", minimum=0) / 100.0,
                        "position_m": _source_to_godot_m(_vector(position or [], 3)),
                    }
                )
            if len(spheres) != expected:
                raise ValueError(f"SphereDataCount says {expected}, found {len(spheres)}")
            events.append(
                {
                    "kind": "attack_area",
                    "start_us": start_us,
                    "end_us": end_us,
                    "spheres": spheres,
                    "attack_type": integer(one(record, "AttackType", required=False) or "0"),
                    "hitting_type": integer(one(record, "HittingType") or "0"),
                    "stiffen_us": seconds_to_us(one(record, "StiffenTime", required=False) or "0"),
                    "invisible_us": seconds_to_us(
                        one(record, "InvisibleTime", required=False) or "0"
                    ),
                    "external_force": finite_number(
                        one(record, "ExternalForce", required=False) or "0"
                    ),
                    "collision_type": integer(one(record, "CollisionType", required=False) or "0"),
                }
            )
        else:
            unsupported.append(
                {
                    "kind": "motion_event",
                    "event_name": record.name,
                    "event_type": event_type,
                    "start_us": start_us,
                    "end_us": end_us,
                    "fields": {key: values for key, values in sorted(record.fields.items())},
                    "reason": "MotionEventType has no implemented semantic adapter",
                }
            )
    return events, unsupported


def parse_msa(text: str) -> dict:
    root = parse_legacy_script(text)
    if one(root, "ScriptType") != "MotionData":
        raise ValueError("Expected ScriptType MotionData")
    duration_us = seconds_to_us(one(root, "MotionDuration") or "")
    if duration_us == 0:
        raise ValueError("MotionDuration must be positive")
    known_fields = {
        "ScriptType",
        "MotionFileName",
        "MotionDuration",
        "Accumulation",
        "CancelEnableSkill",
    }
    known_groups = {"ComboInputData", "AttackingData", "MotionEventData"}
    unsupported = [
        {"kind": "field", "name": key, "values": values, "reason": "Unknown MSA field"}
        for key, values in sorted(root.fields.items())
        if key not in known_fields
    ]
    unsupported.extend(
        {"kind": "group", "name": group.name, "reason": "Unknown MSA group"}
        for group in root.groups
        if group.name not in known_groups
    )
    accumulation = root.fields.get("Accumulation", ["0", "0", "0"])
    result = {
        "motion_file": virtual_path(one(root, "MotionFileName") or ""),
        "duration_us": duration_us,
        "accumulation_m": _source_to_godot_m(_vector(accumulation, 3)),
        "events": [],
        "combo": None,
        "unsupported": unsupported,
    }
    attack = root.group("AttackingData")
    if attack is not None:
        for window in _attack_windows(attack, duration_us):
            result["events"].append({"kind": "attack_window", **window})
    combo = root.group("ComboInputData")
    if combo is not None:
        link = one(combo, "LinkTime", required=False)
        result["combo"] = {
            "pre_input_us": seconds_to_us(one(combo, "PreInputTime") or ""),
            "direct_input_us": seconds_to_us(one(combo, "DirectInputTime") or ""),
            "input_limit_us": seconds_to_us(one(combo, "InputLimitTime") or ""),
            "link_us": seconds_to_us(link) if link is not None else None,
        }
        if any(value is not None and value > duration_us for value in result["combo"].values()):
            raise ValueError("Combo timing exceeds clip duration")
    motion_events = root.group("MotionEventData")
    if motion_events is not None:
        events, omitted = _motion_events(motion_events, duration_us)
        result["events"].extend(events)
        result["unsupported"].extend(omitted)
    return result


def parse_race_script(text: str) -> dict:
    root = parse_legacy_script(text)
    if one(root, "ScriptType") != "RaceDataScript":
        raise ValueError("Expected ScriptType RaceDataScript")
    model = one(root, "BaseModelFileName")
    attaching = root.group("AttachingData")
    collision = []
    if attaching is not None:
        expected = integer(one(attaching, "AttachingDataCount") or "0")
        records = attaching.groups_with_prefix("AttachingData")
        if len(records) != expected:
            raise ValueError(f"AttachingDataCount says {expected}, found {len(records)}")
        for record in records:
            spheres = []
            expected_spheres = integer(one(record, "SphereDataCount") or "0")
            for sphere in record.groups_with_prefix("SphereData"):
                spheres.append(
                    {
                        "radius_m": finite_number(one(sphere, "Radius") or "", minimum=0) / 100.0,
                        "position_m": _source_to_godot_m(
                            _vector(sphere.fields.get("Position", []), 3)
                        ),
                    }
                )
            if len(spheres) != expected_spheres:
                raise ValueError(f"SphereDataCount says {expected_spheres}, found {len(spheres)}")
            collision.append(
                {
                    "bone": one(record, "AttachingBoneName", required=False) or "",
                    "collision_type": integer(one(record, "CollisionType") or "0"),
                    "spheres": spheres,
                }
            )
    return {"base_model": virtual_path(model or ""), "collision": collision}


def parse_item_script(text: str) -> dict:
    root = parse_legacy_script(text)
    if one(root, "ScriptType") != "ItemDataScript":
        raise ValueError("Expected ScriptType ItemDataScript")
    return {
        "type": integer(one(root, "Type") or ""),
        "model": virtual_path(one(root, "ModelFileName") or ""),
        "drop_model": virtual_path(one(root, "DropModelFileName") or ""),
    }
