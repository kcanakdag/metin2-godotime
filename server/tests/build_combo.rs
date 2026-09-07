#[path = "../build_combo.rs"]
mod build_combo;

use build_combo::{PLAYER_COMBO_ACTION_IDS, validate};
use serde_json::{Map, Value, json};

type Mutation = Box<dyn Fn(&mut Value)>;

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
fn accepts_the_generated_three_action_prefix_and_root_endpoints() {
    let value = fixture();
    let combo = validate(root(&value)).expect("generated combo contract");
    assert_eq!(combo[0].combo_input.pre_input_us, 167_094);
    assert_eq!(combo[0].combo_input.direct_input_us, 533_333);
    assert_eq!(combo[0].combo_input.input_limit_us, 602_564);
    assert_eq!(combo[0].combo_input.link_us, 58_889);
    assert_eq!(combo[1].combo_input.pre_input_us, 100_513);
    assert_eq!(combo[1].combo_input.direct_input_us, 543_248);
    assert_eq!(combo[1].combo_input.input_limit_us, 636_581);
    assert_eq!(combo[1].combo_input.link_us, 19_658);
    assert_eq!(combo[2].combo_input.pre_input_us, 84_786);
    assert_eq!(combo[2].combo_input.direct_input_us, 418_462);
    assert_eq!(combo[2].combo_input.input_limit_us, 664_615);
    assert_eq!(combo[2].combo_input.link_us, 60_171);
    assert_eq!(combo[0].root_motion.endpoint_x_m, 0.0);
    assert_eq!(combo[0].root_motion.endpoint_z_m, -1.317569580078125);
    assert_eq!(combo[0].root_motion.duration_us, 1_000_000);
    assert_eq!(combo[1].root_motion.endpoint_z_m, -0.852515640258789);
    assert_eq!(combo[1].root_motion.duration_us, 933_333);
    assert_eq!(combo[2].root_motion.endpoint_z_m, -1.4301394653320312);
    assert_eq!(combo[2].root_motion.duration_us, 1_066_667);
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
            .contains("exactly the five")
    );

    let mut duplicate = fixture();
    let duplicate_row = duplicate["actions"][0].clone();
    duplicate["actions"][1] = duplicate_row;
    assert!(validate(root(&duplicate)).unwrap_err().contains("unique"));

    let mut reordered = fixture();
    reordered["base_combo_prefix"] = json!([
        PLAYER_COMBO_ACTION_IDS[1],
        PLAYER_COMBO_ACTION_IDS[0],
        PLAYER_COMBO_ACTION_IDS[2]
    ]);
    assert!(
        validate(root(&reordered))
            .unwrap_err()
            .contains("combo_1 then combo_2 then combo_3")
    );

    let mut duplicate_prefix = fixture();
    duplicate_prefix["base_combo_prefix"] = json!([
        PLAYER_COMBO_ACTION_IDS[0],
        PLAYER_COMBO_ACTION_IDS[0],
        PLAYER_COMBO_ACTION_IDS[2]
    ]);
    assert!(
        validate(root(&duplicate_prefix))
            .unwrap_err()
            .contains("combo_1 then combo_2 then combo_3")
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
fn rejects_malformed_root_motion_policy_sources_and_runtime_fields() {
    let cases: Vec<(&str, Mutation)> = vec![
        (
            "policy",
            Box::new(|value| value["root_motion_policy"]["id"] = json!("linear")),
        ),
        (
            "reordered sources",
            Box::new(|value| {
                value["root_motion_sources"]
                    .as_array_mut()
                    .expect("sources")
                    .reverse()
            }),
        ),
        (
            "duplicate source",
            Box::new(|value| {
                value["root_motion_sources"][1] = value["root_motion_sources"][0].clone()
            }),
        ),
        (
            "missing root",
            Box::new(|value| {
                combo_mut(value, 0).remove("root_motion");
            }),
        ),
        (
            "extra root field",
            Box::new(|value| value["actions"][2]["root_motion"]["extra"] = json!(1)),
        ),
        (
            "boolean endpoint",
            Box::new(|value| value["actions"][2]["root_motion"]["endpoint_x_m"] = json!(false)),
        ),
        (
            "endpoint bound",
            Box::new(|value| value["actions"][2]["root_motion"]["endpoint_z_m"] = json!(-2.01)),
        ),
        (
            "duration bound",
            Box::new(|value| value["actions"][2]["root_motion"]["duration_us"] = json!(1_600_001)),
        ),
        (
            "wrong raw duration",
            Box::new(|value| {
                value["root_motion_sources"][0]["animation_duration_s_raw_decimal"] = json!("0.9")
            }),
        ),
        (
            "nonfinite raw duration",
            Box::new(|value| {
                value["root_motion_sources"][0]["animation_duration_s_raw_decimal"] = json!("NaN")
            }),
        ),
        (
            "boolean count",
            Box::new(|value| value["root_motion_sources"][0]["animation_count"] = json!(true)),
        ),
        (
            "wrong flag",
            Box::new(|value| value["root_motion_sources"][0]["accumulation_flags"] = json!(1)),
        ),
        (
            "periodic loop",
            Box::new(|value| value["root_motion_sources"][0]["periodic_loop"] = json!({})),
        ),
        (
            "wrong pin",
            Box::new(|value| {
                value["root_motion_sources"][0]["source_gr2"]["sha256"] = json!("0".repeat(64))
            }),
        ),
        (
            "vertical endpoint",
            Box::new(|value| {
                value["root_motion_sources"][0]["loop_translation_source_cm_decimal"] =
                    json!(["0", "-131.7569580078125", "1"])
            }),
        ),
        (
            "MSA mismatch",
            Box::new(|value| {
                value["root_motion_sources"][0]["msa_accumulation_output_actor_local_godot_m_decimal"] =
                    json!(["0", "0", "-1"])
            }),
        ),
    ];
    for (name, mutate) in cases {
        let mut value = fixture();
        mutate(&mut value);
        assert!(
            validate(root(&value)).is_err(),
            "{name} root metadata passed"
        );
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

    let mut nonprefix_root = fixture();
    nonprefix_root["actions"][0]["root_motion"] = json!({
        "endpoint_x_m": 0.0,
        "endpoint_z_m": 0.0,
        "duration_us": 933333
    });
    assert!(
        validate(root(&nonprefix_root))
            .unwrap_err()
            .contains("must omit")
    );
}
