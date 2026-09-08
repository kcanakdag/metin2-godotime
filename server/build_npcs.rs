//! Join authored interactions to the same offline catalog used by presentation.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fmt::Write as _};
const TYPE: &str = "pub struct NpcDefinition { pub id: &'static str, pub name: &'static str, pub body: &'static str, pub x: f32, pub y: f32, pub z: f32 }\n pub struct NpcAreaDefinition { pub id: &'static str, pub actor_id: &'static str, pub bounds_cm: [i32;4], pub respawn_interval_us: i64 }\n";

fn exact(value: &Value, keys: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("Expected an NPC object")?;
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err("Unexpected NPC interaction fields".into());
    }
    Ok(())
}

pub fn generate(catalog: &[u8], actions: &Value, map_hash: &str) -> Result<String, String> {
    let doc: Value = serde_json::from_slice(catalog).map_err(|e| e.to_string())?;
    if doc["schema"] != "mt2spacetime.static-npcs"
        || !matches!(doc["version"].as_u64(), Some(1..=3))
    {
        return Err("Unsupported static NPC catalog".into());
    }
    exact(actions, &["schema_version", "map_id", "interactions"])?;
    if actions["schema_version"] != 1 || actions["map_id"] != "metin2_map_a1" {
        return Err("Unsupported NPC interaction profile".into());
    }
    let maps = doc["maps"].as_array().ok_or("Missing NPC maps")?;
    let worlds: Vec<_> = maps
        .iter()
        .filter(|m| m["id"] == actions["map_id"])
        .collect();
    if worlds.len() != 1 || worlds[0]["content_hash"] != map_hash {
        return Err("NPC catalog differs from the compiled map".into());
    }
    let placements = worlds[0]["placements"]
        .as_array()
        .ok_or("Missing NPC placements")?;
    let actors = doc["actors"].as_array().ok_or("Missing NPC actors")?;
    let rows = actions["interactions"]
        .as_array()
        .ok_or("Missing interactions")?;
    if rows.is_empty() || rows.len() > 4096 {
        return Err("Expected 1..4096 NPC interactions".into());
    }
    let mut output = TYPE.to_owned();
    output.push_str(&format!(
        "pub const NPC_CATALOG_HASH: &str = {:?};\n",
        format!("{:x}", Sha256::digest(catalog))
    ));
    output.push_str("pub const NPCS: &[NpcDefinition] = &[\n");
    let mut ids = BTreeSet::new();
    for row in rows {
        exact(row, &["spawn_id", "kind", "body"])?;
        let id = row["spawn_id"].as_str().ok_or("Missing NPC spawn id")?;
        let body = row["body"].as_str().ok_or("Missing dialogue text")?;
        if !id.starts_with("spawn.")
            || id.len() > 128
            || !ids.insert(id)
            || row["kind"] != "dialogue"
            || body.is_empty()
            || body.len() > 1024
            || body.chars().any(|c| c.is_control() && c != '\n')
        {
            return Err("Invalid or duplicate NPC interaction".into());
        }
        let matches: Vec<_> = placements.iter().filter(|p| p["id"] == id).collect();
        if matches.len() != 1 {
            return Err("Interaction must resolve exactly one NPC placement".into());
        }
        let spawn = matches[0];
        let models: Vec<_> = actors
            .iter()
            .filter(|a| a["id"] == spawn["actor_id"])
            .collect();
        if models.len() != 1 {
            return Err("Interaction must resolve exactly one NPC actor".into());
        }
        let name = models[0]["name"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 160)
            .ok_or("Invalid NPC name")?;
        let position = spawn["position"]
            .as_array()
            .filter(|a| a.len() == 3)
            .ok_or("Invalid NPC position")?;
        let mut coordinates = Vec::new();
        for value in position {
            let number = value
                .as_f64()
                .filter(|n| n.is_finite() && n.abs() <= 1_000_000.0)
                .ok_or("Invalid NPC coordinate")?;
            coordinates.push(number as f32);
        }
        writeln!(output, "NpcDefinition {{ id: {id:?}, name: {name:?}, body: {body:?}, x: {:?}, y: {:?}, z: {:?} }},", coordinates[0], coordinates[1], coordinates[2]).unwrap();
    }
    output.push_str("];\n");
    output.push_str("pub const NPC_AREAS: &[NpcAreaDefinition] = &[\n");
    let mut spawn_ids: BTreeSet<&str> =
        placements.iter().filter_map(|p| p["id"].as_str()).collect();
    if doc["version"] == 3 {
        let areas = worlds[0]["areas"]
            .as_array()
            .filter(|a| a.len() + placements.len() <= 4096)
            .ok_or("Invalid NPC areas")?;
        for area in areas {
            exact(
                area,
                &["id", "actor_id", "bounds_cm", "respawn_interval_us"],
            )?;
            let id = area["id"]
                .as_str()
                .filter(|s| s.starts_with("spawn.") && s.len() <= 128)
                .ok_or("Invalid NPC area id")?;
            let actor = area["actor_id"].as_str().ok_or("Missing NPC area actor")?;
            if !spawn_ids.insert(id) || actors.iter().filter(|a| a["id"] == actor).count() != 1 {
                return Err("Duplicate area or unknown NPC actor".into());
            }
            let values = area["bounds_cm"]
                .as_array()
                .filter(|a| a.len() == 4)
                .ok_or("Invalid area bounds")?;
            let mut bounds = [0_i32; 4];
            for (slot, v) in bounds.iter_mut().zip(values) {
                *slot = i32::try_from(
                    v.as_u64()
                        .ok_or("NPC bounds must be nonnegative integers")?,
                )
                .map_err(|_| "NPC bounds exceed i32")?;
            }
            if bounds[0] > bounds[2] || bounds[1] > bounds[3] || bounds[..2] == bounds[2..] {
                return Err("NPC area must be an ordered non-point rectangle".into());
            }
            let interval = area["respawn_interval_us"]
                .as_i64()
                .filter(|v| (1_000_000..=86_400_000_000).contains(v))
                .ok_or("Invalid NPC retry interval")?;
            writeln!(output,"NpcAreaDefinition {{ id: {id:?}, actor_id: {actor:?}, bounds_cm: {bounds:?}, respawn_interval_us: {interval} }},").unwrap();
        }
    }
    output.push_str("];\n");
    Ok(output)
}

pub fn build() -> String {
    println!("cargo:rerun-if-changed=build_npcs.rs");
    if std::env::var_os("CARGO_FEATURE_YONGAN").is_none() {
        return TYPE.to_owned()
            + "pub const NPC_CATALOG_HASH: &str = \"\";\npub const NPCS: &[NpcDefinition] = &[];\npub const NPC_AREAS: &[NpcAreaDefinition] = &[];\n";
    }
    let catalog = "../client/assets/imported/npcs/catalog.v1.json";
    let actions = "../content/worlds/yongan.interactions.json";
    for path in [catalog, actions, "content/yongan.sha256"] {
        println!("cargo:rerun-if-changed={path}");
    }
    // The offline terrain example does not include trusted_definitions.rs.
    // Emit a compile error in the game module, allowing the inspector to build
    // the first NPC catalog while an ordinary server build still fails closed.
    let result = (|| -> Result<String, String> {
        let bytes =
            std::fs::read(catalog).map_err(|_| "Run make npc-install before building Yongan")?;
        let actions = std::fs::read(actions).map_err(|_| "NPC interaction profile missing")?;
        let actions =
            serde_json::from_slice(&actions).map_err(|_| "Invalid NPC interaction JSON")?;
        let map_hash =
            std::fs::read_to_string("content/yongan.sha256").map_err(|_| "Map hash missing")?;
        generate(&bytes, &actions, map_hash.trim())
    })();
    result.unwrap_or_else(|message| format!("{TYPE}compile_error!({message:?});\npub const NPC_CATALOG_HASH: &str = \"\";\npub const NPCS: &[NpcDefinition] = &[];\n"))
}
