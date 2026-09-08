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
