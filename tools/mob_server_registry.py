"""Emit candidate Rust combat tables using the server's existing definition types."""

import json
import struct

from mob_gameplay import integer, number

# ``EMobRank`` in the pinned ``common/length.h``. Only the first four ranks
# receive common-drop rows, but the protocol carries the original value so a
# future boss content slice does not need a schema change.
MOB_RANKS = ("PAWN", "S_PAWN", "KNIGHT", "S_KNIGHT", "BOSS", "KING")


def mob_rank(source):
    """Original ``EMobRank`` value of a mob prototype row."""
    rank = source.get("rank")
    if rank not in MOB_RANKS:
        raise ValueError(f"Missing or unsupported mob rank: {rank!r}")
    return MOB_RANKS.index(rank)


def immunity_flags(source):
    """Pinned ProtoReader flag order; preserve all bits for future affect handlers."""
    names = ("STUN", "SLOW", "FALL", "CURSE", "POISON", "TERROR", "REFLECT")
    flags = source["flags"].get("immune_flag")
    if (
        not isinstance(flags, list)
        or any(not isinstance(flag, str) or flag not in names for flag in flags)
        or len(set(flags)) != len(flags)
    ):
        raise ValueError("Missing or invalid species immunity flags")
    return sum(1 << names.index(flag) for flag in flags)


def rust_text(value):
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Expected printable ASCII server identity")
    return json.dumps(value)


def compile_registry(catalog):
    physical, actions, kinds, species, mobs = [], [], [], [], []
    seen = set()
    for mob in catalog["mobs"]:
        vnum = integer(mob["vnum"], 1, 2**32 - 1, "vnum")
        if vnum in seen:
            raise ValueError("Duplicate registry vnum")
        seen.add(vnum)
        species.append(species_record(mob))
        source = mob["source_definition"]
        stats, modifiers = source["stats"], source["combat_modifiers"]
        kind = {
            "MELEE": "Normal",
            "POWER": "Normal",
            "TANKER": "Normal",
            "SUPER_POWER": "Normal",
            "SUPER_TANKER": "Normal",
            "RANGE": "NormalRange",
            "MAGIC": "Magic",
        }.get(source["battle_type"])
        if kind is None:
            raise ValueError("Unsupported mob battle type")
        actor = rust_text(mob["id"])
        if source["id"] != mob["id"] or source["vnum"] != vnum:
            raise ValueError("Registry source identity mismatch")
        fields = {"actor_id": actor, "vnum": str(vnum)}
        for target, key, low, high in (
            ("level", "level", 1, 99),
            ("strength", "st", 0, 90),
            ("vitality", "ht", 0, 90),
            ("dexterity", "dx", 0, 90),
            ("proto_defense", "def", 0, 10000),
            ("power_min", "damage_min", 0, 10000),
            ("power_max", "damage_max", 0, 10000),
        ):
            fields[target] = str(integer(stats[key], low, high, key))
        if stats["damage_min"] > stats["damage_max"]:
            raise ValueError("Reversed mob damage range")
        fields["damage_multiplier"] = repr(
            float(number(stats["damage_multiplier"], 0.001, 100, "multiplier"))
        )
        for target, key in (
            ("sword_resistance_percent", "resist_sword"),
            ("fan_resistance_percent", "resist_fan"),
            ("critical_percent", "enchant_critical"),
            ("penetrate_percent", "enchant_penetrate"),
        ):
            fields[target] = str(integer(modifiers[key], 0, 100, key))
        physical.append(
            "MobPhysicalDefinition { " + ", ".join(f"{k}: {v}" for k, v in fields.items()) + " }"
        )
        kinds.append(f"({vnum}, crate::mob_damage::Kind::{kind})")
        rows, ids, total = [], set(), 0
        if not 1 <= len(mob["attacks"]) <= 16:
            raise ValueError("Expected 1..16 weighted mob actions")
        for attack in mob["attacks"]:
            action_id = attack["id"]
            if not action_id.startswith(mob["id"] + ".general.normal_attack") or action_id in ids:
                raise ValueError("Invalid or duplicate mob action identity")
            ids.add(action_id)
            weight = integer(attack["weight"], 1, 100, "weight")
            total += weight
            duration = integer(attack["playback_duration_us"], 1, 60_000_000, "duration")
            cooldown = integer(attack["server_cooldown_us"], 1, 60_000_000, "cooldown")
            expected = {"Normal": "normal_melee", "NormalRange": "normal_range", "Magic": "magic"}[
                kind
            ]
            if attack["damage_kind"] != expected:
                raise ValueError("Source battle type differs from attack damage kind")
            windows = attack["windows"]
            start = end = invulnerability = 0
            if kind == "Normal":
                if (
                    attack["delivery"] != "melee"
                    or len(windows) != 1
                    or attack["projectile_launches"]
                ):
                    raise ValueError("Runtime requires one melee hit window")
                window = windows[0]
                start = integer(window["playback_start_us"], 0, duration - 1, "hit start")
                end = integer(window["playback_end_us"], start + 1, duration, "hit end")
                invulnerability = integer(
                    window["source_parameters"]["invisible_us"], 0, 60_000_000, "invulnerability"
                )
            elif attack["delivery"] != "projectile" or windows or not attack["projectile_launches"]:
                raise ValueError("Projectile dispatch requires launches and no melee windows")
            reach = float(number(mob["attack_range_m"], 0.01, 100, "reach"))
            rows.append(
                f"WeightedMobAttack {{ weight: {weight}, attack: AttackDefinition {{ "
                f"id: {rust_text(action_id)}, duration_us: {duration}, cooldown_us: {cooldown}, "
                f"ordinary_hit_invulnerability_us: {invulnerability}, hit_start_us: {start}, "
                f"hit_end_us: {end}, range_m: {reach!r}, combo_input: None, root_motion: None, "
                "special_area: None, screen_wave: None, ordinary_knockback: None } }"
            )
        if total != 100:
            raise ValueError("Mob action weights must total 100")
        actions.append(f"({vnum}, &[" + ",\n".join(rows) + "])")
        sight = integer(stats["aggressive_sight"], 1, 100000, "aggressive sight") / 100.0
        index = len(mobs)
        mobs.append(
            f"MobDefinition {{ species: SPECIES[{index}], damage_kind: KINDS[{index}].1, "
            f"attacks: ATTACKS[{index}].1, acquisition_range_m: {sight!r}, "
            "chase_home_range_m: 0.0, target_chase_limit_cm: Some(4000), respawn_us: 10000000 }"
        )
    if not 1 <= len(seen) <= 128:
        raise ValueError("Expected 1..128 combat registry definitions")
    return (
        "// Generated candidate mob definitions; full world/party AI installation is separate.\n"
        "use crate::definitions::{MobPhysicalDefinition, WeightedMobAttack, AttackDefinition, MobSpeciesDefinition, DefendingSphereDefinition, MonsterReactionDefinition, MobDefinition};\n"
        "pub const SPECIES: &[MobSpeciesDefinition] = &[\n" + ",\n".join(species) + "];\n"
        "pub const PHYSICAL: &[MobPhysicalDefinition] = &[\n" + ",\n".join(physical) + "];\n"
        "pub const KINDS: &[(u32, crate::mob_damage::Kind)] = &[\n" + ",\n".join(kinds) + "];\n"
        "pub const ATTACKS: &[(u32, &[WeightedMobAttack])] = &[\n" + ",\n".join(actions) + "];\n"
        "pub const MOBS: &[MobDefinition] = &[\n" + ",\n".join(mobs) + "];\n"
    )


def species_record(mob):
    """Species facts only; acquisition/leash/respawn belong to world policy."""
    source = mob["source_definition"]
    rewards = source["rewards"]
    flags = source["flags"]["ai_flag"]
    if (
        not isinstance(flags, list)
        or len(set(flags)) != len(flags)
        or any(f != "AGGR" for f in flags)
    ):
        raise ValueError("Unsupported species AI flags")
    fields = {
        "aggressive": "true" if "AGGR" in flags else "false",
        "immunity_flags": str(immunity_flags(source)),
        "vnum": str(integer(mob["vnum"], 1, 2**32 - 1, "species vnum")),
        "actor_id": rust_text(mob["id"]),
        "name": rust_text(mob["name"]),
        "model_key": rust_text(mob["model_key"]),
        "motion_set": rust_text(mob["id"] + ".general"),
        "rank": str(mob_rank(source)),
        "level": str(integer(mob["level"], 1, 99, "species level")),
        "health": str(integer(mob["health"], 1, 65535, "species health")),
        "attack_range_m": repr(float(number(mob["attack_range_m"], 0.01, 100, "range"))),
        "move_speed_mps": "f32::from_bits(0x%08x)"
        % struct.unpack(
            ">I",
            struct.pack(
                ">f", number(mob["movement"]["server_speed_mps"], 0.001, 100, "move speed")
            ),
        )[0],
    }
    if mob["health"] != source["stats"]["max_hp"] or mob["level"] != source["stats"]["level"]:
        raise ValueError("Species stats differ from source")
    for target, key in (("experience", "exp"), ("gold_min", "gold_min"), ("gold_max", "gold_max")):
        fields[target] = str(integer(rewards[key], 0, 2**32 - 1, key))
    if rewards["gold_min"] > rewards["gold_max"]:
        raise ValueError("Reversed species gold range")
    sphere = mob["defending_sphere"]
    if len(sphere["position_m"]) != 3:
        raise ValueError("Defending sphere needs three coordinates")
    coordinates = [repr(float(number(v, -10, 10, "sphere center"))) for v in sphere["position_m"]]
    radius = repr(float(number(sphere["radius_m"], 0.01, 10, "sphere radius")))
    fields["defending_sphere"] = (
        f"DefendingSphereDefinition {{ local_center_x_m: {coordinates[0]}, "
        f"local_center_y_m: {coordinates[1]}, local_center_z_m: {coordinates[2]}, radius_m: {radius} }}"
    )
    for action in ("front_knockdown", "front_standup", "back_knockdown"):
        reaction = mob["reactions"][action]
        if not reaction["id"].startswith(mob["id"] + ".general." + action):
            raise ValueError("Reaction belongs to another species or action")
        duration = integer(reaction["duration_us"], 1, 60_000_000, "reaction duration")
        fields[action] = (
            f"MonsterReactionDefinition {{ id: {rust_text(reaction['id'])}, duration_us: {duration} }}"
        )
    return "MobSpeciesDefinition { " + ", ".join(f"{k}: {v}" for k, v in fields.items()) + " }"
