//! Validated authored practice targets; never grant combat rewards.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fmt::Write;

fn number(root: &Value, key: &str, low: u64, high: u64) -> Result<u64, String> {
    root[key]
        .as_u64()
        .filter(|n| (low..=high).contains(n))
        .ok_or_else(|| format!("Invalid training target {key}"))
}

pub fn generate(root: &Value, map: &str) -> Result<String, String> {
    let expected = [
        "schema_version",
        "id",
        "vnum",
        "name",
        "health",
        "level",
        "vitality",
        "dexterity",
        "defense",
        "sword_resistance_percent",
        "fan_resistance_percent",
        "respawn_ms",
        "hit_radius_m",
        "hit_center_y_m",
        "height_m",
        "body_radius_m",
        "colors",
        "placements",
    ];
    if !root.as_object().is_some_and(|fields| {
        fields.len() == expected.len() && expected.iter().all(|key| fields.contains_key(*key))
    }) {
        return Err("Invalid training target profile fields".into());
    }
    if root["schema_version"] != 1 {
        return Err("Unsupported training target schema".into());
    }
    let actor = root["id"]
        .as_str()
        .filter(|s| {
            s.starts_with("actor.training.")
                && s.len() > "actor.training.".len()
                && s.len() <= 100
                && s.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'-')
        })
        .ok_or("Invalid training actor ID")?;
    let name = root["name"]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= 64 && !s.chars().any(char::is_control))
        .ok_or("Invalid training target name")?;
    let vnum = number(root, "vnum", 900_000, 999_999)?;
    let health = number(root, "health", 1, 65_535)?;
    let level = number(root, "level", 1, 99)?;
    let vitality = number(root, "vitality", 0, 90)?;
    let dexterity = number(root, "dexterity", 0, 90)?;
    let defense = number(root, "defense", 0, 10_000)?;
    let sword = number(root, "sword_resistance_percent", 0, 100)?;
    let fan = number(root, "fan_resistance_percent", 0, 100)?;
    let respawn = number(root, "respawn_ms", 100, 60_000)? * 1000;
    let finite = |key: &str| {
        root[key]
            .as_f64()
            .filter(|v| v.is_finite() && (0.01..=4.0).contains(v))
            .ok_or("Invalid training target hit sphere")
    };
    let hit_radius = finite("hit_radius_m")?;
    let hit_y = finite("hit_center_y_m")?;
    for (key, low, high) in [("height_m", 0.5, 3.5), ("body_radius_m", 0.1, 0.8)] {
        if !root[key]
            .as_f64()
            .is_some_and(|v| v.is_finite() && (low..=high).contains(&v))
        {
            return Err(format!("Invalid training target {key}"));
        }
    }
    let colors = root["colors"]
        .as_object()
        .ok_or("Invalid training target colors")?;
    if colors.len() != 4
        || !["wood", "straw", "rope", "target"].iter().all(|key| {
            colors
                .get(*key)
                .and_then(Value::as_array)
                .is_some_and(|channels| {
                    channels.len() == 4
                        && channels.iter().all(|channel| {
                            channel
                                .as_f64()
                                .is_some_and(|v| v.is_finite() && (0.0..=1.0).contains(&v))
                        })
                })
        })
    {
        return Err("Invalid training target RGBA colors".into());
    }
    let rows = root["placements"]
        .as_array()
        .filter(|v| !v.is_empty() && v.len() <= 32)
        .ok_or("Invalid training target placements")?;
    let mut ids = std::collections::BTreeSet::new();
    let mut spawns = String::new();
    for row in rows {
        if !row.as_object().is_some_and(|fields| {
            fields.len() == 4
                && ["map_id", "id", "home_x", "home_z"]
                    .iter()
                    .all(|key| fields.contains_key(*key))
        }) {
            return Err("Invalid training target placement fields".into());
        }
        let world = row["map_id"]
            .as_str()
            .filter(|s| matches!(*s, "training" | "metin2_map_a1"))
            .ok_or("Unsupported training target map")?;
        let id = number(row, "id", 900_000, 999_999)?;
        if !ids.insert((world, id)) {
            return Err("Duplicate training target placement".into());
        }
        let coordinate = |key: &str| {
            row[key]
                .as_f64()
                .filter(|v| v.is_finite() && v.abs() <= 1024.0)
                .map(|v| v as f32)
                .ok_or("Invalid training target position")
        };
        let (x, z) = (coordinate("home_x")?, coordinate("home_z")?);
        if world == map {
            writeln!(
                spawns,
                "MonsterSpawnDefinition {{ id: {id}, home_x: {x:?}, home_z: {z:?} }},"
            )
            .unwrap();
        }
    }
    let hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(root).map_err(|e| e.to_string())?)
    );
    Ok(format!("#[derive(Clone, Copy, Debug)]
pub struct TrainingTargetDefinition {{ pub vnum: u32, pub actor_id: &'static str, pub name: &'static str, pub health: u16, pub level: u8, pub vitality: u8, pub dexterity: u8, pub defense: u16, pub sword_resistance: u8, pub fan_resistance: u8, pub respawn_us: i64, pub hit_radius_m: f64, pub hit_center_y_m: f64 }}
pub const TRAINING_TARGET_HASH: &str = {hash:?};
pub const TRAINING_TARGET: TrainingTargetDefinition = TrainingTargetDefinition {{ vnum: {vnum}, actor_id: {actor:?}, name: {name:?}, health: {health}, level: {level}, vitality: {vitality}, dexterity: {dexterity}, defense: {defense}, sword_resistance: {sword}, fan_resistance: {fan}, respawn_us: {respawn}, hit_radius_m: {hit_radius:?}, hit_center_y_m: {hit_y:?} }};
pub const TRAINING_TARGET_SPAWNS: &[MonsterSpawnDefinition] = &[{spawns}];\n"))
}

pub fn build() -> String {
    println!("cargo:rerun-if-env-changed=MT2_TRAINING_TARGET_PROFILE");
    let path = std::env::var("MT2_TRAINING_TARGET_PROFILE")
        .unwrap_or_else(|_| "../content/profiles/training-dummy.json".into());
    println!("cargo:rerun-if-changed={path}");
    println!("cargo:rerun-if-changed=build_training.rs");
    let root =
        serde_json::from_slice(&std::fs::read(&path).expect("Training target profile is required"))
            .expect("Training target profile must be JSON");
    generate(
        &root,
        if std::env::var_os("CARGO_FEATURE_YONGAN").is_some() {
            "metin2_map_a1"
        } else {
            "training"
        },
    )
    .expect("Training target profile must satisfy the server contract")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn profile_bounds_and_unique_placements() {
        let profile: Value =
            serde_json::from_str(include_str!("../content/profiles/training-dummy.json")).unwrap();
        assert!(generate(&profile, "training").is_ok());
        for (key, value) in [
            ("health", 0),
            ("health", 65536),
            ("level", 100),
            ("defense", 10001),
            ("sword_resistance_percent", 101),
            ("respawn_ms", 0),
        ] {
            let mut bad = profile.clone();
            bad[key] = value.into();
            assert!(generate(&bad, "training").is_err(), "{key}");
        }
        let mut duplicate = profile.clone();
        let row = duplicate["placements"][0].clone();
        duplicate["placements"].as_array_mut().unwrap().push(row);
        assert!(generate(&duplicate, "training").is_err());
    }
}
