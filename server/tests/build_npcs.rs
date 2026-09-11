#[allow(dead_code)]
#[path = "../build_npcs.rs"]
mod build_npcs;
use serde_json::{Value, json};
fn fixtures() -> (Value, Value) {
    (
        json!({"schema":"mt2spacetime.static-npcs","version":1,"actors":[{"id":"actor.npc.guard","name":"Guard","vnum":9001}],"maps":[{"id":"metin2_map_a1","content_hash":"map-hash","placements":[{"id":"spawn.guard","actor_id":"actor.npc.guard","position":[1,2,3]}]}]}),
        json!({"schema_version":1,"map_id":"metin2_map_a1","interactions":[{"spawn_id":"spawn.guard","kind":"dialogue","body":"Hello"}]}),
    )
}
fn generate(c: &Value, a: &Value) -> Result<String, String> {
    build_npcs::generate(&serde_json::to_vec(c).unwrap(), a, "map-hash")
}
/// Schema-3 catalog with one wandering placement and the dialogue row that
/// keeps it clickable.
fn area_fixtures() -> (Value, Value) {
    let (mut catalog, mut actions) = fixtures();
    catalog["version"] = json!(3);
    catalog["maps"][0]["areas"] = json!([{
        "id":"spawn.area", "actor_id":"actor.npc.guard",
        "bounds_cm":[100,200,300,400], "respawn_interval_us":60000000
    }]);
    actions["interactions"].as_array_mut().unwrap().push(
        json!({"spawn_id":"spawn.area","kind":"dialogue","body":"You again?","title":"Wanderer:"}),
    );
    (catalog, actions)
}
#[test]
fn compiles_original_area_bounds_without_fabricating_a_point() {
    let (catalog, actions) = area_fixtures();
    let output = generate(&catalog, &actions).unwrap();
    assert!(output.contains("bounds_cm: [100, 200, 300, 400]"));
    assert!(output.contains("respawn_interval_us: 60000000"));
    // The wandering placement resolves to dialogue only; it must not fabricate
    // a static point from the rectangle.
    assert!(output.contains("pub const NPC_AREA_DIALOGUES: &[NpcAreaDialogue] = &["));
    assert!(output.contains(
        r#"NpcAreaDialogue { id: "spawn.area", vnum: 9001, name: "Guard", title: "Wanderer:", body: "You again?" },"#
    ));
    // Only the authored placement becomes an immutable static definition.
    assert_eq!(output.matches("NpcDefinition { id:").count(), 1);
    for (key, value) in [
        ("id", json!("spawn.guard")),
        ("actor_id", json!("unknown")),
        ("bounds_cm", json!([100, 200, 100, 200])),
        ("bounds_cm", json!([300, 200, 100, 400])),
        ("bounds_cm", json!([true, 200, 300, 400])),
        ("bounds_cm", json!([0, 0, 2147483648_u64, 400])),
        ("respawn_interval_us", json!(0)),
        ("respawn_interval_us", json!(1000000.5)),
    ] {
        let mut bad = catalog.clone();
        bad["maps"][0]["areas"][0][key] = value;
        assert!(generate(&bad, &actions).is_err(), "{key}");
    }
}
#[test]
fn rejects_area_rows_without_dialogue_and_orphan_area_dialogue() {
    let (catalog, actions) = area_fixtures();
    let mut missing = actions.clone();
    missing["interactions"].as_array_mut().unwrap().pop();
    assert_eq!(
        generate(&catalog, &missing).unwrap_err(),
        "Area NPC spawn.area has no dialogue row"
    );
    let mut orphan = actions.clone();
    orphan["interactions"]
        .as_array_mut()
        .unwrap()
        .push(json!({"spawn_id":"spawn.ghost","kind":"dialogue","body":"Nowhere"}));
    assert_eq!(
        generate(&catalog, &orphan).unwrap_err(),
        "Interaction must resolve exactly one NPC placement or area"
    );
    let mut duplicate = actions.clone();
    duplicate["interactions"]
        .as_array_mut()
        .unwrap()
        .push(actions["interactions"][1].clone());
    assert_eq!(
        generate(&catalog, &duplicate).unwrap_err(),
        "Invalid or duplicate NPC interaction"
    );
}
#[test]
fn area_dialogue_shares_the_placement_field_budget() {
    let (catalog, actions) = area_fixtures();
    let mut long_body = actions.clone();
    long_body["interactions"][1]["body"] = json!("b".repeat(1025));
    assert!(generate(&catalog, &long_body).is_err());
    let mut long_title = actions.clone();
    long_title["interactions"][1]["title"] = json!("t".repeat(161));
    assert!(generate(&catalog, &long_title).is_err());
    // A schema-1/2 catalog has no areas, so its output declares an empty list.
    let (plain, plain_actions) = fixtures();
    let output = generate(&plain, &plain_actions).unwrap();
    assert!(output.contains("pub const NPC_AREAS: &[NpcAreaDefinition] = &[\n];"));
    assert!(output.contains("pub const NPC_AREA_DIALOGUES: &[NpcAreaDialogue] = &[\n];"));
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
fn carries_the_authored_board_title_and_defaults_it_to_the_actor_name() {
    let (catalog, actions) = fixtures();
    let plain = generate(&catalog, &actions).unwrap();
    assert!(plain.contains(r#"title: """#));
    let mut titled = actions.clone();
    titled["interactions"][0]["title"] = json!("Guard:");
    let output = generate(&catalog, &titled).unwrap();
    assert!(output.contains(r#"title: "Guard:""#));
    assert!(output.contains("pub title: &'static str"));
    let longest = "t".repeat(160);
    titled["interactions"][0]["title"] = json!(longest);
    assert!(generate(&catalog, &titled).unwrap().contains(&longest));
    for bad in ["", "\n", "a\nb", "\u{7}", &"t".repeat(161)] {
        titled["interactions"][0]["title"] = json!(bad);
        assert!(generate(&catalog, &titled).is_err(), "{bad:?}");
    }
    titled["interactions"][0]["title"] = json!(7);
    assert!(generate(&catalog, &titled).is_err());
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
    for bad_vnum in [
        json!(0),
        json!(-1),
        json!(4294967296_u64),
        json!("9001"),
        json!(1.5),
    ] {
        let mut invalid = catalog.clone();
        invalid["actors"][0]["vnum"] = bad_vnum.clone();
        assert!(
            generate(&invalid, &actions).is_err(),
            "actor vnum {bad_vnum}"
        );
    }
    let mut invalid = catalog.clone();
    invalid["actors"][0].as_object_mut().unwrap().remove("vnum");
    assert!(generate(&invalid, &actions).is_err());
}
