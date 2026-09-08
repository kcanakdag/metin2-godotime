//! Shared original population compiler for the build and offline inspection tool.
#[path = "src/population_catalog.rs"]
mod population_catalog;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt::Write;

pub fn compile(bytes: &[u8], registered: Option<&BTreeSet<u32>>) -> Result<String, String> {
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("Population exceeds 16 MiB".into());
    }
    let mut root: Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
    let claimed = root
        .as_object_mut()
        .ok_or("Expected inventory object")?
        .remove("content_hash")
        .ok_or("Missing inventory hash")?;
    let hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&root).map_err(|e| e.to_string())?)
    );
    if claimed != hash
        || root["map"] != "metin2_map_a1"
        || root["runtime_policy"]["first_tick_jitter_us"] != serde_json::json!([0, 16000000])
        || root["runtime_policy"]["first_tick_jitter_step_us"] != 1000000
        || root["runtime_policy"]["unit_release"] != "owner-destruction"
        || root["runtime_policy"]["zero_interval"] != "disabled-including-initial-spawn"
    {
        return Err("Inventory hash, map or regeneration policy differs".into());
    }
    let catalog = population_catalog::Catalog::parse(&root)?;
    if let Some(registered) = registered {
        for vnum in catalog.groups.values().flatten() {
            if !registered.contains(vnum) {
                return Err(format!("Population references uninstalled mob {vnum}"));
            }
        }
    }
    let mut output = format!(
        "// Original population compiled from verified inventory.\n// Inventory SHA-256: {hash}\n"
    );
    output
        .push_str("pub const ORIGINAL_REGENERATION_DEFINITIONS: &[RegenerationDefinition] = &[\n");
    for entry in &catalog.entries {
        let choices = if entry.selector {
            catalog.selectors[&entry.reference].clone()
        } else {
            vec![entry.reference]
        };
        let groups = choices
            .iter()
            .map(|id| format!("&{:?}", catalog.groups[id]))
            .collect::<Vec<_>>()
            .join(",");
        writeln!(output,"RegenerationDefinition {{ id: {}, interval_us: {}, capacity: {}, startup_jitter_max_seconds: 16, force_aggressive: {}, templates: &[], area: Some(RegenerationGroupArea {{ bounds_cm: {:?}, groups: &[{}] }}) }},",
            entry.source_line,entry.interval_us,entry.capacity,entry.forced_aggressive,entry.bounds_cm,groups).map_err(|e|e.to_string())?;
    }
    output.push_str("];\n");
    Ok(output)
}
