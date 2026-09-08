"""Read selected original flight scripts; preserve unsafe source trails as explicit issues."""

import math
from pathlib import PurePosixPath

from content_formats import parse_legacy_script, virtual_path

DEFAULTS = {
    "SpreadingFlag": ["0"],
    "MaintainParallelFlag": ["0"],
    "ConeAngle": ["0"],
    "RollAngle": ["0"],
    "AngularVelocity": ["0", "0", "0"],
    "Gravity": ["0"],
    "HitOnBackground": ["0"],
    "HitOnAnotherMonster": ["0"],
    "PierceCount": ["0"],
    "BombRange": ["10"],
    "BombEffect": [""],
    "HomingFlag": ["0"],
    "HomingStartTime": ["0"],
    "HomingMaxAngle": ["0"],
    "Acceleration": ["0", "0", "0"],
}
FLAGS = {
    "SpreadingFlag",
    "MaintainParallelFlag",
    "HitOnBackground",
    "HitOnAnotherMonster",
    "HomingFlag",
}


def scalar(fields, key):
    values = fields.get(key)
    if not isinstance(values, list) or len(values) != 1:
        raise ValueError(f"Expected one flight value for {key}")
    return values[0]


def number(fields, key):
    value = float(scalar(fields, key))
    if not math.isfinite(value):
        raise ValueError(f"Nonfinite flight value for {key}")
    return value


def integer(fields, key, low, high):
    token = scalar(fields, key)
    value = int(token)
    if str(value) != token or not low <= value <= high:
        raise ValueError(f"Invalid flight integer {key}")
    return value


def effect_path(base, value):
    if not value:
        return None
    normalized = virtual_path(value)
    if not normalized.startswith("ymir work/"):
        normalized = virtual_path(str(PurePosixPath(base).parent / normalized))
    if not normalized.startswith("ymir work/") or not normalized.endswith(".mse"):
        raise ValueError("Flight effect must reference an original MSE path")
    return normalized


def parse_flight(text, path):
    path = virtual_path(path)
    root = parse_legacy_script(text)
    if set(root.fields) - (DEFAULTS.keys() | {"InitialVelocity", "Range", "CollisionSphereRadius"}):
        raise ValueError("Unsupported flight root fields")
    fields = {**DEFAULTS, **root.fields}
    flight = {}
    for key in FLAGS:
        flight[key] = bool(integer(fields, key, 0, 1))
    for key in (
        "InitialVelocity",
        "Range",
        "ConeAngle",
        "RollAngle",
        "Gravity",
        "BombRange",
        "HomingStartTime",
        "HomingMaxAngle",
    ):
        flight[key] = number(fields, key)
        if abs(flight[key]) > 1_000_000:
            raise ValueError("Flight scalar exceeds supported bounds")
    if flight["InitialVelocity"] <= 0 or flight["Range"] <= 0 or flight["HomingStartTime"] < 0:
        raise ValueError("Invalid flight speed, range or homing delay")
    flight["PierceCount"] = integer(fields, "PierceCount", 0, 1000)
    for key in ("Acceleration", "AngularVelocity"):
        values = [float(v) for v in fields[key]]
        if len(values) != 3 or any(not math.isfinite(v) or abs(v) > 1_000_000 for v in values):
            raise ValueError("Invalid flight vector")
        flight[key] = values
    bomb = effect_path(path, scalar(fields, "BombEffect"))
    attachments, issues = [], []
    for index, node in enumerate(root.groups):
        if node.name != "AttachData" or node.groups:
            raise ValueError("Unsupported flight child group")
        allowed = {
            "Type",
            "FlyType",
            "AttachFile",
            "TailFlag",
            "TailColor",
            "TailLength",
            "TailSize",
            "TailShapeRect",
            "Roll",
            "Distance",
            "Period",
            "Amplitude",
        }
        if set(node.fields) - allowed:
            raise ValueError("Unsupported flight attachment fields")
        f = node.fields
        kind, mode = integer(f, "Type", 0, 2), integer(f, "FlyType", 0, 4)
        if kind != 1:
            issues.append({"attachment": index, "reason": "non-effect-attachment-not-implemented"})
        tail = None
        if integer(f, "TailFlag", 0, 1):
            color = scalar(f, "TailColor")
            if (
                not color.endswith("d")
                or not color[:-1].isdecimal()
                or int(color[:-1]) > 0xFFFFFFFF
            ):
                raise ValueError("Invalid original DWORD trail color")
            tail = {
                "argb": int(color[:-1]),
                "length_seconds": number(f, "TailLength"),
                "size_cm": number(f, "TailSize"),
                "rectangular": bool(integer(f, "TailShapeRect", 0, 1)),
            }
            tail["history_policy"] = (
                "expires-immediately" if tail["length_seconds"] < 0 else "timed-history"
            )
            if not 0 < tail["length_seconds"] <= 60 or not 0 < tail["size_cm"] <= 10000:
                issues.append(
                    {
                        "attachment": index,
                        "reason": "invalid-source-trail-dimensions",
                        "source_tail": tail,
                    }
                )
        attachments.append(
            {
                "type": kind,
                "fly_type": mode,
                "effect": effect_path(path, scalar(f, "AttachFile")),
                "tail": tail,
                "roll_degrees": number(f, "Roll"),
                "distance_cm": number(f, "Distance"),
                "period_seconds": number(f, "Period"),
                "amplitude_cm": number(f, "Amplitude"),
            }
        )
    if not 1 <= len(attachments) <= 32:
        raise ValueError("Flight requires a bounded attachment set")
    dependencies = sorted({p for p in [bomb, *(a["effect"] for a in attachments)] if p})
    return {
        "path": path,
        "source_units": "centimetres-seconds-degrees",
        "flight": flight,
        "bomb_effect": bomb,
        "attachments": attachments,
        "effect_dependencies": dependencies,
        "source_issues": issues,
        "ignored_root_fields": {
            k: root.fields[k] for k in ("CollisionSphereRadius",) if k in root.fields
        },
        "defaulted_fields": sorted(DEFAULTS.keys() - root.fields.keys()),
    }
