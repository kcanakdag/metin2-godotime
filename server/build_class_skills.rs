//! Strict compiler for the full classic skill catalog and bounded formula programs.
use serde_json::Value;
use std::collections::BTreeSet;
use std::fmt::Write;

fn integer(value: &Value, low: u64, high: u64) -> Result<u64, String> {
    value
        .as_u64()
        .filter(|v| (low..=high).contains(v))
        .ok_or("Invalid class skill integer".into())
}

fn hit_windows(variant: &Value, duration: u64) -> Result<Vec<[u64; 2]>, String> {
    let hits = variant["hits"]
        .as_array()
        .filter(|hits| hits.len() <= 32)
        .ok_or("Invalid skill hit windows")?;
    let mut result = Vec::new();
    for hit in hits {
        if !matches!(hit["kind"].as_str(), Some("attack_area" | "attack_window")) {
            return Err("Unknown skill hit window kind".into());
        }
        let start = integer(&hit["start_us"], 0, duration)?;
        let end = integer(&hit["end_us"], start, duration + 10_000_000)?;
        if !variant["activation_us"]
            .as_array()
            .is_some_and(|times| times.iter().any(|time| time.as_u64() == Some(start)))
        {
            return Err("Skill hit window has no matching activation".into());
        }
        result.push([start, end]);
    }
    Ok(result)
}

fn affect(value: &Value) -> Result<Option<u16>, String> {
    let text = value.as_str().ok_or("Invalid skill affect identifier")?;
    if text.is_empty() {
        return Ok(None);
    }
    let id = text
        .parse::<u16>()
        .ok()
        .filter(|id| *id > 0 && id.to_string() == text)
        .ok_or("Invalid skill affect identifier")?;
    Ok(Some(id))
}

pub fn program(value: &Value) -> Result<String, String> {
    let ops = value
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 128)
        .ok_or("Invalid formula program length")?;
    let mut stack = 0_i32;
    let mut result = Vec::new();
    for instruction in ops {
        let fields = instruction
            .as_object()
            .ok_or("Formula instruction must be an object")?;
        let op = instruction["op"].as_str().ok_or("Missing formula opcode")?;
        let rendered = match op {
            "constant" => {
                if fields.len() != 2 {
                    return Err("Unexpected constant fields".into());
                }
                let v = instruction["value"]
                    .as_f64()
                    .filter(|v| v.is_finite() && v.abs() <= 1_000_000.0)
                    .ok_or("Invalid formula constant")?;
                stack += 1;
                format!("Op::Constant({v:?})")
            }
            "variable" => {
                if fields.len() != 2 {
                    return Err("Unexpected variable fields".into());
                }
                let index = integer(&instruction["index"], 0, 9)?;
                stack += 1;
                format!("Op::Variable({index})")
            }
            "neg" | "floor" => {
                if fields.len() != 1 || stack < 1 {
                    return Err("Invalid unary instruction".into());
                }
                format!("Op::{}", if op == "neg" { "Neg" } else { "Floor" })
            }
            "add" | "sub" | "mul" | "div" | "number" => {
                if fields.len() != 1 || stack < 2 {
                    return Err("Invalid binary instruction".into());
                }
                stack -= 1;
                let name = match op {
                    "add" => "Add",
                    "sub" => "Sub",
                    "mul" => "Mul",
                    "div" => "Div",
                    _ => "Number",
                };
                format!("Op::{name}")
            }
            _ => return Err("Unsupported formula opcode".into()),
        };
        if stack > 32 {
            return Err("Formula stack exceeds bounds".into());
        }
        result.push(rendered);
    }
    if stack != 1 {
        return Err("Formula does not produce one result".into());
    }
    Ok(format!("&[{}]", result.join(",")))
}

pub fn validate(root: &Value) -> Result<(), String> {
    if root["schema"] != "mt2spacetime.skills" || root["version"] != 2 {
        return Err("Unsupported class skill catalog".into());
    }
    let powers = root["rank_power_percent"]
        .as_array()
        .filter(|values| values.len() == 21)
        .ok_or("Expected 21 skill rank powers")?;
    let mut previous_power = 0;
    for (rank, value) in powers.iter().enumerate() {
        let power = integer(value, 0, 100)?;
        if (rank == 0 && power != 0) || (rank > 0 && power <= previous_power) {
            return Err("Skill rank powers must start at zero and strictly increase".into());
        }
        previous_power = power;
    }
    let skills = root["skills"]
        .as_array()
        .filter(|a| a.len() == 44)
        .ok_or("Expected all 44 classic class skills")?;
    let mut ids = BTreeSet::new();
    for skill in skills {
        let id = integer(&skill["vnum"], 1, 111)?;
        let class = integer(&skill["class_id"], 0, 3)?;
        let group = integer(&skill["group"], 1, 2)?;
        let base = class * 30 + (group - 1) * 15;
        if id <= base || id > base + if class < 2 { 5 } else { 6 } || !ids.insert(id) {
            return Err("Invalid or duplicate class/group skill identity".into());
        }
        integer(&skill["minimum_level"], 1, 99)?;
        integer(&skill["maximum_rank"], 1, 20)?;
        if !matches!(
            skill["attribute"].as_str(),
            Some("NORMAL" | "MELEE" | "RANGE" | "MAGIC")
        ) {
            return Err("Unsupported skill damage attribute".into());
        }
        affect(&skill["affect"])?;
        affect(&skill["secondary_affect"])?;
        if !matches!(
            skill["handler"].as_str(),
            Some("damage" | "periodic_damage" | "buff" | "healing")
        ) {
            return Err("Unsupported class skill handler".into());
        }
        if !matches!(
            skill["target"].as_str(),
            Some("self" | "monster" | "friendly")
        ) {
            return Err("Unsupported class skill target".into());
        }
        for (field, maximum) in [("rank_costs", 10000), ("rank_cooldowns_us", 600_000_000)] {
            let values = skill[field]
                .as_array()
                .filter(|a| a.len() == 21)
                .ok_or("Invalid rank lookup table")?;
            for value in values {
                integer(value, 0, maximum)?;
            }
        }
        for field in [
            "formula",
            "sp_cost",
            "duration",
            "sp_upkeep",
            "cooldown",
            "secondary_formula",
            "secondary_duration",
            "splash_scale",
        ] {
            program(&skill["programs"][field])?;
        }
        let variants = skill["variants"]
            .as_array()
            .filter(|a| a.len() == 2)
            .ok_or("Skill requires both appearances")?;
        let mut actors = BTreeSet::new();
        for variant in variants {
            let actor = variant["actor_id"].as_str().ok_or("Missing skill actor")?;
            let expected_class = ["warrior", "ninja", "sura", "shaman"][class as usize];
            if ![
                format!("actor.player.{expected_class}-male"),
                format!("actor.player.{expected_class}-female"),
            ]
            .iter()
            .any(|v| v == actor)
                || !actors.insert(actor)
                || variant["action_id"] != format!("{actor}.general.skill_{id}")
            {
                return Err("Skill motion/appearance does not belong to its class".into());
            }
            let duration = integer(&variant["duration_us"], 1, 3_200_000)?;
            hit_windows(variant, duration)?;
            let root = variant["root_m"]
                .as_array()
                .filter(|a| a.len() == 3)
                .ok_or("Invalid skill root vector")?;
            for value in root {
                if !value
                    .as_f64()
                    .is_some_and(|v| v.is_finite() && v.abs() <= 8.0)
                {
                    return Err("Skill root exceeds bounds".into());
                }
            }
            let activations = variant["activation_us"]
                .as_array()
                .filter(|a| a.len() <= 32)
                .ok_or("Invalid activation list")?;
            if skill["handler"] == "damage" && activations.is_empty() {
                return Err("Damage skill has no activation".into());
            }
            let mut previous = None;
            for value in activations {
                let time = integer(value, 0, duration)?;
                if previous.is_some_and(|p| p >= time) {
                    return Err("Skill activations must be unique and ordered".into());
                }
                previous = Some(time);
            }
        }
    }
    Ok(())
}

pub fn generate(root: &Value) -> Result<String, String> {
    validate(root)?;
    let mut out = String::from("use crate::skill_formula::Op;\n");
    out.push_str("#[derive(Clone,Copy,Debug,PartialEq,Eq)] pub enum SkillHandler { Damage, PeriodicDamage, Buff, Healing }\n");
    out.push_str("#[derive(Clone,Copy,Debug,PartialEq,Eq)] pub enum SkillTarget { SelfOnly, Monster, Friendly }\n");
    out.push_str("#[derive(Clone,Copy,Debug,PartialEq,Eq)] pub enum SkillAttribute { Normal, Melee, Range, Magic }\n");
    writeln!(
        out,
        "pub const CLASS_SKILL_RANK_POWERS: [u8; 21] = {:?};",
        root["rank_power_percent"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_u64().unwrap())
            .collect::<Vec<_>>()
    )
    .unwrap();
    out.push_str("#[derive(Clone,Copy,Debug)] pub struct SkillPrograms { pub amount:&'static [Op],pub secondary:&'static [Op],pub duration:&'static [Op],pub secondary_duration:&'static [Op],pub upkeep:&'static [Op],pub splash_scale:&'static [Op] }\n");
    out.push_str("#[derive(Clone,Copy,Debug)] pub struct ClassSkillDefinition { pub vnum:u16,pub class_id:u8,pub group:u8,pub minimum_level:u8,pub maximum_rank:u8,pub handler:SkillHandler,pub target:SkillTarget,pub attribute:SkillAttribute,pub affect:Option<u16>,pub secondary_affect:Option<u16>,pub point:&'static str,pub secondary_point:&'static str,pub flags:&'static [&'static str],pub weapon_limits:&'static [&'static str],pub rank_costs:[u32;21],pub rank_cooldowns_us:[i64;21],pub programs:SkillPrograms,pub radius_m:f32,pub range_m:f32,pub max_targets:u8 }\n");
    out.push_str("#[derive(Clone,Copy,Debug)] pub struct ClassSkillMotion {pub skill_vnum:u16,pub actor_id:&'static str,pub action_id:&'static str,pub duration_us:i64,pub root_m:[f32;3],pub activation_us:&'static [i64],pub hit_windows_us:&'static [[i64;2]]}\n");
    let mut definitions = Vec::new();
    let mut motions = Vec::new();
    for skill in root["skills"].as_array().unwrap() {
        let id = skill["vnum"].as_u64().unwrap();
        let class = skill["class_id"].as_u64().unwrap();
        let group = skill["group"].as_u64().unwrap();
        let minimum_level = skill["minimum_level"].as_u64().unwrap();
        let maximum_rank = skill["maximum_rank"].as_u64().unwrap();
        let attribute = match skill["attribute"].as_str().unwrap() {
            "MELEE" => "Melee",
            "RANGE" => "Range",
            "MAGIC" => "Magic",
            _ => "Normal",
        };
        let primary_affect = affect(&skill["affect"])?;
        let secondary_affect = affect(&skill["secondary_affect"])?;
        let handler = match skill["handler"].as_str().unwrap() {
            "damage" => "Damage",
            "periodic_damage" => "PeriodicDamage",
            "buff" => "Buff",
            _ => "Healing",
        };
        let target = match skill["target"].as_str().unwrap() {
            "self" => "SelfOnly",
            "monster" => "Monster",
            _ => "Friendly",
        };
        let costs = skill["rank_costs"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_u64().unwrap())
            .collect::<Vec<_>>();
        let cooldowns = skill["rank_cooldowns_us"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_u64().unwrap())
            .collect::<Vec<_>>();
        let point = skill["point"].as_str().ok_or("Missing primary point")?;
        let secondary = skill["secondary_point"]
            .as_str()
            .ok_or("Missing secondary point")?;
        let strings = |field: &str| -> Result<Vec<&str>, String> {
            skill[field]
                .as_array()
                .filter(|a| a.len() <= 16)
                .ok_or("Invalid flag list")?
                .iter()
                .map(|v| {
                    v.as_str()
                        .filter(|s| s.len() <= 64)
                        .ok_or("Invalid skill flag".into())
                })
                .collect()
        };
        let flags = strings("flags")?;
        let weapons = strings("weapon_limits")?;
        let radius = integer(&skill["splash_radius_cm"], 0, 10000)? as f32 / 100.0;
        let range = integer(&skill["target_range_cm"], 0, 10000)? as f32 / 100.0;
        let max_targets = integer(&skill["max_targets"], 0, 32)?;
        let fields = [
            ("amount", "formula"),
            ("secondary", "secondary_formula"),
            ("duration", "duration"),
            ("secondary_duration", "secondary_duration"),
            ("upkeep", "sp_upkeep"),
            ("splash_scale", "splash_scale"),
        ]
        .into_iter()
        .map(|(name, source)| program(&skill["programs"][source]).map(|p| format!("{name}:{p}")))
        .collect::<Result<Vec<_>, _>>()?
        .join(",");
        definitions.push(format!("ClassSkillDefinition{{vnum:{id},class_id:{class},group:{group},minimum_level:{minimum_level},maximum_rank:{maximum_rank},handler:SkillHandler::{handler},target:SkillTarget::{target},attribute:SkillAttribute::{attribute},affect:{primary_affect:?},secondary_affect:{secondary_affect:?},point:{point:?},secondary_point:{secondary:?},flags:&{flags:?},weapon_limits:&{weapons:?},rank_costs:{costs:?},rank_cooldowns_us:{cooldowns:?},programs:SkillPrograms{{{fields}}},radius_m:{radius:?},range_m:{range:?},max_targets:{max_targets}}}"));
        for variant in skill["variants"].as_array().unwrap() {
            let actor = variant["actor_id"].as_str().unwrap();
            let action = variant["action_id"].as_str().unwrap();
            let duration = variant["duration_us"].as_u64().unwrap();
            let root = variant["root_m"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap() as f32)
                .collect::<Vec<_>>();
            let activations = variant["activation_us"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_u64().unwrap())
                .collect::<Vec<_>>();
            let windows = hit_windows(variant, duration)?;
            motions.push(format!("ClassSkillMotion{{skill_vnum:{id},actor_id:{actor:?},action_id:{action:?},duration_us:{duration},root_m:{root:?},activation_us:&{activations:?},hit_windows_us:&{windows:?}}}"));
        }
    }
    writeln!(
        out,
        "pub const CLASS_SKILLS:&[ClassSkillDefinition]=&[{}];",
        definitions.join(",")
    )
    .unwrap();
    writeln!(
        out,
        "pub const CLASS_SKILL_MOTIONS:&[ClassSkillMotion]=&[{}];",
        motions.join(",")
    )
    .unwrap();
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn catalog() -> Value {
        let mut skills = Vec::new();
        for (class, name) in ["warrior", "ninja", "sura", "shaman"].iter().enumerate() {
            for group in 1..=2 {
                for slot in 1..=if class < 2 { 5 } else { 6 } {
                    let id = class * 30 + (group - 1) * 15 + slot;
                    let variants = ["male", "female"].map(|sex| {
                        let actor = format!("actor.player.{name}-{sex}");
                        json!({"actor_id":actor,"action_id":format!("{actor}.general.skill_{id}"),
                            "duration_us":1_000_000,"root_m":[0,0,0],"activation_us":[0],
                            "hits":[{"kind":"attack_area","start_us":0,"end_us":200_000}]})
                    });
                    let programs = [
                        "formula",
                        "sp_cost",
                        "duration",
                        "sp_upkeep",
                        "cooldown",
                        "secondary_formula",
                        "secondary_duration",
                        "splash_scale",
                    ]
                    .map(|field| (field.to_string(), json!([{"op":"constant","value":1}])));
                    skills.push(json!({
                        "vnum":id,"class_id":class,"group":group,"minimum_level":5,
                        "maximum_rank":20,"handler":"damage","target":"monster",
                        "attribute":"MAGIC","affect":"14","secondary_affect":"",
                        "rank_costs":vec![1;21],"rank_cooldowns_us":vec![1_000_000;21],
                        "programs":programs.into_iter().collect::<serde_json::Map<_,_>>(),
                        "variants":variants,"point":"HP","secondary_point":"NONE",
                        "flags":["ATTACK"],"weapon_limits":[],"splash_radius_cm":200,
                        "target_range_cm":300,"max_targets":12
                    }));
                }
            }
        }
        json!({"schema":"mt2spacetime.skills","version":2,
            "rank_power_percent":(0..=20).collect::<Vec<_>>(),"skills":skills})
    }

    #[test]
    fn hit_windows_preserve_separate_intervals_and_reject_invalid_timing() {
        let mut v = json!({"activation_us":[10,40],"hits":[
            {"kind":"attack_area","start_us":10,"end_us":30},
            {"kind":"attack_window","start_us":40,"end_us":150}
        ]});
        assert_eq!(hit_windows(&v, 100).unwrap(), vec![[10, 30], [40, 150]]);
        for value in [json!(9), json!(10_000_101), json!(-1), json!(true)] {
            v["hits"][0]["end_us"] = value;
            assert!(hit_windows(&v, 100).is_err());
        }
        v["hits"][0]["end_us"] = json!(30);
        v["hits"][0]["start_us"] = json!(11);
        assert!(hit_windows(&v, 100).is_err());
        v["hits"][0]["start_us"] = json!(10);
        v["hits"][0]["kind"] = json!("custom");
        assert!(hit_windows(&v, 100).is_err());
        v["hits"] = Value::Null;
        assert!(hit_windows(&v, 100).is_err());
    }

    #[test]
    fn complete_catalog_compiles_with_primary_and_secondary_effects() {
        let mut root = catalog();
        for attribute in ["NORMAL", "MELEE", "RANGE", "MAGIC"] {
            root["skills"][0]["attribute"] = json!(attribute);
            root["skills"][0]["secondary_affect"] = json!("30");
            assert!(generate(&root).is_ok());
        }
    }

    #[test]
    fn invalid_mechanic_metadata_and_learning_limits_reject() {
        for (field, values) in [
            ("attribute", vec![json!("SCRIPT"), Value::Null]),
            ("minimum_level", vec![json!(0), json!(100), json!(true)]),
            ("maximum_rank", vec![json!(0), json!(21)]),
            (
                "affect",
                vec![
                    json!(14),
                    json!("0"),
                    json!("014"),
                    json!("-1"),
                    json!("65536"),
                ],
            ),
            ("secondary_affect", vec![json!("custom()"), Value::Null]),
        ] {
            for value in values {
                let mut root = catalog();
                root["skills"][0][field] = value;
                assert!(generate(&root).is_err(), "accepted invalid {field}");
            }
        }
    }

    #[test]
    fn rank_power_table_requires_zero_unlearned_and_bounded_progression() {
        for (rank, value) in [(0, 1), (1, 0), (20, 101), (10, 9)] {
            let mut root = catalog();
            root["rank_power_percent"][rank] = json!(value);
            assert!(generate(&root).is_err());
        }
        let mut root = catalog();
        root["rank_power_percent"].as_array_mut().unwrap().pop();
        assert!(generate(&root).is_err());
    }
}
