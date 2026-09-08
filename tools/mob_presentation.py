"""Public converted wildlife actors for the shared Godot actor catalog."""

import copy

from content_compile import _client_motion
from mob_gameplay import validate_actor_reports


def public_motion(motion):
    result = _client_motion(motion, None)
    # The shared PvE presentation uses canonical death action names. Preserve
    # original action IDs and clip names when mapping the source registrations.
    result["action"] = {"front_dead": "front_death", "back_dead": "back_death"}.get(
        result["action"], result["action"]
    )
    return result


def compile_presentation(normalized, report, gameplay_hash):
    validate_actor_reports(normalized["actors"], report["artifacts"])
    actors, artifacts = [], []
    reports = {a["id"]: a for a in report["artifacts"]}
    for actor in normalized["actors"]:
        artifact = reports[actor["id"]]
        path = "res://assets/imported/mobs/" + artifact["relative_path"]
        artifacts.append(
            {
                **{
                    k: copy.deepcopy(artifact[k])
                    for k in (
                        "id",
                        "type",
                        "sha256",
                        "bytes",
                        "mesh_count",
                        "textured_mesh_count",
                        "vertices",
                        "triangles",
                        "bounds_m",
                        "bones",
                        "skeleton_signature",
                    )
                },
                "path": path,
            }
        )
        actors.append(
            {
                **{k: actor[k] for k in ("id", "kind", "vnum", "name", "model_key")},
                "model": {"artifact_id": actor["id"], "path": path},
                "skeleton_signature": artifact["skeleton_signature"],
                "attachment_bones": copy.deepcopy(actor["attachment_bones"]),
                "forward": actor["orientation"]["output_forward"],
                "motion_vector_space": actor["motion_vector_space"],
                "modes": [
                    {
                        "id": mode["id"],
                        "required_item_vnums": [],
                        "combo_chains": [],
                        "motions": [public_motion(m) for m in mode["motions"]],
                    }
                    for mode in actor["modes"]
                ],
            }
        )
    return {
        "schema": "mt2spacetime.mob-presentation-candidate",
        "version": 1,
        "gameplay_hash": gameplay_hash,
        "actors": actors,
        "artifacts": artifacts,
    }
