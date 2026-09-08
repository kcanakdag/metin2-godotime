#[path = "../build_regeneration.rs"]
mod build_regeneration;
use build_regeneration::parse;
use serde_json::json;

#[test]
fn selected_fixture_and_disabled_settings_are_explicit() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../fixtures/p2-regenerating-wild-dog.v1.json")).unwrap();
    let selected = parse(&fixture["regeneration"]).unwrap();
    assert_eq!(
        (
            selected.id,
            selected.interval_us,
            selected.capacity,
            selected.startup_jitter_seconds
        ),
        (1, 5000000, 1, 0)
    );
    let disabled =
        parse(&json!({"id":2,"interval_us":0,"capacity":0,"startup_jitter_seconds":16})).unwrap();
    assert_eq!((disabled.interval_us, disabled.capacity), (0, 0));
}

#[test]
fn malformed_numeric_values_and_unknown_or_missing_fields_reject() {
    let base = json!({"id":1,"interval_us":5000000,"capacity":1,"startup_jitter_seconds":0});
    for (key, value) in [
        ("id", json!(0)),
        ("id", json!(4294967296_u64)),
        ("interval_us", json!(86400000001_u64)),
        ("interval_us", json!(-1)),
        ("interval_us", json!(0.5)),
        ("capacity", json!(1001)),
        ("capacity", json!("1")),
        ("startup_jitter_seconds", json!(17)),
    ] {
        let mut input = base.clone();
        input[key] = value;
        assert!(parse(&input).is_err(), "{key}");
    }
    let mut input = base.clone();
    input["jitter"] = json!(0);
    assert!(parse(&input).is_err());
    input = base;
    input.as_object_mut().unwrap().remove("capacity");
    assert!(parse(&input).is_err());
}
