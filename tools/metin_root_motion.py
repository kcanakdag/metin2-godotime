"""Bounded raw-GR2 root-motion metadata extraction for the selected combo prefix."""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

from fetch_test_assets import CARBON_COMMIT, ROOT

POLICY_ID = "linear-endpoint-approx-v1"
COORDINATE_CONVERSION = "source-cm-(x,z,-y)/100-then-fixture-yaw-180"
MSA_COMPONENT_TOLERANCE_M = 0.00005
MAX_DURATION_US = 1_600_000
MAX_SOURCE_COMPONENT_CM = 200.0
MAX_INITIAL_PLACEMENT_COMPONENT_CM = 300.0
MAX_ENDPOINT_COMPONENT_M = 2.0
CARBON_READER_SHA256 = "c3c8698c5987b6783586cc312e291e63eb315f8a5b0968b4f556219688a0fdce"

EXPECTED_INPUTS = {
    "actor.player.warrior-male.onehand.combo_1": {
        "gr2_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_01.gr2",
        "msa_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_01.msa",
        "gr2": "520fa66815e9757e44ec7f0a7edb12fcd100a149ed9693521fb97b74d728193c",
        "gr2_bytes": 34235,
        "msa": "3659a78e07801bca57a38864092331743b7f30bb269c31d40b92595993d9ccfe",
        "msa_bytes": 1954,
    },
    "actor.player.warrior-male.onehand.combo_2": {
        "gr2_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_02.gr2",
        "msa_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_02.msa",
        "gr2": "8fa914f7d83041c002d7a3b020dfe52091e1cf3793602e65df46a69b9c2cccaa",
        "gr2_bytes": 34765,
        "msa": "fa25fb6ed11338dfac1ff00e673157a766e39fec2b814e1dacb962259d8c7308",
        "msa_bytes": 1784,
    },
    "actor.player.warrior-male.onehand.combo_3": {
        "gr2_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_03.gr2",
        "msa_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_03.msa",
        "gr2": "f1882194129c6c0a17212be8dfe3299e20dbed98035dc3bbdd5e3be52f0ce3b9",
        "gr2_bytes": 34658,
        "msa": "69f4e729aea572006b1ed2d826f1f9a35108c06cb608f8e68ec97f42cef13961",
        "msa_bytes": 4444,
    },
    "actor.player.warrior-male.onehand.combo_4": {
        "gr2_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_04.gr2",
        "msa_path": "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_04.msa",
        "gr2": "7ff6abe943ab2f1e0066be53b89dc9b6aa97d4d773c5ef97c441d4b03bbfd4b2",
        "gr2_bytes": 35664,
        "msa": "df48b7b4bd06668cfb63723aa59666a999310ea3f32101dec50b0050bd837c9f",
        "msa_bytes": 1674,
    },
}

COMBO4_ACTION_ID = "actor.player.warrior-male.onehand.combo_4"
COMBO4_RAW_ENDPOINT_M = [0.0, 0.0, -1.1964712524414062]
COMBO4_MSA_ENDPOINT_M = [0.1289, 0.0, -1.0552]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _decimal(value: float) -> str:
    return format(value, ".17g")


def _decimal_vector(values: list[float]) -> list[str]:
    return [_decimal(value) for value in values]


def _exact_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an exact integer")
    return value


def _finite_vector(value: object, length: int, bound: float, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} must contain exactly {length} values")
    result = []
    for component in value:
        if type(component) not in {int, float} or not math.isfinite(component):
            raise ValueError(f"{label} must contain finite numbers")
        component = float(component)
        if abs(component) > bound:
            raise ValueError(f"{label} exceeds the supported bound")
        result.append(component)
    return result


def source_cm_to_output_actor_local_m(source: list[float], yaw_degrees: float) -> list[float]:
    """Apply the fixed source-to-Godot mapping and fixture yaw exactly once."""
    if type(yaw_degrees) not in {int, float} or float(yaw_degrees) != 180.0:
        raise ValueError("Selected root motion requires the fixed 180-degree fixture yaw")
    x, y, z = _finite_vector(source, 3, MAX_SOURCE_COMPONENT_CM, "GR2 LoopTranslation")
    # Source cm -> Godot metres is (x,z,-y)/100. The selected fixture then has
    # an exact 180-degree yaw, (-x,y,-z), avoiding a second axis conversion.
    result = [-x / 100.0, z / 100.0, y / 100.0]
    return [0.0 if component == 0.0 else component for component in result]


def validate_raw_metadata(
    file_info: object,
    *,
    action_id: str,
    duration_us: int,
    msa_accumulation_m: list[float],
    yaw_degrees: float,
) -> dict:
    """Validate one raw Carbon type tree and return the bounded trusted projection."""
    if action_id not in EXPECTED_INPUTS:
        raise ValueError(f"Unsupported root-motion action {action_id!r}")
    if type(duration_us) is not int or not 0 < duration_us <= MAX_DURATION_US:
        raise ValueError("Root-motion action duration is outside the supported bound")
    if not isinstance(file_info, dict):
        raise ValueError("Raw GR2 metadata must be an object")
    animations = file_info.get("Animations")
    if not isinstance(animations, list) or len(animations) != 1:
        raise ValueError("Selected root-motion GR2 must contain exactly one animation")
    animation = animations[0]
    if not isinstance(animation, dict):
        raise ValueError("Selected root-motion animation must be an object")
    raw_duration = animation.get("Duration")
    if type(raw_duration) not in {int, float} or not math.isfinite(raw_duration):
        raise ValueError("Raw GR2 animation duration must be finite")
    raw_duration = float(raw_duration)
    if not 0.0 < raw_duration <= MAX_DURATION_US / 1_000_000:
        raise ValueError("Raw GR2 animation duration is outside the supported bound")
    rounded_duration_us = round(raw_duration * 1_000_000)
    if rounded_duration_us != duration_us:
        raise ValueError("Raw GR2 duration does not round to the MSA/action duration")
    groups = animation.get("TrackGroups")
    if not isinstance(groups, list) or len(groups) != 1:
        raise ValueError("Selected root-motion GR2 must contain exactly one track group")
    group = groups[0]
    if not isinstance(group, dict) or group.get("Name") != "Bip01":
        raise ValueError("Selected root-motion track group must be Bip01")
    if _exact_int(group.get("AccumulationFlags"), "AccumulationFlags") != 3:
        raise ValueError("Selected root-motion AccumulationFlags must equal 3")
    if (
        "PeriodicLoop" not in group
        or "RootMotion" not in group
        or group["PeriodicLoop"] is not None
        or group["RootMotion"] is not None
    ):
        raise ValueError("PeriodicLoop and RootMotion must be null for the selected fixture")

    source_endpoint = _finite_vector(
        group.get("LoopTranslation"),
        3,
        MAX_SOURCE_COMPONENT_CM,
        "GR2 LoopTranslation",
    )
    endpoint = source_cm_to_output_actor_local_m(source_endpoint, yaw_degrees)
    if any(abs(value) > MAX_ENDPOINT_COMPONENT_M for value in endpoint):
        raise ValueError("Converted root-motion endpoint exceeds the supported bound")
    if endpoint[1] != 0.0:
        raise ValueError("Selected root-motion fixture must have zero vertical endpoint")
    msa_endpoint = _finite_vector(
        msa_accumulation_m,
        3,
        MAX_ENDPOINT_COMPONENT_M,
        "MSA accumulation",
    )
    # The existing generic yaw helper uses sin(pi), which leaves a tiny X value
    # for an exact source-axis vector. Preserve the exact fixed-fixture zero.
    msa_endpoint = [round(component, 4) for component in msa_endpoint]
    msa_endpoint = [0.0 if component == 0.0 else component for component in msa_endpoint]
    differences = [msa_endpoint[index] - endpoint[index] for index in range(3)]
    if action_id == COMBO4_ACTION_ID:
        if endpoint != COMBO4_RAW_ENDPOINT_M or msa_endpoint != COMBO4_MSA_ENDPOINT_M:
            raise ValueError("Pinned combo_4 raw/MSA endpoint discrepancy changed")
        msa_validation = "pinned-combo4-discrepancy-exception"
    else:
        if any(abs(value) > MSA_COMPONENT_TOLERANCE_M for value in differences):
            raise ValueError("MSA accumulation does not corroborate the raw GR2 endpoint")
        msa_validation = "strict-rounded-corroboration"

    placement = group.get("InitialPlacement")
    if not isinstance(placement, dict):
        raise ValueError("Raw GR2 InitialPlacement must be an object")
    placement_flags = _exact_int(placement.get("flags"), "InitialPlacement.flags")
    if not 0 <= placement_flags <= 0xFFFFFFFF:
        raise ValueError("InitialPlacement.flags is outside the supported bound")
    placement_position = _finite_vector(
        placement.get("position"),
        3,
        MAX_INITIAL_PLACEMENT_COMPONENT_CM,
        "InitialPlacement.position",
    )
    placement_orientation = _finite_vector(
        placement.get("orientation"), 4, 2.0, "InitialPlacement.orientation"
    )
    return {
        "animation_count": 1,
        "animation_duration_s_raw": raw_duration,
        "animation_duration_us_rounded": rounded_duration_us,
        "track_group_count": 1,
        "track_group_name": "Bip01",
        "accumulation_flags": 3,
        "loop_translation_source_cm": source_endpoint,
        "endpoint_output_actor_local_godot_m": endpoint,
        "periodic_loop": None,
        "root_motion": None,
        "initial_placement": {
            "flags": placement_flags,
            "position_source_cm": placement_position,
            "orientation_xyzw": placement_orientation,
        },
        "msa_accumulation_output_actor_local_godot_m": msa_endpoint,
        "msa_discrepancy_output_actor_local_godot_m": differences,
        "msa_validation": msa_validation,
    }


def _carbon_reader():
    carbon_root = ROOT / ".cache" / f"tools-blender-{CARBON_COMMIT}"
    reader_path = carbon_root / "packages/carbon-granny/src/carbon_granny/reader.py"
    if not reader_path.is_file():
        raise FileNotFoundError("Pinned Carbon reader missing; run make assets first")
    if _sha256(reader_path.read_bytes()) != CARBON_READER_SHA256:
        raise ValueError("Pinned Carbon raw reader hash mismatch")
    package_root = str(reader_path.parents[1])
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
    from carbon_granny import reader

    reader.GR2_MAGICS["b867b0caf86db10f84728c7e5e19001e"] = 4
    return reader


def extract_root_motion(
    gr2_path: Path,
    msa_path: Path,
    *,
    source_gr2: str,
    source_msa: str,
    action_id: str,
    duration_us: int,
    msa_accumulation_m: list[float],
    yaw_degrees: float,
) -> dict:
    """Read and project one of the three pinned raw GR2 combo motions."""
    expected = EXPECTED_INPUTS.get(action_id)
    if expected is None:
        raise ValueError(f"Unsupported root-motion action {action_id!r}")
    gr2_content = gr2_path.read_bytes()
    msa_content = msa_path.read_bytes()
    gr2_sha256 = _sha256(gr2_content)
    msa_sha256 = _sha256(msa_content)
    if source_gr2 != expected["gr2_path"] or source_msa != expected["msa_path"]:
        raise ValueError(f"Pinned root-motion source path mismatch for {action_id}")
    if (
        gr2_sha256 != expected["gr2"]
        or msa_sha256 != expected["msa"]
        or len(gr2_content) != expected["gr2_bytes"]
        or len(msa_content) != expected["msa_bytes"]
    ):
        raise ValueError(f"Pinned root-motion input hash mismatch for {action_id}")
    raw = _carbon_reader().read_raw(gr2_content).file_info
    projection = validate_raw_metadata(
        raw,
        action_id=action_id,
        duration_us=duration_us,
        msa_accumulation_m=msa_accumulation_m,
        yaw_degrees=yaw_degrees,
    )
    projection["animation_duration_s_raw_decimal"] = _decimal(
        projection.pop("animation_duration_s_raw")
    )
    for old, new in (
        ("loop_translation_source_cm", "loop_translation_source_cm_decimal"),
        (
            "endpoint_output_actor_local_godot_m",
            "endpoint_output_actor_local_godot_m_decimal",
        ),
        (
            "msa_accumulation_output_actor_local_godot_m",
            "msa_accumulation_output_actor_local_godot_m_decimal",
        ),
        (
            "msa_discrepancy_output_actor_local_godot_m",
            "msa_discrepancy_output_actor_local_godot_m_decimal",
        ),
    ):
        projection[new] = _decimal_vector(projection.pop(old))
    placement = projection["initial_placement"]
    placement["position_source_cm_decimal"] = _decimal_vector(placement.pop("position_source_cm"))
    placement["orientation_xyzw_decimal"] = _decimal_vector(placement.pop("orientation_xyzw"))
    return {
        "action_id": action_id,
        "source_gr2": {
            "path": source_gr2,
            "sha256": gr2_sha256,
            "bytes": len(gr2_content),
        },
        "source_msa": {
            "path": source_msa,
            "sha256": msa_sha256,
            "bytes": len(msa_content),
        },
        "carbon_reader": {
            "commit": CARBON_COMMIT,
            "sha256": CARBON_READER_SHA256,
        },
        **projection,
    }
