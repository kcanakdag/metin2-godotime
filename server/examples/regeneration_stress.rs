//! Offline upper-bound lifecycle exercise; no map placement or database mutations.
#[path = "../src/regeneration.rs"]
mod regeneration;
use regeneration::EntryState;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

fn run() -> Result<Value, String> {
    let path = std::env::args()
        .nth(1)
        .ok_or("Expected population.v1.json path")?;
    let bytes = std::fs::read(path).map_err(|e| e.to_string())?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("Population inventory exceeds 16 MiB".into());
    }
    let mut root: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    let hash = root
        .as_object_mut()
        .ok_or("Expected population object")?
        .remove("content_hash")
        .ok_or("Missing content hash")?;
    let actual = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&root).map_err(|e| e.to_string())?)
    );
    if hash.as_str() != Some(actual.as_str())
        || root["schema"] != "mt2spacetime.original-mob-population"
        || root["version"] != 1
        || root["runtime_policy"]["unit_release"] != "owner-destruction"
        || root["runtime_policy"]["zero_interval"] != "disabled-including-initial-spawn"
    {
        return Err("Inventory hash, schema or lifecycle contract differs".into());
    }
    let array = |key: &str| root[key].as_array().ok_or_else(|| format!("Missing {key}"));
    let mut groups = BTreeMap::new();
    for group in array("groups")? {
        let id = group["vnum"].as_u64().ok_or("Invalid group ID")?;
        let count = group["members"]
            .as_array()
            .ok_or("Missing group members")?
            .len();
        if !(1..=256).contains(&count) || groups.insert(id, count).is_some() {
            return Err("Invalid or duplicate group".into());
        }
    }
    let mut selectors = BTreeMap::new();
    for selector in array("group_selectors")? {
        let mut maximum = 0;
        for variant in selector["variants"]
            .as_array()
            .ok_or("Missing selector variants")?
        {
            let id = variant["group_vnum"]
                .as_u64()
                .ok_or("Invalid group reference")?;
            maximum = maximum.max(*groups.get(&id).ok_or("Unknown selector group")?);
        }
        let id = selector["vnum"].as_u64().ok_or("Invalid selector ID")?;
        if maximum == 0 || selectors.insert(id, maximum).is_some() {
            return Err("Empty or duplicate selector".into());
        }
    }
    let entries = array("entries")?;
    if entries.len() > 16384 {
        return Err("Too many regeneration entries".into());
    }
    let mut sequence = 0_u64;
    let mut states = Vec::new();
    let mut initial_members = 0_usize;
    let mut initial_units = 0_usize;
    for entry in entries {
        let interval = entry["interval_us"].as_i64().ok_or("Invalid interval")?;
        let capacity = usize::try_from(entry["max_live_units"].as_u64().ok_or("Invalid capacity")?)
            .map_err(|e| e.to_string())?;
        let id = entry["reference_vnum"]
            .as_u64()
            .ok_or("Invalid reference")?;
        let members = match entry["family"].as_str() {
            Some("m") => 1,
            Some("g" | "ga") => *groups.get(&id).ok_or("Unknown group")?,
            Some("r") => *selectors.get(&id).ok_or("Unknown selector")?,
            _ => return Err("Unsupported family".into()),
        };
        let state = EntryState::new(interval, capacity, 16)?.plan_tick(0, || {
            sequence += 1;
            Ok(Some(sequence))
        })?;
        initial_units += state.owners().len();
        initial_members += state.owners().len() * members;
        states.push((state, members));
    }
    let survivors = initial_members - initial_units;
    let mut replacement_members = 0;
    let mut replacements = 0;
    for (mut state, members) in states {
        let owners: Vec<_> = state.owners().iter().copied().collect();
        for owner in owners {
            if !state.owner_destroyed(owner) || state.owner_destroyed(owner) {
                return Err("Owner destruction was not exactly once".into());
            }
        }
        if let Some(due) = state.next_tick_us() {
            let state = state.plan_tick(due, || {
                sequence += 1;
                Ok(Some(sequence))
            })?;
            replacements += state.owners().len();
            replacement_members += state.owners().len() * members;
        }
    }
    if replacements != initial_units || replacement_members != initial_members {
        return Err("Replacement did not refill original unit capacities".into());
    }
    Ok(
        json!({"scenario":"largest-group-all-placements-succeed-followers-survive",
        "inventory_hash":hash,"entries":entries.len(),"initial_units":initial_units,
        "initial_members":initial_members,"surviving_followers":survivors,
        "replacement_units":replacements,"members_after_refill":survivors+replacement_members,
        "live_gameplay":false,"map_placement_tested":false}),
    )
}

fn main() {
    match run() {
        Ok(report) => println!("{report}"),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
