//! Compile ordinary-monster physical stats without substituting another mob's values.
use serde_json::Value;
use std::collections::BTreeSet;
use std::fmt::Write;

fn integer(root: &Value, key: &str, low: u64, high: u64) -> Result<u64, String> {
    root[key]
        .as_u64()
        .filter(|v| (low..=high).contains(v))
        .ok_or_else(|| format!("Invalid mob physical field {key}"))
}

pub fn generate(root: &Value) -> Result<String, String> {
    if root["schema_version"] != 1 || root["compiler_version"] != "mob-content-v1" {
        return Err("Expected normalized mob content".into());
    }
    let mobs = root["mob_catalog"]
        .as_array()
        .filter(|rows| !rows.is_empty() && rows.len() <= 128)
        .ok_or("Expected 1..128 mob definitions")?;
    let actors = root["actors"]
        .as_array()
        .ok_or("Missing converted mob actors")?;
    let (mut ids, mut vnums) = (BTreeSet::new(), BTreeSet::new());
    let mut out =
        String::from("pub const MOB_PHYSICAL_DEFINITIONS: &[MobPhysicalDefinition] = &[\n");
    for mob in mobs {
        let vnum = integer(mob, "vnum", 1, u32::MAX.into())?;
        let id = mob["id"]
            .as_str()
            .filter(|id| id.starts_with("actor.mob.") && id.len() <= 128)
            .ok_or("Invalid physical mob actor ID")?;
        if !ids.insert(id)
            || !vnums.insert(vnum)
            || actors
                .iter()
                .filter(|a| a["id"] == id && a["vnum"] == vnum && a["kind"] == "mob")
                .count()
                != 1
        {
            return Err("Duplicate mob identity or missing converted actor".into());
        }
        // CHARACTER::Attack dispatches these source battle types to battle_melee_attack.
        if !matches!(
            mob["battle_type"].as_str(),
            Some("MELEE" | "POWER" | "TANKER" | "SUPER_POWER" | "SUPER_TANKER")
        ) {
            return Err("This physical mob handler requires original melee attacks".into());
        }
        let stats = &mob["stats"];
        let level = integer(stats, "level", 1, 99)?;
        let st = integer(stats, "st", 0, 90)?;
        let ht = integer(stats, "ht", 0, 90)?;
        let dx = integer(stats, "dx", 0, 90)?;
        let defense = integer(stats, "def", 0, 10000)?;
        let low = integer(stats, "damage_min", 0, 10000)?;
        let high = integer(stats, "damage_max", low, 10000)?;
        let multiplier = stats["damage_multiplier"]
            .as_f64()
            .filter(|v| v.is_finite() && *v > 0.0 && *v <= 100.0)
            .ok_or("Invalid mob damage multiplier")? as f32;
        if multiplier <= 0.0 {
            return Err("Mob damage multiplier underflows runtime precision".into());
        }
        let modifiers = mob["combat_modifiers"]
            .as_object()
            .ok_or("Missing mob combat modifiers")?;
        for (key, value) in modifiers {
            if !matches!(
                key.as_str(),
                "resist_sword" | "resist_fan" | "enchant_critical"
            ) && value.as_i64() != Some(0)
            {
                return Err(format!(
                    "Mob {vnum} requires unsupported physical mechanic {key}"
                ));
            }
        }
        let sword = integer(&mob["combat_modifiers"], "resist_sword", 0, 100)?;
        let fan = integer(&mob["combat_modifiers"], "resist_fan", 0, 100)?;
        let critical = integer(&mob["combat_modifiers"], "enchant_critical", 0, 100)?;
        writeln!(out, "MobPhysicalDefinition {{ actor_id: {id:?}, vnum: {vnum}, level: {level}, strength: {st}, vitality: {ht}, dexterity: {dx}, proto_defense: {defense}, power_min: {low}, power_max: {high}, damage_multiplier: {multiplier:?}, sword_resistance_percent: {sword}, fan_resistance_percent: {fan}, critical_percent: {critical} }},").unwrap();
    }
    out.push_str("];\n");
    Ok(out)
}
