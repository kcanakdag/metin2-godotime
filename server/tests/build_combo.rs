#[path = "../build_combo.rs"]
mod build_combo;

use build_combo::{PLAYER_COMBO_ACTION_IDS, validate};
use serde_json::{Map, Value, json};

fn fixture() -> Value {
    serde_json::from_slice(include_bytes!("../content/p0-warrior-dog/actions.v1.json"))
        .expect("tracked trusted definitions must be JSON")
}

fn root(value: &Value) -> &Map<String, Value> {
    value.as_object().expect("fixture root")
}

fn combo_mut(value: &mut Value, index: usize) -> &mut Map<String, Value> {
    value["actions"]
        .as_array_mut()
        .expect("actions")
        .iter_mut()
        .find(|row| row["id"] == PLAYER_COMBO_ACTION_IDS[index])
        .expect("combo action")
        .as_object_mut()
        .expect("combo row")
}

#[test]
fn accepts_the_generated_two_action_prefix() {
    let value = fixture();
    let combo = validate(root(&value)).expect("generated combo contract");
    assert_eq!(combo[0].pre_input_us, 167_094);
    assert_eq!(combo[0].direct_input_us, 533_333);
    assert_eq!(combo[0].input_limit_us, 602_564);
    assert_eq!(combo[0].link_us, 58_889);
    assert_eq!(combo[1].pre_input_us, 100_513);
    assert_eq!(combo[1].direct_input_us, 543_248);
    assert_eq!(combo[1].input_limit_us, 636_581);
    assert_eq!(combo[1].link_us, 19_658);
}

#[test]
fn rejects_missing_duplicate_and_reordered_prefix_records() {
    let mut missing = fixture();
    missing["base_combo_prefix"] = Value::Null;
    assert!(
        validate(root(&missing))
            .unwrap_err()
            .contains("must be an array")
    );

    let mut missing_action = fixture();
    missing_action["actions"]
        .as_array_mut()
        .expect("actions")
        .retain(|row| row["id"] != PLAYER_COMBO_ACTION_IDS[1]);
    assert!(
        validate(root(&missing_action))
            .unwrap_err()
            .contains("exactly the four")
    );

    let mut duplicate = fixture();
    let duplicate_row = duplicate["actions"][0].clone();
    duplicate["actions"][1] = duplicate_row;
    assert!(validate(root(&duplicate)).unwrap_err().contains("unique"));

    let mut reordered = fixture();
    reordered["base_combo_prefix"] =
        json!([PLAYER_COMBO_ACTION_IDS[1], PLAYER_COMBO_ACTION_IDS[0]]);
    assert!(
        validate(root(&reordered))
            .unwrap_err()
            .contains("combo_1 then combo_2")
    );

    let mut duplicate_prefix = fixture();
    duplicate_prefix["base_combo_prefix"] =
        json!([PLAYER_COMBO_ACTION_IDS[0], PLAYER_COMBO_ACTION_IDS[0]]);
    assert!(
        validate(root(&duplicate_prefix))
            .unwrap_err()
            .contains("combo_1 then combo_2")
    );
}

#[test]
fn rejects_malformed_combo_timing_at_the_build_boundary() {
    let cases: [(&str, Value); 10] = [
        ("missing", Value::Null),
        (
            "extra",
            json!({
                "pre_input_us": 1,
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 4,
                "extra": 5
            }),
        ),
        (
            "boolean",
            json!({
                "pre_input_us": false,
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 4
            }),
        ),
        (
            "float",
            json!({
                "pre_input_us": 1.5,
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 4
            }),
        ),
        (
            "string",
            json!({
                "pre_input_us": "1",
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 4
            }),
        ),
        (
            "negative",
            json!({
                "pre_input_us": -1,
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 4
            }),
        ),
        (
            "equal",
            json!({
                "pre_input_us": 2,
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 4
            }),
        ),
        (
            "inverted",
            json!({
                "pre_input_us": 3,
                "direct_input_us": 2,
                "input_limit_us": 4,
                "link_us": 5
            }),
        ),
        (
            "overbound",
            json!({
                "pre_input_us": 1,
                "direct_input_us": 2,
                "input_limit_us": 3,
                "link_us": 60_000_001
            }),
        ),
        (
            "limit after duration",
            json!({
                "pre_input_us": 1,
                "direct_input_us": 2,
                "input_limit_us": 2_000_000,
                "link_us": 4
            }),
        ),
    ];
    for (name, timing) in cases {
        let mut value = fixture();
        if name == "missing" {
            combo_mut(&mut value, 0).remove("combo_input");
        } else {
            combo_mut(&mut value, 0).insert("combo_input".to_owned(), timing);
        }
        assert!(validate(root(&value)).is_err(), "{name} timing passed");
    }
}

#[test]
fn rejects_wrong_action_semantics_primary_and_nonprefix_combo_data() {
    let mut mode = fixture();
    combo_mut(&mut mode, 0).insert("mode".to_owned(), json!("general"));
    assert!(
        validate(root(&mode))
            .unwrap_err()
            .contains("actor/mode/action")
    );

    let mut item = fixture();
    combo_mut(&mut item, 0).insert("required_item_vnums".to_owned(), json!([]));
    assert!(validate(root(&item)).unwrap_err().contains("equipment"));

    let mut primary = fixture();
    primary["actors"][0]["primary_actions"]["onehand"] = json!(PLAYER_COMBO_ACTION_IDS[1]);
    assert!(
        validate(root(&primary))
            .unwrap_err()
            .contains("prefix head")
    );

    let mut nonprefix = fixture();
    nonprefix["actions"][0]["combo_input"] = json!({
        "pre_input_us": 1,
        "direct_input_us": 2,
        "input_limit_us": 3,
        "link_us": 4
    });
    assert!(
        validate(root(&nonprefix))
            .unwrap_err()
            .contains("must omit")
    );
}
