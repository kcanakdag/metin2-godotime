//! Validated original group inventory shared by build tools and runtime preparation.
//! The caller verifies artifact provenance/hash before parsing this payload.
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug)]
pub struct Catalog {
    pub groups: BTreeMap<u32, Vec<u32>>,
    pub selectors: BTreeMap<u32, Vec<u32>>,
    pub entries: Vec<Entry>,
}

#[derive(Debug)]
pub struct Entry {
    pub source_line: u32,
    pub selector: bool,
    pub reference: u32,
    pub bounds_cm: [i32; 4],
    pub interval_us: i64,
    pub capacity: usize,
    pub forced_aggressive: bool,
}

fn id(value: &Value) -> Result<u32, String> {
    value
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .filter(|n| *n > 0)
        .ok_or("Expected positive population ID".into())
}

fn rows<'a>(value: &'a Value, key: &str) -> Result<&'a Vec<Value>, String> {
    value[key]
        .as_array()
        .filter(|v| !v.is_empty() && v.len() <= 16384)
        .ok_or_else(|| format!("Missing, empty or oversized population {key}"))
}

impl Catalog {
    pub fn parse(root: &Value) -> Result<Self, String> {
        if root["schema"] != "mt2spacetime.original-mob-population" || root["version"] != 1 {
            return Err("Unsupported population schema".into());
        }
        let mut groups = BTreeMap::new();
        for group in rows(root, "groups")? {
            let members = rows(group, "members")?;
            if members.len() > 256 {
                return Err("Group exceeds 256 members".into());
            }
            let mut definitions = Vec::new();
            for (slot, member) in members.iter().enumerate() {
                if member["slot"].as_u64() != Some(slot as u64)
                    || member["leader"].as_bool() != Some(slot == 0)
                {
                    return Err("Group slots or leader differ from source ordering".into());
                }
                definitions.push(id(&member["vnum"])?);
            }
            if groups.insert(id(&group["vnum"])?, definitions).is_some() {
                return Err("Duplicate population group".into());
            }
        }
        let mut selectors = BTreeMap::new();
        for selector in rows(root, "group_selectors")? {
            let mut choices = Vec::new();
            for (index, variant) in rows(selector, "variants")?.iter().enumerate() {
                let group = id(&variant["group_vnum"])?;
                if variant["slot"].as_u64() != Some(index as u64 + 1)
                    || variant["effective_weight"] != 1
                    || !groups.contains_key(&group)
                {
                    return Err("Invalid selector ordering, weight or group reference".into());
                }
                choices.push(group);
            }
            if selectors.insert(id(&selector["vnum"])?, choices).is_some() {
                return Err("Duplicate population selector".into());
            }
        }
        let mut entries = Vec::new();
        let mut lines = BTreeSet::new();
        for row in rows(root, "entries")? {
            let source_line = id(&row["source_line"])?;
            let reference = id(&row["reference_vnum"])?;
            let (selector, forced_aggressive) = match row["family"].as_str() {
                Some("g") => (false, false),
                Some("ga") => (false, true),
                Some("r") => (true, false),
                _ => return Err("Unsupported regeneration family".into()),
            };
            let interval_us = row["interval_us"]
                .as_i64()
                .filter(|n| (0..=86_400_000_000).contains(n))
                .ok_or("Invalid interval")?;
            let capacity = row["max_live_units"]
                .as_u64()
                .filter(|n| *n <= 1000)
                .ok_or("Invalid regeneration capacity")? as usize;
            let bounds_cm: [i32; 4] = rows(row, "bounds_cm")?
                .iter()
                .map(|v| {
                    v.as_i64()
                        .and_then(|n| i32::try_from(n).ok())
                        .ok_or("Invalid rectangle coordinate")
                })
                .collect::<Result<Vec<_>, _>>()?
                .try_into()
                .map_err(|_| "Expected four bounds")?;
            let [left, top, right, bottom] = bounds_cm;
            if !lines.insert(source_line)
                || left < 0
                || top < 0
                || right < left
                || bottom < top
                || (left == right && top == bottom)
                || row["enabled"].as_bool() != Some(interval_us > 0)
                || row["forced_aggressive"].as_bool() != Some(forced_aggressive)
                || if selector {
                    !selectors.contains_key(&reference)
                } else {
                    !groups.contains_key(&reference)
                }
            {
                return Err(
                    "Invalid population entry identity, rectangle, flags or reference".into(),
                );
            }
            entries.push(Entry {
                source_line,
                selector,
                reference,
                bounds_cm,
                interval_us,
                capacity,
                forced_aggressive,
            });
        }
        Ok(Self {
            groups,
            selectors,
            entries,
        })
    }
}
