"""Pinned RaceManager motion registration, including explicit ignored source rows."""

from npc_definitions import motion_groups

# Canonical action names for the motion indices in __LoadRaceMotionList.
REGISTERED = {"spawn": "spawn", "stop": "stop", "dead": "front_dead"}
for _action, _count in (
    ("wait", 2),
    ("walk", 2),
    ("run", 2),
    ("normal_attack", 2),
    ("front_damage", 3),
    ("front_dead", 2),
    ("front_knockdown", 1),
    ("front_standup", 1),
    ("back_damage", 1),
    ("back_dead", 2),
    ("back_knockdown", 1),
    ("back_standup", 1),
):
    REGISTERED[_action] = _action
    REGISTERED.update({f"{_action}{i}": _action for i in range(1, _count + 1)})
for _prefix, _count, _base in (("combo_attack", 3, 1), ("special", 6, 1)):
    for _index in range(_count):
        REGISTERED[_prefix + (str(_index) if _index else "")] = (
            f"combo_{_index + _base}" if _prefix == "combo_attack" else f"special_{_index + _base}"
        )
REGISTERED.update({f"skill{i}": f"skill_{120 + i}" for i in range(1, 6)})


def registered_action(source):
    # Exact names win. The source then tries dropping one and two trailing
    # characters, not stripping every trailing digit before the exact lookup.
    for candidate in (source, source[:-1], source[:-2]):
        if candidate in REGISTERED:
            return REGISTERED[candidate]
    return None


def compile_motion_groups(rows):
    active, ignored = [], []
    for row in rows:
        if row["mode"] != "general":
            raise ValueError("Mob importer supports only the general source motion mode")
        action = registered_action(row["action"])
        if action is None:
            ignored.append({**row, "reason": "unregistered-by-pinned-client-motion-loader"})
        else:
            active.append({**row, "action": action})
    aliases = {name: name for name in REGISTERED.values()}
    return motion_groups(active, aliases=aliases), ignored
