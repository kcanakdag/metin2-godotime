"""Original default monster shape and explicit material skin substitutions."""

from pathlib import PurePosixPath

from content_formats import integer, one, parse_legacy_script, virtual_path


def default_shape(text):
    root = parse_legacy_script(text)
    if one(root, "ScriptType") != "RaceDataScript":
        raise ValueError("Expected monster race script")
    base = virtual_path(one(root, "BaseModelFileName") or "")
    shape = root.group("ShapeData")
    result = {"index": 0, "model": base, "skin_remaps": []}
    if shape is None:
        return result
    rows = shape.groups_with_prefix("ShapeData")
    if integer(one(shape, "ShapeDataCount") or "0") != len(rows):
        raise ValueError("Monster shape count differs from its records")
    indices = [integer(one(row, "ShapeIndex") or "") for row in rows]
    if len(set(indices)) != len(indices):
        raise ValueError("Duplicate monster shape index")
    if not rows:
        return result
    if 0 not in indices:
        raise ValueError("Monster default shape zero is missing")
    row = rows[indices.index(0)]
    if set(row.fields) - {"ShapeIndex", "Model", "SourceSkin", "TargetSkin"} or row.groups:
        raise ValueError("Unsupported default monster shape fields")
    directory = virtual_path((one(shape, "PathName") or "").rstrip("/\\"))
    model = one(row, "Model", required=False)
    if model:
        result["model"] = virtual_path(str(PurePosixPath(directory) / model))
    source = one(row, "SourceSkin", required=False)
    target = one(row, "TargetSkin", required=False)
    if bool(source) != bool(target):
        raise ValueError("Default monster skin needs both source and target")
    if source:
        result["skin_remaps"] = [
            {
                "source": virtual_path(str(PurePosixPath(directory) / source)),
                "target": virtual_path(str(PurePosixPath(directory) / target)),
            }
        ]
    return result


def apply_skin_remaps(bindings, remaps):
    substitutions = {}
    for row in remaps:
        source, target = row["source"], row["target"]
        if source in substitutions or source not in bindings.values():
            raise ValueError("Monster skin remap is duplicated or has no bound source texture")
        substitutions[source] = target
    # Simultaneous substitution: A->B and B->C must not accidentally turn A into C.
    return {key: substitutions.get(value, value) for key, value in bindings.items()}
