"""Preserve every layer of selected mixed particle/mesh MSE effects."""

from dataclasses import asdict, replace

from content_formats import parse_legacy_script, virtual_path
from metin_effect_mesh import parse_mesh_root
from metin_particles import parse_particle_root


def parse_mixed_effect(text: str, effect_path: str) -> dict:
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Mixed effect exceeds byte limit")
    path = virtual_path(effect_path)
    if not path.startswith("ymir work/") or not path.endswith(".mse"):
        raise ValueError("Expected original virtual MSE path")
    root = parse_legacy_script(text)
    if root.rows or not 2 <= len(root.groups) <= 36:
        raise ValueError("Expected bounded mixed effect layers")
    groups = {"Particle": [], "Mesh": []}
    order = []
    for group in root.groups:
        if group.kind != "group" or group.name not in groups:
            raise ValueError("Unsupported mixed effect layer")
        order.append({"kind": group.name.lower(), "index": len(groups[group.name])})
        groups[group.name].append(group)
    if not all(groups.values()):
        raise ValueError("Mixed effect requires particles and meshes")
    particles = parse_particle_root(replace(root, groups=groups["Particle"]), path)
    meshes = parse_mesh_root(
        replace(root, groups=groups["Mesh"]), blend_pairs={(3, 2), (3, 8), (5, 2), (5, 6)}
    )
    return {
        "effect_path": path,
        "layer_order": order,
        "particles": particles,
        "mesh_effect": asdict(meshes),
        "runtime_status": "parsed-not-converted",
    }
