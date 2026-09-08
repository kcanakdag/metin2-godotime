//! Trusted authoring limits shared by the compiler and its focused tests.
use serde_json::Value;

#[derive(Debug, PartialEq, Eq)]
pub struct Settings {
    pub id: u32,
    pub interval_us: u64,
    pub capacity: u64,
    pub startup_jitter_seconds: u64,
}

pub fn parse(value: &Value) -> Result<Settings, String> {
    let row = value
        .as_object()
        .ok_or("Regeneration settings must be an object")?;
    let fields = ["id", "interval_us", "capacity", "startup_jitter_seconds"];
    if row.len() != fields.len() || fields.iter().any(|key| !row.contains_key(*key)) {
        return Err("Expected exactly id, interval_us, capacity and startup_jitter_seconds".into());
    }
    let read = |key: &str, max: u64| {
        row[key]
            .as_u64()
            .filter(|v| *v <= max)
            .ok_or_else(|| format!("Regeneration {key} must be an integer within 0..={max}"))
    };
    let id = read("id", u64::from(u32::MAX))? as u32;
    if id == 0 {
        return Err("Regeneration entry ID must be positive".into());
    }
    Ok(Settings {
        id,
        interval_us: read("interval_us", 86_400_000_000)?,
        capacity: read("capacity", 1000)?,
        startup_jitter_seconds: read("startup_jitter_seconds", 16)?,
    })
}

#[derive(Debug, PartialEq, Eq)]
pub struct GroupArea {
    pub bounds_cm: [i32; 4],
    pub groups: Vec<Vec<u32>>,
}

pub fn parse_area(value: &Value, available: &[u32]) -> Result<GroupArea, String> {
    let row = value.as_object().ok_or("Group area must be an object")?;
    if row.len() != 2 || !row.contains_key("bounds_cm") || !row.contains_key("groups") {
        return Err("Expected group area bounds_cm and groups".into());
    }
    let bounds_cm: [i32; 4] = row["bounds_cm"]
        .as_array()
        .ok_or("Missing bounds")?
        .iter()
        .map(|v| {
            v.as_i64()
                .and_then(|n| i32::try_from(n).ok())
                .ok_or("Invalid bound")
        })
        .collect::<Result<Vec<_>, _>>()?
        .try_into()
        .map_err(|_| "Expected four bounds")?;
    let [left, top, right, bottom] = bounds_cm;
    if left < 0 || top < 0 || right < left || bottom < top || (left == right && top == bottom) {
        return Err("Invalid group area rectangle".into());
    }
    let rows = row["groups"]
        .as_array()
        .filter(|rows| !rows.is_empty() && rows.len() <= 256)
        .ok_or("Expected 1..=256 equal-weight group choices")?;
    let mut groups = Vec::new();
    for row in rows {
        let members = row
            .as_array()
            .filter(|r| !r.is_empty() && r.len() <= 256)
            .ok_or("Expected 1..=256 group members")?;
        groups.push(
            members
                .iter()
                .map(|v| {
                    v.as_u64()
                        .and_then(|n| u32::try_from(n).ok())
                        .filter(|n| *n != 0 && available.contains(n))
                        .ok_or("Group member has no installed definition")
                })
                .collect::<Result<Vec<_>, _>>()?,
        );
    }
    Ok(GroupArea { bounds_cm, groups })
}
