"""Typed presentation-only adapter for original type-1 MSA effect events."""

from content_formats import finite_number, seconds_to_us, virtual_path

_REQUIRED = {
    "MotionEventType",
    "StartingTime",
    "AttachingEnable",
    "AttachingBoneName",
    "EffectFileName",
    "EffectPosition",
}
_OPTIONAL = {"IndependentFlag", "FollowingEnable"}


def motion_effect(event: dict, duration_us: int) -> dict:
    """Preserve source timing and explicit root/bone follow versus capture semantics."""
    fields = event["fields"]
    if not _REQUIRED <= fields.keys() or fields.keys() - _REQUIRED - _OPTIONAL:
        raise ValueError("Unsupported motion-effect fields")
    for key, values in fields.items():
        if not isinstance(values, list) or len(values) != (3 if key == "EffectPosition" else 1):
            raise ValueError("Invalid motion-effect field arity")
        if any(not isinstance(value, str) or any(ord(c) < 32 for c in value) for value in values):
            raise ValueError("Invalid motion-effect field text")
    if event.get("event_type") != 1 or fields["MotionEventType"] != ["1"]:
        raise ValueError("Expected type-1 motion effect")
    start = seconds_to_us(fields["StartingTime"][0])
    if start != event["start_us"] or not 0 <= start <= duration_us:
        raise ValueError("Motion-effect time differs from clip metadata")
    flags = {}
    for key in ("IndependentFlag", "AttachingEnable", "FollowingEnable"):
        value = fields.get(key, ["0"])[0]
        if value not in ("0", "1"):
            raise ValueError("Motion-effect flags must be boolean")
        flags[key] = value == "1"
    path = virtual_path(fields["EffectFileName"][0])
    if not path.startswith("ymir work/") or not path.endswith(".mse"):
        raise ValueError("Effect must reference an original-root MSE")
    position = [finite_number(value) for value in fields["EffectPosition"]]
    if any(abs(value) > 100000 for value in position):
        raise ValueError("Effect position exceeds source bounds")
    bone = fields["AttachingBoneName"][0]
    if not bone or len(bone) > 128:
        raise ValueError("Invalid motion-effect bone")
    if flags["IndependentFlag"]:
        attachment = "capture_root"
    elif flags["AttachingEnable"]:
        attachment = "follow_bone" if flags["FollowingEnable"] else "capture_bone"
    else:
        # The original non-attaching branch creates an actor-root attachment.
        attachment = "follow_root"
    return {
        "source_event": event["event_name"],
        "start_us": start,
        "effect_path": path,
        "attachment": attachment,
        "bone": bone if attachment.endswith("bone") else "",
        "position_m": [position[0] / 100, position[2] / 100, -position[1] / 100],
    }


def resolve_attachment(effect: dict, source_bones: set[str], converted_bones: set[str]) -> dict:
    """Resolve legacy missing-bone behavior while detecting conversion loss."""
    result = {**effect, "requested_bone": effect["bone"], "enabled": True}
    if effect["attachment"] not in ("follow_bone", "capture_bone"):
        return result
    bone = effect["bone"]
    if bone in source_bones:
        if bone not in converted_bones:
            raise ValueError(f"Conversion lost effect attachment bone: {bone}")
        return result
    if bone in converted_bones:
        raise ValueError(f"Converted effect bone is absent from source skeleton: {bone}")
    if effect["attachment"] == "follow_bone":
        result.update(attachment="follow_root", bone="", resolution="original-missing-bone-root")
    else:
        result.update(enabled=False, resolution="original-missing-bone-skip")
    return result


def main():
    """Extract explicitly selected local MSA files without installing runtime content."""
    import argparse
    import hashlib
    import json
    from pathlib import Path

    from content_formats import parse_msa

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msa", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [path.resolve() for path in args.msa]
    if not 1 <= len(paths) <= 256 or len(set(paths)) != len(paths):
        parser.error("Select 1..256 distinct MSA files")
    motions = []
    for path in paths:
        raw = path.read_bytes()
        parsed = parse_msa(raw.decode(), ignore_legacy_link_time=True, allow_post_clip_area=True)
        effects = [
            motion_effect(event, parsed["duration_us"])
            for event in parsed["unsupported"]
            if event.get("event_type") == 1
        ]
        motions.append(
            {
                "source_msa": str(path),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "duration_us": parsed["duration_us"],
                "effects": effects,
                "remaining_unsupported": [
                    e for e in parsed["unsupported"] if e.get("event_type") != 1
                ],
            }
        )
    result = {
        "schema": "mt2spacetime.motion-effect-candidate",
        "version": 1,
        "runtime_status": "candidate-not-installed",
        "motions": motions,
    }
    with args.output.open("x") as destination:
        json.dump(result, destination, indent=2)
        destination.write("\n")
    print(json.dumps({"motions": len(motions), "effects": sum(len(m["effects"]) for m in motions)}))


if __name__ == "__main__":
    main()
