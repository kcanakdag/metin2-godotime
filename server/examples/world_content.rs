//! Offline authoring inspector. No SpacetimeDB connection or privileged reducers.
#[path = "../build_population.rs"]
mod build_population;
// The CLI deliberately calls only the authoring subset of these shared modules.
#[allow(dead_code)]
#[path = "../src/content.rs"]
mod content;
#[allow(dead_code)]
#[path = "../src/movement.rs"]
mod movement;

use serde_json::{Value, json};
use std::io::Read;

fn inspect() -> Result<Value, String> {
    let mut input = String::new();
    std::io::stdin()
        .take(256 * 1024 + 1)
        .read_to_string(&mut input)
        .map_err(|error| error.to_string())?;
    if input.len() > 256 * 1024 {
        return Err("Authoring request exceeds 256 KiB".into());
    }
    let request: Value = serde_json::from_str(&input).map_err(|error| error.to_string())?;
    let map_id = if content::YONGAN {
        "metin2_map_a1"
    } else {
        "training"
    };
    let definitions: Value =
        serde_json::from_str(include_str!("../content/p0-warrior-dog/actions.v1.json"))
            .map_err(|error| error.to_string())?;
    // The definition artifact's selected actor is the available runtime handler.
    let mobs: Vec<_> = definitions["actors"]
        .as_array()
        .ok_or("Missing trusted actors")?
        .iter()
        .filter(|row| row.get("vnum").is_some())
        .collect();
    if mobs.len() != 1 {
        return Err("Expected one currently supported mob definition".into());
    }
    let vnum = u32::try_from(mobs[0]["vnum"].as_u64().ok_or("Missing mob vnum")?)
        .map_err(|_| "Invalid mob vnum")?;
    let spawns = build_population::parse(&request["profile"], map_id, &[vnum])?;
    let rows: Vec<_> = spawns
        .iter()
        .map(|spawn| {
            let validation = content::valid_spawn(spawn.home_x, spawn.home_z);
            json!({"id": spawn.id, "definition_vnum": spawn.definition_vnum, "x": spawn.home_x,
            "y": content::height(spawn.home_x, spawn.home_z), "z": spawn.home_z,
            "valid": validation.is_ok(), "error": validation.err()})
        })
        .collect();
    let points = request["points"]
        .as_array()
        .ok_or("Points must be an array")?;
    if points.len() > 4096 {
        return Err("Too many inspection points".into());
    }
    let mut samples = Vec::new();
    let point_policy = request["point_policy"].as_str().unwrap_or("walkable");
    if !matches!(point_policy, "walkable" | "static_npc") {
        return Err("Unsupported point inspection policy".into());
    }
    for point in points {
        let x = point["x"].as_f64().ok_or("Invalid inspection X")? as f32;
        let z = point["z"].as_f64().ok_or("Invalid inspection Z")? as f32;
        let validation = if point_policy == "static_npc" {
            content::valid_npc_position(x, z)
        } else {
            content::valid_spawn(x, z)
        };
        samples.push(
            json!({"id":point["id"], "x":x,"y":content::height(x,z),"z":z,
            "valid":validation.is_ok(),"error":validation.err()}),
        );
    }
    let valid = rows
        .iter()
        .chain(samples.iter())
        .all(|row| row["valid"] == true);
    Ok(
        json!({"valid":valid, "map_id":map_id, "map_content_hash":content::HASH.trim(),
        "spawns":rows,"points":samples, "profile":request["profile"]}),
    )
}

fn main() {
    match inspect() {
        Ok(report) => println!("{}", serde_json::to_string_pretty(&report).unwrap()),
        Err(error) => {
            eprintln!("World content validation failed: {error}");
            std::process::exit(1);
        }
    }
}
