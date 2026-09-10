//! Join authored interactions to the same offline catalog used by presentation.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fmt::Write as _};
const TYPE: &str = "pub struct NpcDefinition { pub id: &'static str, pub vnum: u32, pub name: &'static str, pub title: &'static str, pub body: &'static str, pub x: f32, pub y: f32, pub z: f32 }\n pub struct NpcAreaDefinition { pub id: &'static str, pub actor_id: &'static str, pub bounds_cm: [i32;4], pub respawn_interval_us: i64 }\n pub struct NpcAreaDialogue { pub id: &'static str, pub vnum: u32, pub name: &'static str, pub title: &'static str, pub body: &'static str }\n";

fn exact(value: &Value, keys: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("Expected an NPC object")?;
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err("Unexpected NPC interaction fields".into());
    }
    Ok(())
}

/// Interaction rows carry an optional authored board title. The profile omits
/// it when the original script built the title dynamically, and the server then
/// falls back to the actor name, which is what the original board displayed.
fn interaction_row(value: &Value) -> Result<(), String> {
    let object = value.as_object().ok_or("Expected an NPC object")?;
    let base = ["spawn_id", "kind", "body"];
    let titled = ["spawn_id", "kind", "body", "title"];
    if object.len() == base.len() && base.iter().all(|key| object.contains_key(*key)) {
        return Ok(());
    }
    if object.len() == titled.len() && titled.iter().all(|key| object.contains_key(*key)) {
        return Ok(());
    }
    Err("Unexpected NPC interaction fields".into())
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
    // Areas are validated first so that every interaction row can resolve
    // against the complete placement/area set in a single pass.
    let mut spawn_ids: BTreeSet<&str> =
        placements.iter().filter_map(|p| p["id"].as_str()).collect();
    let mut areas = Vec::new();
    if doc["version"] == 3 {
        let listed = worlds[0]["areas"]
            .as_array()
            .filter(|a| a.len() + placements.len() <= 4096)
            .ok_or("Invalid NPC areas")?;
        for area in listed {
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
            areas.push((id, actor, bounds, interval));
        }
    }
    let mut output = TYPE.to_owned();
    output.push_str(&format!(
        "pub const NPC_CATALOG_HASH: &str = {:?};\n",
        format!("{:x}", Sha256::digest(catalog))
    ));
    output.push_str("pub const NPCS: &[NpcDefinition] = &[\n");
    let mut ids = BTreeSet::new();
    // Area rows carry dialogue only. Their position keeps living in the
    // mutable `npc_spawn` row owned by the placement sampler, so a wandering
    // NPC is still resolvable by the identical spawn id the client renders.
    let mut area_dialogues = Vec::new();
    for row in rows {
        interaction_row(row)?;
        let id = row["spawn_id"].as_str().ok_or("Missing NPC spawn id")?;
        let body = row["body"].as_str().ok_or("Missing dialogue text")?;
        // The authored title is optional; an absent one becomes the empty
        // string, so the runtime falls back to the actor name.
        let title = match row.get("title") {
            None => "",
            Some(value) => value
                .as_str()
                .filter(|title| {
                    !title.is_empty()
                        && title.chars().count() <= 160
                        && !title.chars().any(|c| c.is_control())
                })
                .ok_or("Invalid NPC dialogue title")?,
        };
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
        let area_match = areas.iter().find(|area| area.0 == id);
        if matches.len() + usize::from(area_match.is_some()) != 1 {
            return Err("Interaction must resolve exactly one NPC placement or area".into());
        }
        let (actor_id, position) = match matches.first() {
            Some(spawn) => {
                let position = spawn["position"]
                    .as_array()
                    .filter(|a| a.len() == 3)
                    .ok_or("Invalid NPC position")?;
                let mut coordinates = [0.0_f32; 3];
                for (slot, value) in coordinates.iter_mut().zip(position) {
                    let number = value
                        .as_f64()
                        .filter(|n| n.is_finite() && n.abs() <= 1_000_000.0)
                        .ok_or("Invalid NPC coordinate")?;
                    *slot = number as f32;
                }
                (
                    spawn["actor_id"].as_str().ok_or("Missing NPC actor")?,
                    Some(coordinates),
                )
            }
            None => (
                area_match
                    .ok_or("Interaction must resolve exactly one NPC")?
                    .1,
                None,
            ),
        };
        let models: Vec<_> = actors.iter().filter(|a| a["id"] == actor_id).collect();
        if models.len() != 1 {
            return Err("Interaction must resolve exactly one NPC actor".into());
        }
        let name = models[0]["name"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 160)
            .ok_or("Invalid NPC name")?;
        let vnum = u32::try_from(
            models[0]["vnum"]
                .as_u64()
                .filter(|value| (1..=u32::MAX as u64).contains(value))
                .ok_or("Invalid NPC vnum")?,
        )
        .map_err(|_| "Invalid NPC vnum")?;
        match position {
            Some([x, y, z]) => writeln!(output, "NpcDefinition {{ id: {id:?}, vnum: {vnum}, name: {name:?}, title: {title:?}, body: {body:?}, x: {x:?}, y: {y:?}, z: {z:?} }},").unwrap(),
            None => area_dialogues.push((id, vnum, name, title, body)),
        }
    }
    output.push_str("];\n");
    output.push_str("pub const NPC_AREAS: &[NpcAreaDefinition] = &[\n");
    for (id, actor, bounds, interval) in &areas {
        writeln!(output,"NpcAreaDefinition {{ id: {id:?}, actor_id: {actor:?}, bounds_cm: {bounds:?}, respawn_interval_us: {interval} }},").unwrap();
    }
    output.push_str("];\n");
    output.push_str("pub const NPC_AREA_DIALOGUES: &[NpcAreaDialogue] = &[\n");
    for (id, vnum, name, title, body) in &area_dialogues {
        writeln!(output,"NpcAreaDialogue {{ id: {id:?}, vnum: {vnum}, name: {name:?}, title: {title:?}, body: {body:?} }},").unwrap();
    }
    output.push_str("];\n");
    // A wandering placement with no dialogue would still render and accept a
    // click that the server could not answer, so coverage is enforced here.
    let covered: BTreeSet<&str> = area_dialogues.iter().map(|row| row.0).collect();
    if let Some(missing) = areas
        .iter()
        .map(|area| area.0)
        .find(|id| !covered.contains(id))
    {
        return Err(format!("Area NPC {missing} has no dialogue row"));
    }
    Ok(output)
}

pub fn build() -> String {
    println!("cargo:rerun-if-changed=build_npcs.rs");
    if std::env::var_os("CARGO_FEATURE_YONGAN").is_none() {
        return TYPE.to_owned()
            + "pub const NPC_CATALOG_HASH: &str = \"\";\npub const NPCS: &[NpcDefinition] = &[];\npub const NPC_AREAS: &[NpcAreaDefinition] = &[];\npub const NPC_AREA_DIALOGUES: &[NpcAreaDialogue] = &[];\n";
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
    result.unwrap_or_else(|message| format!("{TYPE}compile_error!({message:?});\npub const NPC_CATALOG_HASH: &str = \"\";\npub const NPCS: &[NpcDefinition] = &[];\npub const NPC_AREAS: &[NpcAreaDefinition] = &[];\npub const NPC_AREA_DIALOGUES: &[NpcAreaDialogue] = &[];\n"))
}
