#[path = "../build_mobs.rs"]
mod build_mobs;
use serde_json::json;
use sha2::{Digest, Sha256};

#[test]
fn package_requires_matching_bytes_and_gameplay_identities() {
    let dir = std::env::temp_dir().join(format!("mt2-mob-package-{}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    let hash = "a".repeat(64);
    let gameplay = json!({"content_hash":hash,"mobs":[{"vnum":101}]}).to_string();
    let presentation = json!({"gameplay_hash":hash,"actors":[{
        "kind":"mob","vnum":101,"id":"actor.mob.test","modes":[{"id":"general","motions":[{
            "action":"front_damage","action_id":"actor.mob.test.general.front_damage",
            "duration_us":500000,"weight":100,"loop":false,"events":[]
        }]}]
    }]})
    .to_string();
    let registry = "pub const MOBS: &[MobDefinition] = &[];";
    let digest = |text: &str| format!("{:x}", Sha256::digest(text.as_bytes()));
    let receipt = json!({"content_hash":hash,"catalog_sha256":digest(&gameplay),
        "presentation_sha256":digest(&presentation),"combat_registry_sha256":digest(registry)});
    std::fs::write(dir.join("receipt.json"), receipt.to_string()).unwrap();
    for (name, bytes) in [
        ("gameplay.v1.json", gameplay.as_str()),
        ("presentation.v1.json", presentation.as_str()),
        ("combat-registry.rs", registry),
    ] {
        std::fs::write(dir.join(name), bytes).unwrap();
    }
    let package = build_mobs::load(&dir).unwrap();
    assert_eq!(package.gameplay_hash, hash);
    assert!(package.registry.starts_with(registry));
    assert!(package.registry.contains("GOOD_REACTIONS"));
    assert_eq!(package.vnums, [101].into());
    for (name, original) in [
        ("gameplay.v1.json", gameplay.as_str()),
        ("presentation.v1.json", presentation.as_str()),
        ("combat-registry.rs", registry),
    ] {
        std::fs::write(dir.join(name), "corrupt").unwrap();
        assert!(build_mobs::load(&dir).is_err(), "{name}");
        std::fs::write(dir.join(name), original).unwrap();
    }
    let mut mismatch = receipt;
    mismatch["content_hash"] = json!("b".repeat(64));
    std::fs::write(dir.join("receipt.json"), mismatch.to_string()).unwrap();
    assert!(build_mobs::load(&dir).is_err());
    std::fs::remove_dir_all(dir).unwrap();
}
