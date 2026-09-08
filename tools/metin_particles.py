"""Bounded particle-only MSE reader; values retain original cm/seconds units.

This is an independently authored adapter for EffectLib/ParticleSystemData.cpp,
not a simulation or a claim that every parsed render mode is implemented.
"""

import re
from pathlib import PurePosixPath

from content_formats import finite_number, integer, parse_legacy_script, virtual_path
from metin_effect_mesh import d3dx_color_byte

EMITTER_FIELDS = {
    "MaxEmissionCount": (1, 4096),
    "CycleLength": (0.000001, 60.0),
    "CycleLoopEnable": (0, 1),
    "LoopCount": (0, 10000),
    "EmitterShape": (0, 3),
    "EmitterAdvancedType": (0, 2),
    "EmitterEmitFromEdgeFlag": (0, 1),
}
PARTICLE_FIELDS = {
    "SrcBlendType": (1, 13),
    "DestBlendType": (1, 13),
    "ColorOperationType": (1, 26),
    "BillboardType": (0, 5),
    "RotationType": (0, 4),
    "RotationSpeed": (-10000.0, 10000.0),
    "RotationRandomStartingBegin": (0, 65535),
    "RotationRandomStartingEnd": (0, 65535),
    "AttachEnable": (0, 1),
    "StretchEnable": (0, 1),
    "TexAniType": (0, 4),
    "TexAniDelay": (0.0, 60.0),
    "TexAniRandomStartFrameEnable": (0, 1),
}
EMITTER_CURVES = (
    "EmittingSize",
    "EmittingAngularVelocity",
    "EmittingDirectionX",
    "EmittingDirectionY",
    "EmittingDirectionZ",
    "EmittingVelocity",
    "EmissionCountPerSecond",
    "LifeTime",
    "SizeX",
    "SizeY",
)
PARTICLE_CURVES = (
    "Gravity",
    "AirResistance",
    "ScaleX",
    "ScaleY",
    "ColorRed",
    "ColorGreen",
    "ColorBlue",
    "Alpha",
    "Rotation",
)


def number(token, low=-100000.0, high=100000.0):
    value = finite_number(token)
    if not low <= value <= high:
        raise ValueError("Particle value exceeds supported bounds")
    return value


def shape(node, fields, children, *, repeated=False):
    if node.rows or set(node.fields) - set(fields):
        raise ValueError(f"Unexpected fields/rows in {node.name}")
    keys = [(g.kind, g.name) for g in node.groups]
    if set(keys) - set(children) or (not repeated and len(set(keys)) != len(keys)):
        raise ValueError(f"Unexpected or duplicate groups in {node.name}")


def child(node, name):
    result = node.group(name)
    if result is None:
        raise ValueError(f"Missing particle group {name}")
    return result


def vector(node, name, default=None):
    values = node.fields.get(name, default)
    if values is None or len(values) != 3:
        raise ValueError(f"Expected three {name} components")
    return [number(v) for v in values]


def properties(node, schema):
    result = {}
    for name, (low, high) in schema.items():
        values = node.fields.get(name, [])
        if len(values) != 1:
            raise ValueError(f"Expected one {name}")
        result[name] = (
            integer(values[0], minimum=low, maximum=high)
            if type(low) is int
            else number(values[0], low, high)
        )
    return result


def curve(node):
    if node.kind != "list" or node.fields or node.groups or len(node.rows) > 256:
        raise ValueError("Invalid particle curve")
    result = []
    for row in node.rows:
        if len(row) != 2:
            raise ValueError("Expected curve time/value pair")
        time, value = number(row[0], 0, 3600), number(row[1])
        if result and time < result[-1][0]:
            raise ValueError("Particle curve times must be nondecreasing")
        result.append([time, value])
    return result


def sample_curve(events, time):
    """Original scalar interpolation; exact duplicate times select the first key."""
    number(time, 0, 3600)
    if not events:
        return 0.0
    if time <= events[0][0]:
        return events[0][1]
    for (start, a), (end, b) in zip(events, events[1:], strict=False):
        if time <= end:
            return a + (b - a) * ((time - start) / (end - start))
    return events[-1][1]


def texture_path(effect_path, path):
    if any(ord(c) < 32 for c in path):
        raise ValueError("Invalid texture path characters")
    normalized = virtual_path(path)
    if re.match(r"^[A-Za-z]:", path) and not normalized.startswith("ymir work/"):
        raise ValueError("Texture drive path is outside the original asset root")
    if not normalized.startswith("ymir work/"):
        normalized = virtual_path(str(PurePosixPath(effect_path).parent / normalized))
    if not normalized.startswith("ymir work/") or not normalized.endswith((".dds", ".tga", ".png")):
        raise ValueError("Unsupported particle texture path")
    return normalized


def parse_particle_mse(text, effect_path):
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Particle script exceeds byte limit")
    effect_path = virtual_path(effect_path)
    if not effect_path.startswith("ymir work/") or not effect_path.endswith(".mse"):
        raise ValueError("Expected original virtual MSE path")
    return parse_particle_root(parse_legacy_script(text), effect_path)


def parse_particle_root(root, effect_path):
    """Validate a particle-only syntax tree selected by a complete effect adapter."""
    shape(
        root,
        {"BoundingSphereRadius", "BoundingSpherePosition"},
        {("group", "Particle")},
        repeated=True,
    )
    if not 1 <= len(root.groups) <= 32:
        raise ValueError("Expected 1–32 particle systems")
    sphere = properties(root, {"BoundingSphereRadius": (0.0, 100000.0)})
    systems = []
    for node in root.groups:
        shape(
            node,
            {"StartTime"},
            {
                ("list", "TimeEventPosition"),
                ("group", "EmitterProperty"),
                ("group", "ParticleProperty"),
            },
        )
        start = properties(node, {"StartTime": (0.0, 3600.0)})["StartTime"]
        positions = child(node, "TimeEventPosition")
        if (
            positions.kind != "list"
            or positions.groups
            or positions.fields
            or not 1 <= len(positions.rows) <= 256
        ):
            raise ValueError("Invalid particle position keys")
        position_keys = []
        position_controls = []
        for row in positions.rows:
            direct = len(row) == 5 and row[1] == "MOVING_TYPE_DIRECT"
            bezier = len(row) == 8 and row[1] == "MOVING_TYPE_BEZIER_CURVE"
            if not direct and not bezier:
                raise ValueError("Unsupported particle position interpolation")
            time = number(row[0], 0, 3600)
            if position_keys and time <= position_keys[-1][0]:
                raise ValueError("Particle position times must strictly increase")
            position_keys.append([time, *[number(v) for v in row[2:5]]])
            position_controls.append([number(v) for v in row[5:]] if bezier else [])
        emitter = child(node, "EmitterProperty")
        shape(
            emitter,
            set(EMITTER_FIELDS) | {"EmittingDirection", "EmittingSize", "EmittingRadius"},
            {("list", "TimeEvent" + n) for n in EMITTER_CURVES},
        )
        emission = properties(emitter, EMITTER_FIELDS)
        emission["EmittingDirection"] = vector(emitter, "EmittingDirection")
        emission["EmittingSize"] = vector(emitter, "EmittingSize", ["0"] * 3)
        radius = emitter.fields.get("EmittingRadius", ["0"])
        if len(radius) != 1:
            raise ValueError("Expected one emission radius")
        emission["EmittingRadius"] = number(radius[0], 0)
        emission["curves"] = {n: curve(child(emitter, "TimeEvent" + n)) for n in EMITTER_CURVES}
        particle = child(node, "ParticleProperty")
        shape(
            particle,
            PARTICLE_FIELDS,
            {("list", "TimeEvent" + n) for n in PARTICLE_CURVES} | {("list", "TextureFiles")},
        )
        presentation = properties(particle, PARTICLE_FIELDS)
        presentation["curves"] = {
            n: curve(child(particle, "TimeEvent" + n)) for n in PARTICLE_CURVES
        }
        textures = child(particle, "TextureFiles")
        if (
            textures.kind != "list"
            or textures.fields
            or textures.groups
            or not 1 <= len(textures.rows) <= 64
        ):
            raise ValueError("Expected bounded texture frame list")
        if any(len(row) != 1 for row in textures.rows):
            raise ValueError("Expected one texture per frame")
        presentation["textures"] = [texture_path(effect_path, row[0]) for row in textures.rows]
        channels = [
            presentation["curves"][n] for n in ("ColorRed", "ColorGreen", "ColorBlue", "Alpha")
        ]
        times = sorted({time for channel in channels for time, _ in channel})
        presentation["packed_color_keys"] = [
            [time, *[d3dx_color_byte(sample_curve(channel, time)) for channel in channels]]
            for time in times
        ]
        systems.append(
            {
                "start_seconds": start,
                "position_keys_cm": position_keys,
                **({"position_controls_cm": position_controls} if any(position_controls) else {}),
                "emitter": emission,
                "particle": presentation,
            }
        )
    return {
        "effect_path": effect_path,
        "bounding_radius_cm": sphere["BoundingSphereRadius"],
        "bounding_position_cm": vector(root, "BoundingSpherePosition"),
        "systems": systems,
    }
