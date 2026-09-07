//! Shared population authoring validation for the build and offline developer tool.
use serde_json::{Map, Value};
use std::collections::BTreeSet;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MonsterSpawn {
    pub id: u32,
    pub home_x: f32,
    pub home_z: f32,
}

fn fields<'a>(value: &'a Value, expected: &[&str]) -> Result<&'a Map<String, Value>, String> {
    let row = value.as_object().ok_or("Expected an object")?;
    if row.len() != expected.len() || expected.iter().any(|key| !row.contains_key(*key)) {
        return Err(format!(
            "Expected exactly these fields: {}",
            expected.join(", ")
        ));
    }
    Ok(row)
}

fn positive_u32(value: &Value) -> Result<u32, String> {
    value
        .as_u64()
        .and_then(|number| u32::try_from(number).ok())
        .filter(|number| *number > 0)
        .ok_or("Expected a positive u32 integer".into())
}

fn coordinate(value: &Value) -> Result<f32, String> {
    let number = value.as_f64().ok_or("Expected a numeric coordinate")?;
    if !number.is_finite() || number.abs() > 1_000_000.0 {
        return Err("Coordinate exceeds the finite supported range".into());
    }
    Ok(number as f32)
}

pub fn parse(value: &Value, map_id: &str, mob_vnum: u32) -> Result<Vec<MonsterSpawn>, String> {
    let root = fields(
        value,
        &[
            "schema_version",
            "profile_id",
            "revision",
            "map_id",
            "basis",
            "placements",
        ],
    )?;
    if root["schema_version"].as_u64() != Some(1) || root["map_id"].as_str() != Some(map_id) {
        return Err("Population schema or map identity does not match the selected map".into());
    }
    positive_u32(&root["revision"])?;
    let profile = root["profile_id"]
        .as_str()
        .ok_or("Missing profile identity")?;
    if profile.is_empty()
        || profile.len() > 80
        || !profile
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
    {
        return Err("Invalid population profile identity".into());
    }
    if root["basis"].as_str() != Some("authored-development-layout") {
        return Err("This schema accepts authored development layouts".into());
    }
    let rows = root["placements"]
        .as_array()
        .ok_or("Placements must be an array")?;
    if rows.is_empty() || rows.len() > 128 {
        return Err("Population must contain 1..=128 monster placements".into());
    }
    let mut ids = BTreeSet::new();
    let mut spawns: Vec<MonsterSpawn> = Vec::with_capacity(rows.len());
    for value in rows {
        let row = fields(value, &["id", "definition_vnum", "home_x", "home_z"])?;
        let id = positive_u32(&row["id"])?;
        if !ids.insert(id) {
            return Err(format!("Duplicate spawn ID {id}"));
        }
        if positive_u32(&row["definition_vnum"])? != mob_vnum {
            return Err(format!(
                "Spawn {id} refers to an unavailable monster definition"
            ));
        }
        let home_x = coordinate(&row["home_x"])?;
        let home_z = coordinate(&row["home_z"])?;
        if spawns
            .iter()
            .any(|other| (other.home_x - home_x).hypot(other.home_z - home_z) < 1.0)
        {
            return Err(format!("Spawn {id} overlaps another authored home"));
        }
        spawns.push(MonsterSpawn { id, home_x, home_z });
    }
    spawns.sort_by_key(|spawn| spawn.id);
    Ok(spawns)
}
