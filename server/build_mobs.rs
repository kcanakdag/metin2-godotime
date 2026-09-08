//! Verify a locally compiled mob package before linking its generated registry.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::Path;

pub struct Package {
    pub gameplay_hash: String,
    pub registry: String,
}

fn read(root: &Path, name: &str) -> Result<Vec<u8>, String> {
    let path = root.join(name);
    println!("cargo:rerun-if-changed={}", path.display());
    let bytes = std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err(format!("{name} exceeds 16 MiB"));
    }
    Ok(bytes)
}

pub fn load(root: &Path) -> Result<Package, String> {
    let receipt: Value =
        serde_json::from_slice(&read(root, "receipt.json")?).map_err(|e| e.to_string())?;
    let gameplay = read(root, "gameplay.v1.json")?;
    let presentation = read(root, "presentation.v1.json")?;
    let registry = read(root, "combat-registry.rs")?;
    for (bytes, key) in [
        (&gameplay, "catalog_sha256"),
        (&presentation, "presentation_sha256"),
        (&registry, "combat_registry_sha256"),
    ] {
        if receipt[key] != format!("{:x}", Sha256::digest(bytes)) {
            return Err(format!("Mob package {key} mismatch"));
        }
    }
    let gameplay: Value = serde_json::from_slice(&gameplay).map_err(|e| e.to_string())?;
    let presentation: Value = serde_json::from_slice(&presentation).map_err(|e| e.to_string())?;
    let hash = receipt["content_hash"]
        .as_str()
        .ok_or("Missing mob gameplay hash")?;
    if hash.len() != 64
        || !hash
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        || gameplay["content_hash"] != hash
        || presentation["gameplay_hash"] != hash
    {
        return Err("Mob package gameplay identities differ".into());
    }
    let registry = String::from_utf8(registry).map_err(|e| e.to_string())?;
    if !registry.contains("pub const MOBS: &[MobDefinition]") {
        return Err("Mob package lacks assembled definitions; rebuild it".into());
    }
    Ok(Package {
        gameplay_hash: hash.into(),
        registry,
    })
}
