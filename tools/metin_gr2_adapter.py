"""Adapt the legacy float curves found in the pinned Metin2 GR2 fixtures.

Carbon handles GR2 relocation/decompression. This module maps old inline curves
and samples their spline controls at the source animation's frame interval.
"""

import math

from carbon_gr2.curves import decode_curve, sample_curve
from carbon_granny import reader


def adapt_model_placement(path, graph):
    # Mesh vertices are in model space; the legacy skeleton omits this placement.
    # Animation root tracks already include their animated model-space transform.
    from mathutils import Matrix, Quaternion, Vector

    raw = reader.read_raw(path.read_bytes())
    placement = raw.file_info["Models"][0]["InitialPlacement"]
    x, y, z, w = placement["orientation"]
    transform = (
        Matrix.Translation(Vector(placement["position"]))
        @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
    )
    seen = set()
    for skeleton in [*graph["skeletons"], *(m["skeleton"] for m in graph["models"])]:
        for bone in skeleton["bones"]:
            if bone["parentIndex"] >= 0 or id(bone) in seen:
                continue
            seen.add(id(bone))
            x, y, z, w = bone.get("orientation", [0, 0, 0, 1])
            local = (
                Matrix.Translation(Vector(bone.get("position", [0, 0, 0])))
                @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            )
            corrected = transform @ local
            rotation = corrected.to_quaternion()
            bone["position"] = list(corrected.to_translation())
            bone["orientation"] = [rotation.x, rotation.y, rotation.z, rotation.w]


def adapt_legacy_animation(path, graph):
    raw = reader.read_raw(path.read_bytes())
    for original, animation in zip(raw.file_info["Animations"], graph["animations"], strict=True):
        duration = animation["duration"]
        step = animation["timeStep"]
        times = [min(i * step, duration) for i in range(round(duration / step) + 1)]
        for raw_group, group in zip(original["TrackGroups"], animation["trackGroups"], strict=True):
            for raw_track, track in zip(
                raw_group["TransformTracks"], group["transformTracks"], strict=True
            ):
                for source, target, dimension in (
                    ("PositionCurve", "position", 3),
                    ("OrientationCurve", "orientation", 4),
                    ("ScaleShearCurve", "scaleShear", 9),
                ):
                    curve = raw_track[source]
                    if "CurveData" in curve:
                        continue
                    knots = [v["Real32"] for v in curve["Knots"]]
                    controls = [v["Real32"] for v in curve["Controls"]]
                    if not knots and not controls:
                        track[target] = {"format": 2, "degree": 0}
                        continue
                    if len(controls) != len(knots) * dimension:
                        raise ValueError(
                            f"Invalid legacy curve dimensions: {track['name']} {source}"
                        )
                    if curve["Degree"] not in (0, 1, 2):
                        raise ValueError(f"Untested spline degree {curve['Degree']}")
                    decoded = decode_curve(
                        {
                            "format": 1,
                            "degree": curve["Degree"],
                            "knots": knots,
                            "controls": controls,
                        },
                        dimension,
                    )
                    sampled = []
                    for time in times:
                        value = list(
                            sample_curve([0.0] * dimension, decoded, time, duration=duration)
                        )
                        if dimension == 4:
                            length = math.sqrt(sum(v * v for v in value))
                            if length < 1e-8:
                                raise ValueError("Invalid zero quaternion")
                            value = [v / length for v in value]
                        sampled.extend(value)
                    track[target] = {
                        "format": 1,
                        "degree": 1,
                        "dimension": dimension,
                        "knots": times,
                        "controls": sampled,
                    }
