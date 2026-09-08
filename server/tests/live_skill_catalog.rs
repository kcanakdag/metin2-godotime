#[path = "../build_skills.rs"]
mod compiler;

#[test]
fn installed_catalog_compiles_without_changing_its_event_contract() {
    let bytes = include_bytes!("../../client/assets/imported/skills/catalog.v1.json");
    assert_eq!(compiler::generate(bytes).unwrap(), compiler::build());
}

#[test]
fn live_repeat_limits_are_bounded_and_emitted() {
    let mut catalog: serde_json::Value = serde_json::from_slice(include_bytes!(
        "../../client/assets/imported/skills/catalog.v1.json"
    ))
    .unwrap();
    catalog["skills"][0]["hits_per_life"] = serde_json::json!(3);
    assert!(
        compiler::generate(&catalog.to_string().into_bytes())
            .unwrap()
            .contains("hits_per_life:3")
    );
    for value in [
        serde_json::json!(0),
        serde_json::json!(33),
        serde_json::json!(true),
        serde_json::json!(-1),
        serde_json::Value::Null,
    ] {
        catalog["skills"][0]["hits_per_life"] = value;
        assert!(compiler::generate(&catalog.to_string().into_bytes()).is_err());
    }
}
