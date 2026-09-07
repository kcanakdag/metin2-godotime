#[path = "../build_population.rs"]
mod build_population;
use serde_json::{Value, json};

fn profile() -> Value {
    serde_json::from_str(include_str!(
        "../../content/worlds/training.population.json"
    ))
    .unwrap()
}

#[test]
fn same_handler_accepts_multiple_homes_and_stable_nonsequential_ids() {
    let mut data = profile();
    data["placements"]
        .as_array_mut()
        .unwrap()
        .push(json!({"id": 83, "definition_vnum":101, "home_x": -4.0, "home_z": 12.0}));
    let parsed = build_population::parse(&data, "training", 101).unwrap();
    assert_eq!(parsed.len(), 2);
    assert_eq!(parsed[1].id, 83);
    assert_eq!((parsed[1].home_x, parsed[1].home_z), (-4.0, 12.0));
}

#[test]
fn rejects_unknown_fields_definitions_ids_and_ambiguous_coordinates() {
    for (key, bad) in [
        ("id", json!(true)),
        ("id", json!(0)),
        ("id", json!(1.0)),
        ("definition_vnum", json!(102)),
        ("home_x", json!("NaN")),
        ("home_x", json!(true)),
        ("home_z", json!(1e20)),
        ("script", json!("run")),
    ] {
        let mut data = profile();
        data["placements"][0][key] = bad;
        assert!(
            build_population::parse(&data, "training", 101).is_err(),
            "{key}"
        );
    }
    let mut data = profile();
    let mut duplicate = data["placements"][0].clone();
    data["placements"]
        .as_array_mut()
        .unwrap()
        .push(duplicate.clone());
    assert!(build_population::parse(&data, "training", 101).is_err());
    duplicate["id"] = json!(2);
    data["placements"][1] = duplicate;
    assert!(build_population::parse(&data, "training", 101).is_err());
    assert!(build_population::parse(&profile(), "another-map", 101).is_err());
}
