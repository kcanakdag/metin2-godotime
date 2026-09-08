"""Validate original projectile launch declarations without inventing hit windows."""

import math

from content_formats import virtual_path


def compile_launches(normalized):
    motions = {
        motion["action_id"]: (actor["id"], motion)
        for actor in normalized["actors"]
        for mode in actor["modes"]
        for motion in mode["motions"]
    }
    result, seen = {}, set()
    for event in normalized["deferred_motion_events"]:
        actor, motion = motions.get(event.get("action_id"), (None, None))
        if (
            actor != event.get("actor_id")
            or motion is None
            or motion["action"] != "normal_attack"
            or event.get("source") != motion["source_msa"]
            or event.get("kind") != "motion_event"
            or event.get("event_type") != 6
        ):
            raise ValueError("Deferred event is not a supported ordinary projectile launch")
        identity = (event["action_id"], event.get("event_name"))
        if not isinstance(identity[1], str) or not identity[1] or identity in seen:
            raise ValueError("Duplicate or invalid projectile source event")
        seen.add(identity)
        timestamp = event["start_us"]
        if (
            type(timestamp) is not int
            or not 0 <= timestamp <= motion["duration_us"]
            or event["end_us"] != timestamp
        ):
            raise ValueError("Projectile launch must be an instantaneous event inside its motion")
        fields = event["fields"]
        expected = {
            "AttachingBoneName",
            "AttachingEnable",
            "FlyFileName",
            "FlyPosition",
            "MotionEventType",
            "StartingTime",
        }
        if set(fields) != expected or any(
            not isinstance(values, list)
            or len(values) != (3 if key == "FlyPosition" else 1)
            or any(not isinstance(v, str) for v in values)
            for key, values in fields.items()
        ):
            raise ValueError("Unsupported projectile source fields")
        if fields["MotionEventType"] != ["6"] or fields["AttachingEnable"][0] not in ("0", "1"):
            raise ValueError("Invalid projectile type or attachment flag")
        start = float(fields["StartingTime"][0])
        if not math.isfinite(start) or abs(start * 1_000_000 - timestamp) > 1:
            raise ValueError("Projectile timestamp differs from original metadata")
        position = [float(v) for v in fields["FlyPosition"]]
        if any(not math.isfinite(v) or abs(v) > 10000 for v in position):
            raise ValueError("Projectile source position exceeds finite bounds")
        bone = fields["AttachingBoneName"][0]
        attached = fields["AttachingEnable"] == ["1"]
        if len(bone) > 128 or any(ord(c) < 32 for c in bone) or (attached and not bone):
            raise ValueError("Invalid projectile attachment bone")
        path = virtual_path(fields["FlyFileName"][0])
        if not path.startswith("ymir work/") or not path.endswith(".msf"):
            raise ValueError("Projectile must reference an original fly-system definition")
        result.setdefault(event["action_id"], []).append(
            {
                "source_event": event["event_name"],
                "source_msa": event["source"],
                "start_us": timestamp,
                "fly_definition": path,
                "attached": attached,
                "bone": bone,
                "source_position_cm": position,
                "semantics": "visual-launch-not-server-damage-authorization",
            }
        )
    return result
