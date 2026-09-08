//! Offline upper-bound lifecycle exercise; no map placement or database mutations.
#[path = "../src/regeneration.rs"]
mod regeneration;
use regeneration::{EntrySnapshot, EntryState};
#[path = "../src/monster_allocation.rs"]
mod monster_allocation;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
#[path = "../src/population_catalog.rs"]
mod population_catalog;
use std::io::Write;

fn snapshot(value: &Value) -> Result<EntrySnapshot, String> {
    Ok(EntrySnapshot {
        initial: value["initial"]
            .as_bool()
            .ok_or("Invalid saved initial flag")?,
        next_tick_us: if value["next_tick_us"].is_null() {
            None
        } else {
            Some(
                value["next_tick_us"]
                    .as_i64()
                    .ok_or("Invalid saved deadline")?,
            )
        },
        last_owner: value["last_owner"]
            .as_u64()
            .ok_or("Invalid saved owner counter")?,
        owners: value["owners"]
            .as_array()
            .ok_or("Missing saved owners")?
            .iter()
            .map(|v| v.as_u64().ok_or_else(|| "Invalid saved owner token".into()))
            .collect::<Result<_, String>>()?,
    })
}

fn run() -> Result<Value, String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if !matches!(args.len(), 1 | 3)
        || (args.len() == 3 && !matches!(args[1].as_str(), "--checkpoint" | "--resume"))
    {
        return Err(
            "Usage: regeneration_stress POPULATION [--checkpoint NEW_FILE | --resume FILE]".into(),
        );
    }
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
    let saved: Option<Value> = if args.get(1).is_some_and(|s| s == "--resume") {
        let bytes = std::fs::read(&args[2]).map_err(|e| e.to_string())?;
        if bytes.len() > 16 * 1024 * 1024 {
            return Err("Checkpoint exceeds 16 MiB".into());
        }
        let saved: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        if saved["version"] != 2 || saved["inventory_hash"] != hash {
            return Err("Checkpoint belongs to another inventory or schema".into());
        }
        Some(saved)
    } else {
        None
    };
    let catalog = population_catalog::Catalog::parse(&root)?;
    let entries = &catalog.entries;
    let mut sequence = if let Some(saved) = &saved {
        if saved["entries"]
            .as_array()
            .ok_or("Missing saved entries")?
            .len()
            != entries.len()
        {
            return Err("Checkpoint entry count differs".into());
        }
        saved["sequence"]
            .as_u64()
            .ok_or("Missing saved allocation counter")?
    } else {
        0
    };
    let mut states = Vec::new();
    let mut checkpoint_rows = Vec::new();
    let mut all_owners = std::collections::BTreeSet::new();
    let mut initial_members = 0_usize;
    let mut initial_units = 0_usize;
    for (index, entry) in entries.iter().enumerate() {
        let interval = entry.interval_us;
        let capacity = entry.capacity;
        let members = if entry.selector {
            catalog.selectors[&entry.reference]
                .iter()
                .map(|group| catalog.groups[group].len())
                .max()
                .ok_or("Empty selector")?
        } else {
            catalog.groups[&entry.reference].len()
        };
        // These fields are validated even though this upper-bound tool does not
        // sample terrain or run AI; placement and live consumers must use them.
        let _placement_policy = (entry.bounds_cm, entry.forced_aggressive);
        let state = if let Some(saved) = &saved {
            let row = &saved["entries"][index];
            if row["source_line"] != entry.source_line {
                return Err("Checkpoint entry identity differs".into());
            }
            let restored = snapshot(row)?;
            if restored.last_owner > sequence {
                return Err("Checkpoint allocation counter precedes an issued token".into());
            }
            EntryState::restore(interval, capacity, 16, restored)?
        } else {
            EntryState::new(interval, capacity, 16)?.plan_tick(0, || {
                let allocation = monster_allocation::reserve(
                    u32::try_from(sequence).map_err(|_| "Saved monster ID counter exceeds u32")?,
                    members,
                )?;
                sequence = u64::from(allocation.last);
                Ok(Some(allocation.owner()))
            })?
        };
        if state.owners().iter().any(|id| !all_owners.insert(*id)) {
            return Err("Checkpoint owner belongs to multiple entries".into());
        }
        let row = state.snapshot();
        checkpoint_rows.push(json!({"source_line":entry.source_line,
            "initial":row.initial,"next_tick_us":row.next_tick_us,
            "last_owner":row.last_owner,"owners":row.owners}));
        initial_units += state.owners().len();
        initial_members += state.owners().len() * members;
        states.push((state, members));
    }
    if args.get(1).is_some_and(|s| s == "--checkpoint") {
        let checkpoint = json!({"version":2,"inventory_hash":hash,"sequence":sequence,
            "entries":checkpoint_rows});
        let bytes = serde_json::to_vec(&checkpoint).map_err(|e| e.to_string())?;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&args[2])
            .map_err(|e| e.to_string())?;
        file.write_all(&bytes).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        return Ok(json!({"checkpoint_written":true,"entries":entries.len(),
            "initial_units":initial_units,"initial_members":initial_members,
            "last_allocated_monster_id":sequence}));
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
                let allocation = monster_allocation::reserve(
                    u32::try_from(sequence).map_err(|_| "Saved monster ID counter exceeds u32")?,
                    members,
                )?;
                sequence = u64::from(allocation.last);
                Ok(Some(allocation.owner()))
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
        "restored_from_checkpoint":saved.is_some(),"last_allocated_monster_id":sequence,
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
