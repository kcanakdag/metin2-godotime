#[allow(dead_code)]
#[path = "../build_npcs.rs"]
mod build_npcs;
use serde_json::{Value, json};
fn fixtures() -> (Value, Value) {
    (
        json!({"schema":"mt2spacetime.static-npcs","version":1,"actors":[{"id":"actor.npc.guard","name":"Guard"}],"maps":[{"id":"metin2_map_a1","content_hash":"map-hash","placements":[{"id":"spawn.guard","actor_id":"actor.npc.guard","position":[1,2,3]}]}]}),
        json!({"schema_version":1,"map_id":"metin2_map_a1","interactions":[{"spawn_id":"spawn.guard","kind":"dialogue","body":"Hello"}]}),
    )
}
fn generate(c: &Value, a: &Value) -> Result<String, String> {
    build_npcs::generate(&serde_json::to_vec(c).unwrap(), a, "map-hash")
}
#[test]
fn links_another_npc_without_gameplay_code() {
    let (mut catalog, mut actions) = fixtures();
    catalog["maps"][0]["placements"]
        .as_array_mut()
        .unwrap()
        .push(json!({"id":"spawn.second","actor_id":"actor.npc.guard","position":[4,2,3]}));
    actions["interactions"]
        .as_array_mut()
        .unwrap()
        .push(json!({"spawn_id":"spawn.second","kind":"dialogue","body":"Different text"}));
    let output = generate(&catalog, &actions).unwrap();
    assert!(output.contains("Different text"));
    assert!(output.contains("NPC_CATALOG_HASH"));
}
#[test]
fn rejects_unknown_handlers_stale_maps_duplicate_and_missing_links() {
    let (catalog, actions) = fixtures();
    for pointer in [
        "/interactions/0/kind",
        "/interactions/0/spawn_id",
        "/map_id",
    ] {
        let mut invalid = actions.clone();
        *invalid.pointer_mut(pointer).unwrap() = json!("unknown");
        assert!(generate(&catalog, &invalid).is_err(), "{pointer}");
    }
    let mut invalid = actions.clone();
    invalid["interactions"]
        .as_array_mut()
        .unwrap()
        .push(actions["interactions"][0].clone());
    assert!(generate(&catalog, &invalid).is_err());
    invalid = actions.clone();
    invalid["interactions"][0]["reward"] = json!(100);
    assert!(generate(&catalog, &invalid).is_err());
    let mut stale = catalog.clone();
    stale["maps"][0]["content_hash"] = json!("old-map");
    assert!(generate(&stale, &actions).is_err());
    stale = catalog.clone();
    stale["maps"][0]["placements"][0]["position"][0] = json!("NaN");
    assert!(generate(&stale, &actions).is_err());
}
