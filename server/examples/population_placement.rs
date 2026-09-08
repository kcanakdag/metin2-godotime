//! Seeded original group placement against the server's real baked map collision.
// The inspector uses only the placement subset of the shared map/movement modules.
#[allow(dead_code)]
#[path = "../src/content.rs"]
mod content;
#[allow(dead_code)]
#[path = "../src/movement.rs"]
mod movement;
#[path = "../src/npc_placement.rs"]
mod npc_placement;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use spacetimedb::rand::{Rng, SeedableRng, rngs::StdRng};
use std::collections::BTreeMap;

fn inspect() -> Result<Value, String> {
    if !content::YONGAN {
        return Err("Build with --features yongan for this original-map inspector".into());
    }
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 2 {
        return Err("Usage: population_placement POPULATION_JSON SEED".into());
    }
    let seed: u64 = args[1].parse().map_err(|_| "Invalid seed")?;
    let bytes = std::fs::read(&args[0]).map_err(|e| e.to_string())?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("Population exceeds 16 MiB".into());
    }
    let mut root: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    let hash = root
        .as_object_mut()
        .ok_or("Expected inventory object")?
        .remove("content_hash")
        .ok_or("Missing inventory hash")?;
    let actual = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&root).map_err(|e| e.to_string())?)
    );
    if hash != actual
        || root["map"] != "metin2_map_a1"
        || root["schema"] != "mt2spacetime.original-mob-population"
        || root["version"] != 1
    {
        return Err("Inventory hash, map or schema differs".into());
    }
    let mut groups = BTreeMap::new();
    for group in root["groups"].as_array().ok_or("Missing groups")? {
        let id = group["vnum"].as_u64().ok_or("Invalid group ID")?;
        let members = group["members"]
            .as_array()
            .ok_or("Missing members")?
            .iter()
            .map(|m| {
                m["vnum"]
                    .as_u64()
                    .and_then(|v| u32::try_from(v).ok())
                    .ok_or("Invalid member")
            })
            .collect::<Result<Vec<_>, _>>()?;
        if groups.insert(id, members).is_some() {
            return Err("Duplicate group".into());
        }
    }
    let mut selectors = BTreeMap::new();
    for selector in root["group_selectors"]
        .as_array()
        .ok_or("Missing selectors")?
    {
        let id = selector["vnum"].as_u64().ok_or("Invalid selector ID")?;
        let mut choices = Vec::new();
        for variant in selector["variants"].as_array().ok_or("Missing variants")? {
            let group = variant["group_vnum"]
                .as_u64()
                .ok_or("Invalid selector group")?;
            if variant["effective_weight"] != 1 || !groups.contains_key(&group) {
                return Err("Unsupported selector weight or missing group".into());
            }
            choices.push(group);
        }
        if choices.is_empty() || selectors.insert(id, choices).is_some() {
            return Err("Empty or duplicate selector".into());
        }
    }
    let mut rng = StdRng::seed_from_u64(seed);
    let mut placements = Vec::new();
    let mut failed_units = 0;
    let mut failed_followers = 0;
    let mut units = 0;
    let entries = root["entries"].as_array().ok_or("Missing entries")?;
    if entries.len() > 16384 {
        return Err("Too many entries".into());
    }
    for entry in entries {
        let interval = entry["interval_us"].as_i64().ok_or("Invalid interval")?;
        if !(0..=86_400_000_000).contains(&interval) {
            return Err("Invalid interval".into());
        }
        if interval == 0 {
            continue;
        }
        let count = entry["max_live_units"]
            .as_u64()
            .filter(|v| *v <= 1000)
            .ok_or("Invalid capacity")?;
        let reference = entry["reference_vnum"]
            .as_u64()
            .ok_or("Invalid reference")?;
        let bounds: [i32; 4] = entry["bounds_cm"]
            .as_array()
            .ok_or("Missing bounds")?
            .iter()
            .map(|v| {
                v.as_i64()
                    .and_then(|i| i32::try_from(i).ok())
                    .ok_or("Invalid bound")
            })
            .collect::<Result<Vec<_>, _>>()?
            .try_into()
            .map_err(|_| "Expected four bounds")?;
        for unit in 0..count {
            let group = match entry["family"].as_str() {
                Some("g" | "ga") => reference,
                Some("r") => {
                    let choices = selectors.get(&reference).ok_or("Unknown selector")?;
                    choices[rng.gen_range(0..choices.len())]
                }
                _ => return Err("This inspector currently supports group families only".into()),
            };
            let members = groups.get(&group).ok_or("Unknown group")?;
            let rows = npc_placement::sample_group(
                members,
                bounds,
                |lo, hi| rng.gen_range(lo..=hi),
                |_, x, z| {
                    content::valid_spawn(x, z)
                        .ok()
                        .map(|()| content::height(x, z))
                },
            )?;
            if rows.is_empty() {
                failed_units += 1;
                continue;
            }
            units += 1;
            failed_followers += members.len() - rows.len();
            for row in rows {
                let p = row.placement;
                placements.push(json!({"source_line":entry["source_line"],"unit":unit,
                    "group_vnum":group,"slot":row.slot,"vnum":row.vnum,
                    "x_cm":p.x_cm,"z_cm":p.z_cm,"height_m":p.height_m,
                    "heading_degrees":p.heading_degrees,"yaw":p.yaw()}));
            }
        }
    }
    Ok(
        json!({"inventory_hash":hash,"map_hash":content::HASH.trim(),"seed":seed,
        "entries":entries.len(),"placed_units":units,"failed_units":failed_units,
        "failed_followers":failed_followers,"placed_members":placements.len(),
        "placements":placements,"position_policy":"current-server-movement-footprint",
        "live_gameplay":false}),
    )
}

fn main() {
    match inspect() {
        Ok(report) => println!("{report}"),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
