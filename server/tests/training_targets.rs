#[path = "../build_training.rs"]
mod build_training;

#[test]
fn build_authored_training_definition() {
    assert!(build_training::build().contains("TrainingTargetDefinition"));
}

#[test]
fn rejects_malformed_authoring_data_before_embedding() {
    use serde_json::{Value, json};
    let profile: Value =
        serde_json::from_str(include_str!("../../content/profiles/training-dummy.json")).unwrap();
    for (key, value) in [
        ("height_m", json!(0.1)),
        ("body_radius_m", json!(8)),
        ("id", json!("actor.training.")),
        ("health", json!(true)),
        ("heatlh", json!(600)),
        (
            "colors",
            json!({"wood": [0,0,0,1], "straw": [0,0,0,1], "rope": [0,0,0,1], "target": [2,0,0,1]}),
        ),
    ] {
        let mut bad = profile.clone();
        bad[key] = value;
        assert!(build_training::generate(&bad, "training").is_err(), "{key}");
    }
    let mut bad = profile.clone();
    bad["placements"][0]["typo"] = json!(1);
    assert!(build_training::generate(&bad, "training").is_err());
    let mut custom = profile;
    custom["health"] = json!(600);
    custom["height_m"] = json!(2.2);
    custom["sword_resistance_percent"] = json!(50);
    assert!(build_training::generate(&custom, "training").is_ok());
}
