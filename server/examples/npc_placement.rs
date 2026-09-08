//! Offline area-placement qualification using the game's real terrain and shared sampler.
#[allow(dead_code)]
#[path = "../src/content.rs"]
mod content;
#[allow(dead_code)]
#[path = "../src/movement.rs"]
mod movement;
// This stationary-NPC tool uses Area; group placement is exercised by
// the separate population_placement example and shared module tests.
#[allow(dead_code)]
#[path = "../src/npc_placement.rs"]
mod npc_placement;

use serde_json::{Value, json};
use spacetimedb::rand::{Rng, SeedableRng, rngs::StdRng};
use std::io::Read;

fn inspect() -> Result<Value, String> {
    let mut input = String::new();
    std::io::stdin()
        .take(256 * 1024 + 1)
        .read_to_string(&mut input)
        .map_err(|e| e.to_string())?;
    if input.len() > 256 * 1024 {
        return Err("NPC request exceeds 256 KiB".into());
    }
    let request: Value = serde_json::from_str(&input).map_err(|e| e.to_string())?;
    let seed = request["preview_seed"]
        .as_u64()
        .ok_or("Missing offline preview seed")?;
    let areas = request["areas"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 4096)
        .ok_or("Expected 1..4096 area definitions")?;
    let mut random = StdRng::seed_from_u64(seed);
    let mut ids = std::collections::BTreeSet::new();
    let mut rows = Vec::new();
    for area in areas {
        let id = area["id"]
            .as_str()
            .filter(|s| s.len() <= 128 && s.starts_with("spawn."))
            .ok_or("Invalid NPC spawn ID")?;
        if !ids.insert(id)
            || area["map_id"] != "metin2_map_a1"
            || !content::YONGAN
            || area["position_policy"] != "server-random-area"
            || area["position_step_cm"] != 1
            || area["spawn_attempts"] != 16
            || area["heading_policy"] != "random-integer-degree"
            || area["heading_bounds_degrees"] != json!([0, 360])
        {
            return Err("Unsupported or duplicate original NPC area policy".into());
        }
        let values = area["bounds_cm"]
            .as_array()
            .filter(|a| a.len() == 4)
            .ok_or("Invalid NPC bounds")?;
        let mut bounds = [0; 4];
        for (slot, value) in bounds.iter_mut().zip(values) {
            *slot = i32::try_from(value.as_i64().ok_or("NPC bounds must be integers")?)
                .map_err(|_| "NPC bounds exceed i32")?;
        }
        let placement = npc_placement::Area::new(bounds)?.sample(
            |lo, hi| random.gen_range(lo..=hi),
            |x, z| {
                content::valid_npc_position(x, z)
                    .ok()
                    .map(|()| content::height(x, z))
            },
        )?;
        let p =
            placement.ok_or_else(|| format!("No valid NPC terrain in sixteen attempts: {id}"))?;
        rows.push(
            json!({"id":id,"x_cm":p.x_cm,"z_cm":p.z_cm,"height_m":p.height_m,
            "heading_degrees":p.heading_degrees,"yaw":p.yaw()}),
        );
    }
    Ok(
        json!({"purpose":"offline-preview-not-live-placement","map_content_hash":content::HASH.trim(),
        "preview_seed":seed,"placements":rows}),
    )
}

fn main() {
    match inspect() {
        Ok(value) => println!("{value}"),
        Err(error) => {
            eprintln!("NPC placement qualification failed: {error}");
            std::process::exit(1);
        }
    }
}
