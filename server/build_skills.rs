//! Compile bounded skill definitions shared with the exported client.
#[path = "build_buff_skills.rs"]
mod buffs;
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

fn area_dispatch(windows: &[[u64; 2]]) -> Result<Vec<[u64; 2]>, String> {
    windows
        .iter()
        .map(|&[start, end]| {
            // Same source 60-Hz event bucket policy used by original combo areas.
            let frame = start.checked_mul(60).ok_or("Skill dispatch overflow")? / 1_000_000;
            let activation = (frame + 1)
                .checked_mul(1_000_000)
                .ok_or("Skill dispatch overflow")?
                .div_ceil(60);
            let expiry = activation
                .checked_add(end.checked_sub(start).ok_or("Reversed skill area")?)
                .ok_or("Skill expiry overflow")?;
            if activation > 3_200_000 || expiry > 13_200_000 {
                return Err("Skill area dispatch exceeds runtime bounds".into());
            }
            Ok([activation, expiry])
        })
        .collect()
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
        "#[derive(Clone,Copy,Debug)]\npub struct SkillDefinition {pub vnum:u16,pub class_id:u8,pub minimum_level:u8,pub maximum_rank:u8,pub cooldown_us:i64,pub radius_m:f32,pub max_targets:u8,pub hits_per_life:u8,pub requires_target:bool,pub target_range_m:f32,pub sp_base:u16,pub sp_per_power:u16,pub damage_milli:[i64;6],pub charge:Option<crate::charge_lifecycle::Definition>}\n",
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
    let mut buff_definitions = Vec::new();
    let mut ids = BTreeSet::new();
    for row in rows {
        if !matches!(
            row["handler"].as_str(),
            Some("physical_splash_v1" | "physical_area_v1" | "physical_charge_v1" | "self_buff_v1")
        ) || row["weapon_class"]
            != if row["handler"] == "physical_charge_v1" {
                "sword_or_two_handed"
            } else if row["handler"] == "self_buff_v1" {
                "any"
            } else {
                "sword"
            }
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
        let is_buff = row["handler"] == "self_buff_v1";
        if (is_buff && radius != 0.0) || (!is_buff && radius <= 0.0) {
            return Err("Invalid skill radius".into());
        }
        let targets = n(row, "max_targets", 1, 32)?;
        let hits_per_life = if row.get("hits_per_life").is_some() {
            n(row, "hits_per_life", 1, 32)?
        } else {
            1
        };
        let requires_target = match row.get("requires_target") {
            None => false,
            Some(value) => value.as_bool().ok_or("Invalid skill target requirement")?,
        };
        let target_range = if row.get("target_range_m").is_some() {
            f(row, "target_range_m", 100.0)?
        } else {
            0.0
        };
        if target_range < 0.0 || (!requires_target && target_range != 0.0) {
            return Err("Invalid skill target range policy".into());
        }
        if is_buff {
            if requires_target || targets != 1 || hits_per_life != 1 {
                return Err("Self buff cannot target damage victims".into());
            }
            buff_definitions.push(buffs::generate(id, &row["buff"])?);
        } else if row.get("buff").is_some() {
            return Err("Buff programs require self-buff dispatch".into());
        }
        let charge = if row["handler"] == "physical_charge_v1" {
            if !requires_target || target_range <= 0.0 || hits_per_life != 1 {
                return Err("Charge requires a bounded target and one hit per life".into());
            }
            let value = &row["charge"];
            if value.as_object().is_none_or(|v| v.len() != 4) {
                return Err("Invalid charge definition fields".into());
            }
            let duration = n(value, "duration_us", 1, 600_000_000)?;
            let speed = n(value, "speed_bonus", 0, 1000)?;
            let push = f(value, "push_distance_m", 20.0)?;
            let stun = n(value, "main_target_stun_us", 0, 600_000_000)?;
            if push < 0.0 {
                return Err("Invalid charge push distance".into());
            }
            format!(
                "Some(crate::charge_lifecycle::Definition{{duration_us:{duration},speed_bonus:{speed},push_distance_m:{push:?},main_target_stun_us:{stun}}})"
            )
        } else {
            if row.get("charge").is_some() {
                return Err("Charge metadata requires charge dispatch".into());
            }
            "None".to_owned()
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
        if is_buff && coefficients.iter().any(|coefficient| *coefficient != 0) {
            return Err("Self buff cannot carry physical damage coefficients".into());
        }
        definitions.push(format!("SkillDefinition{{vnum:{id},class_id:{class},minimum_level:{level},maximum_rank:{rank},cooldown_us:{cooldown},radius_m:{radius:?},max_targets:{targets},hits_per_life:{hits_per_life},requires_target:{requires_target},target_range_m:{target_range:?},sp_base:{sp},sp_per_power:{per},damage_milli:{coefficients:?},charge:{charge}}}"));
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
            let (start, end, events) = if is_buff {
                if [
                    "hit_start_us",
                    "hit_end_us",
                    "hit_windows_us",
                    "hit_geometry",
                    "source_hit_events",
                ]
                .iter()
                .any(|field| v.get(field).is_some())
                {
                    return Err("Self buff cannot schedule motion damage".into());
                }
                (0, 0, Vec::new())
            } else if row["handler"] == "physical_charge_v1" {
                for field in [
                    "hit_start_us",
                    "hit_end_us",
                    "hit_windows_us",
                    "hit_geometry",
                ] {
                    if v.get(field).is_some() {
                        return Err("Charge cannot schedule animation-window damage".into());
                    }
                }
                let source = v["source_hit_events"]
                    .as_array()
                    .filter(|v| v.len() <= 32)
                    .ok_or("Missing charge source event metadata")?;
                for hit in source {
                    let start = n(hit, "start_us", 0, duration)?;
                    n(hit, "end_us", start, duration + 10_000_000)?;
                    geometry::generate(hit)?;
                }
                (0, 0, Vec::new())
            } else {
                if v.get("source_hit_events").is_some() {
                    return Err("Unconsumed charge source events on ordinary skill".into());
                }
                let start = n(v, "hit_start_us", 1, duration)?;
                let end = n(v, "hit_end_us", start + 1, duration)?;
                (start, end, windows(v, duration, start, end)?)
            };
            let dispatch = if row["handler"] == "physical_area_v1" {
                area_dispatch(&events)?
            } else {
                events.clone()
            };
            event_lists.push(format!("({id},{actor:?},&{dispatch:?})"));
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
        "pub const SELF_BUFFS:&[crate::buff_capture::Definition<'static>]=&[{}];",
        buff_definitions.join(",")
    )
    .unwrap();
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
    println!("cargo:rerun-if-env-changed=MT2_SKILL_CATALOG");
    let path = std::env::var("MT2_SKILL_CATALOG")
        .unwrap_or_else(|_| "../client/assets/imported/skills/catalog.v1.json".into());
    println!("cargo:rerun-if-changed={path}");
    generate(&fs::read(path).expect("Run tools/build_skill_catalog.py before building skills"))
        .expect("Invalid skill catalog")
}

#[cfg(test)]
mod event_tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn original_area_frames_preserve_duration_and_exact_boundary_policy() {
        assert_eq!(
            area_dispatch(&[[162206, 362206], [434712, 634712], [849959, 1049959]]).unwrap(),
            vec![[166667, 366667], [450000, 650000], [850000, 1050000]]
        );
        assert_eq!(
            area_dispatch(&[[100000, 300000]]).unwrap(),
            vec![[116667, 316667]]
        );
        assert!(area_dispatch(&[[20, 10]]).is_err());
        assert!(area_dispatch(&[[u64::MAX, u64::MAX]]).is_err());
    }

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
