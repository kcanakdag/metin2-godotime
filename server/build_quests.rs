//! Embed the compiled quest catalog in the module so the authority and the
//! client resolve the same quest states, text and rewards.
use std::fmt::Write as _;

const TYPE: &str =
    "pub const QUEST_CATALOG: &str = \"\";\npub const QUEST_CATALOG_HASH: &str = \"\";\n";

fn empty() -> String {
    TYPE.to_owned()
}

pub fn generate(catalog: &[u8]) -> Result<String, String> {
    let text = std::str::from_utf8(catalog).map_err(|_| "Quest catalog must be UTF-8")?;
    let doc: serde_json::Value =
        serde_json::from_str(text).map_err(|_| "Quest catalog is not valid JSON")?;
    if doc["schema"] != "mt2spacetime.static-quests" || doc["version"].as_u64() != Some(1) {
        return Err("Unsupported quest catalog".into());
    }
    let hash = doc["content_hash"]
        .as_str()
        .filter(|value| value.len() == 64)
        .ok_or("Quest catalog is missing its content hash")?;
    let mut output = TYPE.to_owned();
    output.clear();
    writeln!(output, "pub const QUEST_CATALOG_HASH: &str = {hash:?};").unwrap();
    writeln!(output, "pub const QUEST_CATALOG: &str = {text:?};").unwrap();
    Ok(output)
}

pub fn build() -> String {
    println!("cargo:rerun-if-env-changed=MT2_QUEST_CATALOG");
    let path = std::env::var("MT2_QUEST_CATALOG")
        .unwrap_or_else(|_| "../client/assets/imported/quests/catalog.v1.json".into());
    println!("cargo:rerun-if-changed={path}");
    match std::fs::read(&path) {
        Ok(catalog) => {
            generate(&catalog).unwrap_or_else(|error| format!("{TYPE}compile_error!({error:?});\n"))
        }
        // A checkout without exported quest content still builds, but the empty
        // catalog fails closed: no quest can be started and the client hash is
        // empty, which the client compares against its own content.
        Err(_) => empty(),
    }
}
