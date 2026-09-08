"""Original regeneration entries and their transitive mob-group dependencies."""

import re

from content_formats import parse_legacy_script


def runtime_policy():
    """Reviewed overworld behavior; dungeon/stone spawning has separate rules."""
    return {
        "scope": "persistent-overworld",
        "zero_interval": "disabled-including-initial-spawn",
        "initial_spawn": "immediate",
        "first_tick_jitter_us": [0, 16_000_000],
        "first_tick_jitter_step_us": 1_000_000,
        "following_ticks": "fixed-entry-interval",
        "refill": "attempt-missing-units-once-per-tick",
        "group_unit_owner": "leader",
        "unit_release": "owner-destruction",
        "surviving_members": "retain-independent-lives",
        "range_attempts_per_member": 16,
        "group_leader_failure": "abort-group",
        "group_member_failure": "skip-member",
        "group_next_bounds": "last-successful-member-position",
        "group_bound_offsets_cm": [300, 500],
        "group_bound_offset_draws": "independent-left-top-right-bottom",
        "range_heading_degrees": [0, 360],
        "range_source_direction": "ignored",
        "range_source_section": "ignored-use-zero",
        "range_regen_exceptions": "disabled-in-pinned-source",
    }


def integer(token, low=0, high=2**31 - 1):
    if not re.fullmatch(r"-?[0-9]+", token):
        raise ValueError("Population field must be an integer")
    value = int(token)
    if not low <= value <= high:
        raise ValueError("Population integer exceeds supported bounds")
    return value


def interval_us(token):
    if not re.fullmatch(r"(?:[0-9]+[hms])+", token):
        raise ValueError("Unsupported source regeneration interval")
    seconds = sum(
        int(n) * {"h": 3600, "m": 60, "s": 1}[unit]
        for n, unit in re.findall(r"([0-9]+)([hms])", token)
    )
    if seconds > 86400:
        raise ValueError("Regeneration interval exceeds one day")
    return seconds * 1_000_000


def group_index(text):
    root = parse_legacy_script("\n".join(line.split("//", 1)[0] for line in text.splitlines()))
    result = {}
    for node in root.groups:
        fields = {key.lower(): value for key, value in node.fields.items()}
        if len(fields) != len(node.fields) or len(fields.get("vnum", [])) != 1:
            raise ValueError("Invalid group identity fields")
        vnum = integer(fields["vnum"][0], 1)
        result.setdefault(vnum, []).append(fields)
    return result


def selected(index, vnum):
    rows = index.get(vnum, [])
    if len(rows) != 1:
        raise ValueError(f"Missing or ambiguous referenced group {vnum}")
    return rows[0]


def slots(fields):
    # Original loader reads 1..255 and stops at the first missing slot.
    active = []
    for slot in range(1, 256):
        if str(slot) not in fields:
            break
        active.append((slot, fields[str(slot)]))
    used = {str(slot) for slot, _ in active}
    ignored = {key: row for key, row in fields.items() if key.isdecimal() and key not in used}
    return active, ignored


def compile_population(regen, groups_text, choices_text, selected_vnums):
    groups, choices = group_index(groups_text), group_index(choices_text)
    group_rows, choice_rows, mob_vnums = {}, {}, set()

    def resolve_group(vnum):
        if vnum in group_rows:
            return group_rows[vnum]
        fields = selected(groups, vnum)
        leader = fields.get("leader", [])
        if len(leader) != 2:
            raise ValueError("Group requires a name and leader vnum")
        members = [{"slot": 0, "leader": True, "vnum": integer(leader[1], 1)}]
        active, ignored = slots(fields)
        for slot, row in active:
            if len(row) != 2:
                raise ValueError("Group member requires a name and mob vnum")
            members.append({"slot": slot, "leader": False, "vnum": integer(row[1], 1)})
        mob_vnums.update(m["vnum"] for m in members)
        result = {"vnum": vnum, "members": members, "ignored_after_slot_gap": ignored}
        group_rows[vnum] = result
        return result

    def resolve_choice(vnum):
        if vnum in choice_rows:
            return choice_rows[vnum]
        active, ignored = slots(selected(choices, vnum))
        if not active:
            raise ValueError("Referenced group selector is empty")
        variants = []
        for slot, row in active:
            if len(row) not in (1, 2):
                raise ValueError("Group selector requires a group vnum and optional weight")
            group_vnum = integer(row[0], 1)
            resolve_group(group_vnum)
            variants.append(
                {
                    "slot": slot,
                    "group_vnum": group_vnum,
                    "source_weight": integer(row[1], -(2**31)) if len(row) == 2 else 1,
                    # This pinned LoadGroupGroup reads prob but calls AddMember(vnum)
                    # without passing it. Do not invent weighted behavior from the file.
                    "effective_weight": 1,
                }
            )
        result = {"vnum": vnum, "variants": variants, "ignored_after_slot_gap": ignored}
        choice_rows[vnum] = result
        return result

    entries = []
    for line_number, original in enumerate(regen.splitlines(), 1):
        tokens = original.split("//", 1)[0].split()
        if not tokens:
            continue
        if len(tokens) != 11:
            raise ValueError(f"Regeneration line {line_number} requires eleven fields")
        kind, x, y, rx, ry, section, heading, interval, chance, count, ref = tokens
        if kind not in ("m", "g", "ga", "r"):
            raise ValueError(f"Unsupported regeneration family {kind}")
        x, y, rx, ry = (integer(v, high=1_000_000) for v in (x, y, rx, ry))
        if min(x - rx, y - ry) < 0:
            raise ValueError("Population rectangle crosses negative map coordinates")
        if kind != "m" and rx == 0 and ry == 0:
            raise ValueError("Point group entries use a distinct original direct-spawn path")
        reference = integer(ref, 1)
        if kind == "r":
            selection = resolve_choice(reference)
            variants = [resolve_group(v["group_vnum"])["members"] for v in selection["variants"]]
        elif kind in ("g", "ga"):
            variants = [resolve_group(reference)["members"]]
        else:
            mob_vnums.add(reference)
            variants = [[{"vnum": reference}]]
        required = sorted({m["vnum"] for variant in variants for m in variant})
        maximum = integer(count, high=1000)
        period = interval_us(interval)
        entries.append(
            {
                "source_line": line_number,
                "family": kind,
                "reference_vnum": reference,
                "bounds_cm": [(x - rx) * 100, (y - ry) * 100, (x + rx) * 100, (y + ry) * 100],
                "section": integer(section, high=255),
                "source_direction": integer(heading, high=8),
                "interval_us": period,
                "enabled": period != 0,
                "source_percent": integer(chance, high=100),
                "percent_policy": "ignored-by-original-loader",
                "max_live_units": maximum,
                "forced_aggressive": kind == "ga",
                "required_mob_vnums": required,
                "initial_member_upper_bound": maximum * max(len(v) for v in variants)
                if period
                else 0,
                "covered_by_selection": set(required).issubset(selected_vnums),
            }
        )
    if not entries:
        raise ValueError("Population contains no spawn entries")
    return {
        "runtime_policy": runtime_policy(),
        "entries": entries,
        "groups": [group_rows[k] for k in sorted(group_rows)],
        "group_selectors": [choice_rows[k] for k in sorted(choice_rows)],
        "required_mob_vnums": sorted(mob_vnums),
        "outside_selected_vnums": sorted(mob_vnums - set(selected_vnums)),
        "initial_member_upper_bound": sum(e["initial_member_upper_bound"] for e in entries),
        "covered_entries": sum(e["covered_by_selection"] for e in entries),
    }
