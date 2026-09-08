"""Normalize original single-bone rigid meshes into standard glTF skinning."""

from __future__ import annotations

import math
from collections import Counter


def unused_material_slot(raw_mesh: dict, index: int) -> bool:
    """An empty exporter slot is harmless only if topology proves no face uses it."""
    groups = raw_mesh.get("PrimaryTopology", {}).get("Groups")
    return isinstance(groups, list) and not any(
        group["MaterialIndex"] == index and group["TriCount"] != 0 for group in groups
    )


def material_slots(raw_mesh: dict, imported_groups: list[int]) -> list[int]:
    """Resolve Carbon's per-face group indices before Blender clears its slots."""
    groups = raw_mesh["PrimaryTopology"]["Groups"]
    count = len(raw_mesh["MaterialBindings"])
    actual = Counter(imported_groups)
    if any(type(index) is not int or not 0 <= index < len(groups) for index in actual):
        raise ValueError("Imported face references an unknown GR2 material group")
    for index, group in enumerate(groups):
        slot = group["MaterialIndex"]
        if type(slot) is not int or not 0 <= slot < count:
            raise ValueError("GR2 group references an unknown material binding")
        if actual[index] != group["TriCount"]:
            raise ValueError("Imported face count differs from its GR2 material group")
    return [groups[index]["MaterialIndex"] for index in imported_groups]


def validate_shared_skin_bones(actor: dict, part: dict, weighted: set[str]) -> dict:
    """Validate used bones in model space, allowing unused part export helpers.

    Parent-local rest transforms can differ while the final weighted-bone poses
    are identical. Compare the exact world rest matrices used by the converter.
    Positions are centimetres; tolerances only cover source float roundoff.
    """
    if not weighted or not weighted <= actor.keys() or not weighted <= part.keys():
        raise ValueError("Weighted skin bone does not resolve on the shared skeleton")
    max_position_error = 0.0
    for name in sorted(weighted):
        first, second = actor[name], part[name]
        for matrix in (first, second):
            if (
                len(matrix) != 4
                or any(len(row) != 4 for row in matrix)
                or any(
                    type(v) not in (int, float) or not math.isfinite(v)
                    for row in matrix
                    for v in row
                )
            ):
                raise ValueError("Invalid skin rest matrix")
        for i in range(4):
            for j in range(4):
                error = abs(first[i][j] - second[i][j])
                tolerance = 0.001 if j == 3 and i < 3 else 0.00001
                if error > tolerance:
                    raise ValueError(f"Skin world rest transform differs on {name}")
                if j == 3 and i < 3:
                    max_position_error = max(max_position_error, error)
    return {
        "checked_shared_bones": sorted(weighted),
        "max_rest_position_error_cm": max_position_error,
    }


def normalize_rigid_bindings(graph: dict) -> list[dict]:
    """Preserve model-space vertices; a rigid mesh uses one composite bone matrix.

    The original renderer's ModelInstanceUpdate.cpp applies the first binding's
    pose/inverse-bind composite to rigid meshes. Unit weights express the same
    operation through Blender's armature modifier and glTF, without a runtime
    Granny dependency or asset-specific attachment offsets.
    """
    skeletons = graph.get("skeletons", [])
    if len(skeletons) != 1:
        raise ValueError("Actor skinning requires one skeleton")
    names = {bone["name"] for bone in skeletons[0]["bones"]}
    records = []
    for mesh in graph["meshes"]:
        vertex = mesh["vertex"]
        indices, weights = vertex.get("blendIndice", []), vertex.get("blendWeight", [])
        if indices and weights:
            continue
        if indices or weights:
            raise ValueError(f"Incomplete skin attributes on {mesh['name']}")
        bindings = mesh.get("boneBindings", [])
        if len(bindings) != 1 or bindings[0].get("name") not in names:
            raise ValueError(f"Rigid mesh {mesh['name']} needs one resolved bone binding")
        count, remainder = divmod(len(vertex["position"]), 3)
        if remainder or not count:
            raise ValueError(f"Invalid rigid vertex positions on {mesh['name']}")
        vertex["blendIndice"] = [0, 0, 0, 0] * count
        vertex["blendWeight"] = [1.0, 0.0, 0.0, 0.0] * count
        records.append({"mesh": mesh["name"], "bone": bindings[0]["name"], "vertices": count})
    return records
