//! Compile the same character definitions packaged by the Godot client.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt::Write;
use std::fs;

const CATALOG: &str = "../client/assets/imported/characters/catalog.v1.json";

fn number(row: &Value, key: &str, min: u64, max: u64) -> Result<u64, String> {
    row[key]
        .as_u64()
        .filter(|value| (min..=max).contains(value))
        .ok_or_else(|| format!("Invalid character definition {key}"))
}

pub fn generate(bytes: &[u8]) -> Result<String, String> {
    let document: Value = serde_json::from_slice(bytes).map_err(|error| error.to_string())?;
    if document["schema"] != "mt2spacetime.characters" || document["version"] != 1 {
        return Err("Unsupported character catalog".into());
    }
    let classes = document["classes"].as_array().ok_or("Missing classes")?;
    if classes.len() != 4 {
        return Err("Expected four classic classes".into());
    }
    let mut output = String::from(
        "#[derive(Clone, Copy, Debug)]\n\
         pub struct CharacterClassDefinition {\n\
         pub id: u8, pub strength: u8, pub vitality: u8, pub dexterity: u8, pub intelligence: u8,\n\
         pub base_hp: u32, pub base_sp: u32, pub hp_per_vitality: u32, pub sp_per_intelligence: u32,\n\
         pub hp_gain_min: u32, pub hp_gain_max: u32, pub sp_gain_min: u32, pub sp_gain_max: u32,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct CharacterAppearanceDefinition {pub class_id: u8, pub sex: u8, pub actor_id: &'static str}\n",
    );
    writeln!(
        output,
        "pub const CHARACTER_CATALOG_HASH: &str = {:?};",
        format!("{:x}", Sha256::digest(bytes))
    )
    .unwrap();
    output.push_str("pub const CHARACTER_CLASSES: [CharacterClassDefinition; 4] = [\n");
    let mut variants = Vec::new();
    let mut races = BTreeSet::new();
    for (index, class) in classes.iter().enumerate() {
        if number(class, "class_id", 0, 3)? != index as u64 {
            return Err("Class definitions must be sorted by unique ID".into());
        }
        write!(output, "CharacterClassDefinition {{ id: {index}, ").unwrap();
        for key in [
            "strength",
            "vitality",
            "dexterity",
            "intelligence",
            "base_hp",
            "base_sp",
            "hp_per_vitality",
            "sp_per_intelligence",
            "hp_gain_min",
            "hp_gain_max",
            "sp_gain_min",
            "sp_gain_max",
        ] {
            let max = if ["strength", "vitality", "dexterity", "intelligence"].contains(&key) {
                90
            } else {
                10000
            };
            write!(
                output,
                "{key}: {},",
                number(&class["initial_points"], key, 1, max)?
            )
            .unwrap();
        }
        output.push_str("},\n");
        let appearances = class["variants"]
            .as_array()
            .ok_or("Missing class appearances")?;
        if appearances.len() != 2 {
            return Err("Expected both original class appearances".into());
        }
        for (sex, appearance) in appearances.iter().enumerate() {
            if number(appearance, "sex", 0, 1)? != sex as u64
                || !races.insert(number(appearance, "race_id", 0, 7)?)
            {
                return Err("Duplicate or unsorted character appearance".into());
            }
            let actor = appearance["actor_id"]
                .as_str()
                .filter(|id| id.starts_with("actor.player."))
                .ok_or("Invalid character actor identity")?;
            variants.push(format!("CharacterAppearanceDefinition {{class_id: {index}, sex: {sex}, actor_id: {actor:?}}}"));
        }
    }
    output.push_str("];\n");
    writeln!(
        output,
        "pub const CHARACTER_APPEARANCES: [CharacterAppearanceDefinition; 8] = [{}];",
        variants.join(",")
    )
    .unwrap();
    output.push_str(&basic_attacks(&document)?);
    Ok(output)
}

fn basic_attacks(document: &Value) -> Result<String, String> {
    let actors = document["actors"]
        .as_array()
        .ok_or("Missing character actors")?;
    let mut records = Vec::new();
    let mut ids = BTreeSet::new();
    for actor in actors {
        let actor_id = actor["id"].as_str().ok_or("Invalid actor ID")?;
        if actor_id == "actor.player.warrior-male" {
            // Gameplay retains the accepted Warrior profile; this copy adds intro clips.
            continue;
        }
        for mode in actor["modes"].as_array().ok_or("Missing actor motions")? {
            let mode_id = mode["id"].as_str().ok_or("Missing motion mode")?;
            let (actions, weapon): (&[&str], u32) = match mode_id {
                "general" => (&["normal_attack"], 0),
                "onehand" => (&["combo_1", "combo_2", "combo_3", "combo_4"], 10),
                _ => continue,
            };
            if weapon != 0 && mode["combo_chains"][0] != serde_json::json!(actions) {
                return Err("Unsupported source common combo registration".into());
            }
            for (step, action) in actions.iter().enumerate() {
                let motion = mode["motions"]
                    .as_array()
                    .ok_or("Missing motions")?
                    .iter()
                    .find(|motion| motion["action"] == *action && motion["variant"] == 1)
                    .ok_or("Missing first basic attack variant")?;
                let id = motion["action_id"].as_str().ok_or("Missing attack ID")?;
                if !id.starts_with(&format!("{actor_id}.{mode_id}.")) || !ids.insert(id) {
                    return Err("Duplicate or mismatched basic attack identity".into());
                }
                let duration = number(motion, "duration_us", 100_000, 1_600_000)?;
                let events = motion["events"].as_array().ok_or("Missing motion events")?;
                let hits: Vec<_> = events
                    .iter()
                    .filter(|event| event["kind"] == "attack_window")
                    .collect();
                if hits.len() != 1 {
                    return Err("Basic attack requires exactly one authored hit window".into());
                }
                let hit = hits[0];
                let area = area_expression(events, duration)?;
                // Original area finishers carry a disabled 0..0 ordinary window.
                // They must never schedule an additional single-target hit.
                let area_only = area != "None";
                let start = number(hit, "start_us", if area_only { 0 } else { 1 }, duration)?;
                let end = number(hit, "end_us", start, duration)?;
                if area_only && (step != 3 || start != 0 || end != 0 || hit["sample_count"] != 0) {
                    return Err(format!("Unsupported mixed ordinary/area hit: {id}"));
                }
                let invisible = number(&hit["source_parameters"], "invisible_us", 0, 1_000_000)?;
                let invisible = if area_only { 0 } else { invisible };
                let accumulation = motion["accumulation_m"]
                    .as_array()
                    .ok_or("Missing root accumulation")?;
                if accumulation.len() != 3 {
                    return Err("Invalid attack accumulation dimensions".into());
                }
                let vector: Vec<_> = accumulation
                    .iter()
                    .map(|v| {
                        v.as_f64()
                            .filter(|v| v.is_finite() && v.abs() <= 2.0)
                            .ok_or("Invalid root displacement")
                    })
                    .collect::<Result<_, _>>()?;
                if vector[1].abs() > 0.000001 {
                    return Err("Basic melee supports only horizontal root motion".into());
                }
                let root = if vector[0].hypot(vector[2]) < 0.000001 {
                    "None".into()
                } else {
                    format!(
                        "Some(RootMotionDefinition {{ endpoint_x_m: {:?}, endpoint_z_m: {:?}, duration_us: {duration} }})",
                        vector[0], vector[2]
                    )
                };
                let combo = if weapon != 0 && step < 3 {
                    let input = &motion["combo"];
                    let pre = number(input, "pre_input_us", 0, duration - 1)?;
                    let direct = number(input, "direct_input_us", pre + 1, duration - 1)?;
                    // Original Sura input limit extends beyond the clip. The shared
                    // chain expires at clip end, so this cannot extend the action.
                    let limit = number(input, "input_limit_us", direct, 1_600_000)?.min(duration);
                    if start >= direct {
                        return Err("Combo boundary precedes its captured hit".into());
                    }
                    format!(
                        "Some(ComboInputDefinition {{ pre_input_us: {pre}, direct_input_us: {direct}, input_limit_us: {limit}, link_us: 0 }})"
                    )
                } else {
                    "None".into()
                };
                let range = if area_only {
                    "0.0"
                } else {
                    "PLAYER_GENERAL_ATTACK.range_m"
                };
                records.push(format!("({actor_id:?}, {weapon}, AttackDefinition {{ id: {id:?}, duration_us: {duration}, cooldown_us: {duration}, ordinary_hit_invulnerability_us: {invisible}, hit_start_us: {start}, hit_end_us: {end}, range_m: {range}, combo_input: {combo}, root_motion: {root}, special_area: {area}, screen_wave: None }})"));
            }
        }
    }
    if records.len() != 27 {
        return Err("Expected seven unarmed attacks and five four-step sword chains".into());
    }
    Ok(format!(
        "pub const CHARACTER_BASIC_ATTACKS: [(&str, u32, AttackDefinition); 27] = [{}];\n",
        records.join(",")
    ))
}

fn area_expression(events: &[Value], duration: u64) -> Result<String, String> {
    let areas: Vec<_> = events
        .iter()
        .filter(|event| event["kind"] == "attack_area")
        .collect();
    if areas.is_empty() {
        return Ok("None".into());
    }
    if areas.len() != 1 {
        return Err("Only one authored melee area is supported".into());
    }
    let area = areas[0];
    let start = number(area, "start_us", 1, duration)?;
    let end = number(area, "end_us", start, duration)?;
    let spheres = area["spheres"].as_array().ok_or("Missing area geometry")?;
    if spheres.len() != 1
        || spheres[0]["radius_m"] != 1.0
        || spheres[0]["position_m"].as_array().is_none_or(|v| {
            v.len() != 3
                || v[0].as_f64().is_none_or(|x| x.abs() > 0.000001)
                || v[1] != 0.0
                || v[2] != -1.2
        })
        || area["attack_type"] != 0
        || area["hitting_type"] != 1
        || area["collision_type"] != 0
        || area["external_force"] != 17.0
        || area["invisible_us"] != 300000
        || end - start != 200000
        || ![659316, 434359].contains(&start)
    {
        return Err("Unsupported original melee area policy".into());
    }
    let frame = start * 60 / 1_000_000;
    let activation = ((frame + 1) * 1_000_000).div_ceil(60);
    Ok(format!(
        "Some(SpecialAreaDefinition {{ authored_start_us: {start}, legacy_dispatch_frame: {frame}, activation_offset_us: {activation}, duration_us: 200000, local_center_x_m: 0.0, local_center_z_m: -1.2, radius_m: 1.0, max_targets: 16, hit_once_per_life: true, hit_type: 1, invulnerability_us: 300000, knockback: KnockbackDefinition {{ source_external_force: 17.0, unobstructed_distance_m: 4.732, duration_us: 1000000 }} }})"
    ))
}

pub fn build() -> String {
    println!("cargo:rerun-if-changed={CATALOG}");
    match fs::read(CATALOG)
        .map_err(|error| error.to_string())
        .and_then(|bytes| generate(&bytes))
    {
        Ok(generated) => generated,
        Err(error) => format!(
            "compile_error!({:?});",
            format!(
                "Character content: {error}. Run tools/import_character_content.py and tools/build_character_catalog.py."
            )
        ),
    }
}
