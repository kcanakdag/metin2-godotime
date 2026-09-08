"""Emit candidate Rust combat tables using the server's existing definition types."""

import json

from mob_gameplay import integer, number


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
    physical, actions, kinds = [], [], []
    seen = set()
    for mob in catalog["mobs"]:
        vnum = integer(mob["vnum"], 1, 2**32 - 1, "vnum")
        if vnum in seen:
            raise ValueError("Duplicate registry vnum")
        seen.add(vnum)
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
    if not 1 <= len(seen) <= 128:
        raise ValueError("Expected 1..128 combat registry definitions")
    return (
        "// Generated candidate combat tables; not a complete spawn/AI/reward registry.\n"
        "use crate::definitions::{MobPhysicalDefinition, WeightedMobAttack, AttackDefinition};\n"
        "pub const PHYSICAL: &[MobPhysicalDefinition] = &[\n" + ",\n".join(physical) + "];\n"
        "pub const KINDS: &[(u32, crate::mob_damage::Kind)] = &[\n" + ",\n".join(kinds) + "];\n"
        "pub const ATTACKS: &[(u32, &[WeightedMobAttack])] = &[\n" + ",\n".join(actions) + "];\n"
    )
