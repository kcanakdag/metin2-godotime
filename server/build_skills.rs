//! Compile bounded skill definitions shared with the exported client.
#[path = "build_skill_geometry.rs"]
mod geometry;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fmt::Write, fs};

fn n(row: &Value, key: &str, lo: u64, hi: u64) -> Result<u64, String> {
    row[key]
        .as_u64()
        .filter(|v| (lo..=hi).contains(v))
        .ok_or_else(|| format!("Invalid skill {key}"))
}
fn f(row: &Value, key: &str, max: f64) -> Result<f64, String> {
    row[key]
        .as_f64()
        .filter(|v| v.is_finite() && v.abs() <= max)
        .ok_or_else(|| format!("Invalid skill {key}"))
}
fn windows(variant: &Value, duration: u64, start: u64, end: u64) -> Result<Vec<[u64; 2]>, String> {
    let Some(value) = variant.get("hit_windows_us") else {
        return Ok(vec![[start, end]]);
    };
    let rows = value
        .as_array()
        .filter(|r| !r.is_empty() && r.len() <= 32)
        .ok_or("Invalid live skill event list")?;
    let mut result = Vec::new();
    for row in rows {
        let pair = row
            .as_array()
            .filter(|r| r.len() == 2)
            .ok_or("Invalid live skill event pair")?;
        let a = pair[0]
            .as_u64()
            .filter(|v| *v <= duration)
            .ok_or("Invalid live skill event start")?;
        let b = pair[1]
            .as_u64()
            .filter(|v| *v >= a && *v <= duration + 10_000_000)
            .ok_or("Invalid live skill event end")?;
        result.push([a, b]);
    }
    if result.windows(2).any(|w| w[0][0] >= w[1][0])
        || result.iter().map(|w| w[0]).min() != Some(start)
        || result.iter().map(|w| w[1]).max() != Some(end)
    {
        return Err("Live skill events differ from their ordered action envelope".into());
    }
    Ok(result)
}

pub fn generate(bytes: &[u8]) -> Result<String, String> {
    let root: Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
    if root["schema"] != "mt2spacetime.skills" || root["version"] != 1 {
        return Err("Unsupported skill catalog".into());
    }
    let powers = root["rank_power_percent"]
        .as_array()
        .ok_or("Missing skill powers")?;
    if powers.len() != 21 || powers[0] != 0 {
        return Err("Invalid skill powers".into());
    }
    let mut values = Vec::new();
    for p in powers {
        values.push(
            p.as_u64()
                .filter(|v| *v <= 100)
                .ok_or("Invalid rank power")?,
        );
    }
    if values.windows(2).any(|w| w[0] >= w[1]) {
        return Err("Rank powers must increase".into());
    }
    let rows = root["skills"]
        .as_array()
        .filter(|r| !r.is_empty() && r.len() <= 64)
        .ok_or("Invalid skills")?;
    let mut out = String::from(
        "#[derive(Clone,Copy,Debug)]\npub struct SkillDefinition {pub vnum:u16,pub class_id:u8,pub minimum_level:u8,pub maximum_rank:u8,pub cooldown_us:i64,pub radius_m:f32,pub max_targets:u8,pub hits_per_life:u8,pub sp_base:u16,pub sp_per_power:u16,pub damage_milli:[i64;6]}\n",
    );
    writeln!(
        out,
        "pub const SKILL_CATALOG_HASH:&str={:?};",
        format!("{:x}", Sha256::digest(bytes))
    )
    .unwrap();
    writeln!(out, "pub const SKILL_POWERS:[u16;21]={values:?};").unwrap();
    // Selected catalogs may omit either geometry kind while sharing the strict resolver.
    out.push_str(&geometry::TYPES.replace(
        "pub enum SkillHitGeometry",
        "#[allow(dead_code)] pub enum SkillHitGeometry",
    ));
    out.push_str(geometry::RESOLVER);
    out.push_str("#[derive(Clone,Copy,Debug)] pub struct SkillHitReaction {pub hit_type:u8,pub invulnerability_us:i64,pub external_force:f64}\n");
    let mut reactions = Vec::new();
    let mut geometries = Vec::new();
    let mut definitions = Vec::new();
    let mut actions = Vec::new();
    let mut event_lists = Vec::new();
    let mut ids = BTreeSet::new();
    for row in rows {
        if !matches!(
            row["handler"].as_str(),
            Some("physical_splash_v1" | "physical_area_v1")
        ) || row["weapon_class"] != "sword"
        {
            return Err("Unsupported skill handler".into());
        }
        let id = n(row, "vnum", 1, 255)?;
        if !ids.insert(id) {
            return Err("Duplicate skill ID".into());
        }
        let class = n(row, "class_id", 0, 3)?;
        let level = n(row, "minimum_level", 5, 99)?;
        let rank = n(row, "maximum_rank", 1, 20)?;
        let cooldown = n(row, "cooldown_us", 1_000_000, 300_000_000)?;
        let radius = f(row, "radius_m", 10.0)?;
        if radius <= 0.0 {
            return Err("Invalid skill radius".into());
        }
        let targets = n(row, "max_targets", 1, 32)?;
        let hits_per_life = if row.get("hits_per_life").is_some() {
            n(row, "hits_per_life", 1, 32)?
        } else {
            1
        };
        let sp = n(row, "sp_base", 0, 1000)?;
        let per = n(row, "sp_per_power", 0, 1000)?;
        let coefficients = row["damage_milli"]
            .as_array()
            .filter(|r| r.len() == 6)
            .ok_or("Invalid skill coefficients")?
            .iter()
            .map(|v| {
                v.as_u64()
                    .filter(|n| *n <= 1_000_000)
                    .ok_or("Invalid skill coefficient")
            })
            .collect::<Result<Vec<_>, _>>()?;
        definitions.push(format!("SkillDefinition{{vnum:{id},class_id:{class},minimum_level:{level},maximum_rank:{rank},cooldown_us:{cooldown},radius_m:{radius:?},max_targets:{targets},hits_per_life:{hits_per_life},sp_base:{sp},sp_per_power:{per},damage_milli:{coefficients:?}}}"));
        let variants = row["variants"]
            .as_array()
            .filter(|r| r.len() == 2)
            .ok_or("Skill needs both appearances")?;
        let mut actor_ids = BTreeSet::new();
        for v in variants {
            let actor = v["actor_id"]
                .as_str()
                .filter(|s| s.starts_with("actor.player."))
                .ok_or("Invalid skill actor")?;
            let action = v["action_id"]
                .as_str()
                .filter(|s| s.starts_with(&format!("{actor}.general.skill_")))
                .ok_or("Invalid skill action")?;
            if !actor_ids.insert(actor) {
                return Err("Duplicate skill appearance".into());
            }
            let duration = n(v, "duration_us", 1, 3_200_000)?;
            let start = n(v, "hit_start_us", 1, duration)?;
            let end = n(v, "hit_end_us", start + 1, duration)?;
            let events = windows(v, duration, start, end)?;
            event_lists.push(format!("({id},{actor:?},&{events:?})"));
            if row["handler"] == "physical_area_v1" {
                let hits = v["hit_geometry"]
                    .as_array()
                    .filter(|hits| hits.len() == events.len())
                    .ok_or("Skill areas must match their event list")?;
                let mut shapes = Vec::new();
                let mut responses = Vec::new();
                for hit in hits {
                    if hit["kind"] != "attack_area" {
                        return Err("Fixed-area handler requires attack-area geometry".into());
                    }
                    shapes.push(geometry::generate(hit)?);
                    let hit_type = n(hit, "hitting_type", 1, 2)?;
                    let invisible = n(hit, "invisible_us", 0, 10_000_000)?;
                    n(hit, "stiffen_us", 0, 0)?;
                    let force = f(hit, "external_force", 20.0)?;
                    if force < 0.0
                        || (hit_type == 2 && force != 0.0)
                        || hit["attack_type"] != 0
                        || hit["collision_type"] != 4
                    {
                        return Err("Unsupported fixed-area reaction or attack policy".into());
                    }
                    responses.push(format!("SkillHitReaction{{hit_type:{hit_type},invulnerability_us:{invisible},external_force:{force:?}}}"));
                }
                reactions.push(format!("({id},{actor:?},&[{}])", responses.join(",")));
                geometries.push(format!("({id},{actor:?},&[{}])", shapes.join(",")));
            } else if v.get("hit_geometry").is_some() {
                return Err("Radial handler cannot silently ignore authored geometry".into());
            }
            let x = f(v, "root_x_m", 4.0)?;
            let z = f(v, "root_z_m", 4.0)?;
            actions.push(format!("({id},{actor:?},AttackDefinition{{id:{action:?},duration_us:{duration},cooldown_us:{duration},ordinary_hit_invulnerability_us:200000,hit_start_us:{start},hit_end_us:{end},range_m:{radius:?},combo_input:None,root_motion:Some(RootMotionDefinition{{endpoint_x_m:{x:?},endpoint_z_m:{z:?},duration_us:{duration}}}),special_area:None,screen_wave:None,ordinary_knockback:None}})"));
        }
    }
    writeln!(
        out,
        "pub const SKILL_DEFINITIONS:&[SkillDefinition]=&[{}];",
        definitions.join(",")
    )
    .unwrap();
    writeln!(
        out,
        "pub const SKILL_ACTIONS:&[(u16,&str,AttackDefinition)]=&[{}];",
        actions.join(",")
    )
    .unwrap();
    writeln!(
        out,
        "pub const SKILL_EVENT_WINDOWS:&[(u16,&str,&[[i64;2]])]=&[{}];",
        event_lists.join(",")
    )
    .unwrap();
    writeln!(
        out,
        "pub const SKILL_EVENT_GEOMETRY:&[(u16,&str,&[SkillHitGeometry])]=&[{}];",
        geometries.join(",")
    )
    .unwrap();
    writeln!(
        out,
        "pub const SKILL_EVENT_REACTIONS:&[(u16,&str,&[SkillHitReaction])]=&[{}];",
        reactions.join(",")
    )
    .unwrap();
    Ok(out)
}
pub fn build() -> String {
    let path = "../client/assets/imported/skills/catalog.v1.json";
    println!("cargo:rerun-if-changed={path}");
    generate(&fs::read(path).expect("Run tools/build_skill_catalog.py before building skills"))
        .expect("Invalid skill catalog")
}

#[cfg(test)]
mod event_tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn legacy_and_multiple_windows_preserve_envelopes() {
        assert_eq!(windows(&json!({}), 100, 10, 90).unwrap(), vec![[10, 90]]);
        assert_eq!(
            windows(
                &json!({"hit_windows_us":[[10,20],[30,40],[50,90]]}),
                100,
                10,
                90
            )
            .unwrap(),
            vec![[10, 20], [30, 40], [50, 90]]
        );
    }
    #[test]
    fn malformed_or_mismatched_windows_reject() {
        for value in [
            json!([]),
            json!([[10, 9]]),
            json!([[11, 90]]),
            json!([[10, 89]]),
            json!([[30, 40], [10, 90]]),
            json!([[10, 90], [10, 90]]),
            json!([[true, 90]]),
            json!([[10, 90, 100]]),
        ] {
            assert!(windows(&json!({"hit_windows_us":value}), 100, 10, 90).is_err());
        }
    }
}
