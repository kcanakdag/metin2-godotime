//! Embed the compiled drop catalog in the module so a kill rolls exactly the
//! table the pinned loader produced, without shipping the research corpus.
use std::fmt::Write as _;

const TYPE: &str =
    "pub const DROP_CATALOG: &str = \"\";\npub const DROP_CATALOG_HASH: &str = \"\";\n";

fn empty() -> String {
    TYPE.to_owned()
}

pub fn generate(catalog: &[u8]) -> Result<String, String> {
    let text = std::str::from_utf8(catalog).map_err(|_| "Drop catalog must be UTF-8")?;
    let doc: serde_json::Value =
        serde_json::from_str(text).map_err(|_| "Drop catalog is not valid JSON")?;
    if doc["schema"] != "mt2spacetime.static-drops" || doc["version"].as_u64() != Some(1) {
        return Err("Unsupported drop catalog".into());
    }
    let hash = doc["content_hash"]
        .as_str()
        .filter(|value| value.len() == 64)
        .ok_or("Drop catalog is missing its content hash")?;
    for key in ["normal_percent", "boss_percent"] {
        let table = doc["level_delta"][key]
            .as_array()
            .ok_or("Drop catalog is missing its level-delta table")?;
        if table.len() != 31
            || table
                .iter()
                .any(|value| value.as_u64().is_none_or(|percent| percent > 1000))
        {
            return Err(format!(
                "Drop catalog {key} must hold 31 percentages within 0..1000"
            ));
        }
    }
    let mut output = TYPE.to_owned();
    output.clear();
    writeln!(output, "pub const DROP_CATALOG_HASH: &str = {hash:?};").unwrap();
    writeln!(output, "pub const DROP_CATALOG: &str = {text:?};").unwrap();
    Ok(output)
}

pub fn build() -> String {
    println!("cargo:rerun-if-env-changed=MT2_DROP_CATALOG");
    let path = std::env::var("MT2_DROP_CATALOG")
        .unwrap_or_else(|_| "content/drops/catalog.v1.json".into());
    println!("cargo:rerun-if-changed={path}");
    match std::fs::read(&path) {
        Ok(catalog) => {
            generate(&catalog).unwrap_or_else(|error| format!("{TYPE}compile_error!({error:?});\n"))
        }
        // A checkout without converted drop content still builds, but the empty
        // catalog fails closed: a kill drops nothing instead of guessing.
        Err(_) => empty(),
    }
}
