#[path = "../build_items.rs"]
mod build_items;
use serde_json::{Value, json};

fn catalog() -> Value {
    let root: Value =
        serde_json::from_str(include_str!("../content/p0-warrior-dog/actions.v1.json")).unwrap();
    root["item_catalog"].clone()
}

#[test]
fn generated_registry_accepts_another_recovery_definition_without_a_new_handler() {
    let mut data = catalog();
    let mut extra = data["items"][2].clone();
    extra["vnum"] = json!(27003);
    extra["id"] = json!("item.consumable.red-potion-large");
    extra["recovery"]["hp"] = json!(1200);
    data["items"].as_array_mut().unwrap().push(extra);
    let generated = build_items::generate(&data).unwrap();
    assert!(generated.contains("hp: 1200"));
    assert!(generated.contains("vnum: 27003"));
}

#[test]
fn build_boundary_rejects_invalid_ranges_unknown_handlers_and_collisions() {
    for (field, bad) in [
        ("height", json!(10)),
        ("height", json!(0)),
        ("stack_limit", json!(201)),
        ("vnum", json!(true)),
        ("revision", json!(1.0)),
        ("allowed_classes", json!(0)),
        ("allowed_sexes", json!(4)),
        ("kind", json!("script")),
    ] {
        let mut data = catalog();
        data["items"][1][field] = bad;
        assert!(build_items::generate(&data).is_err(), "{field}");
    }
    let mut data = catalog();
    data["items"][2]["recovery"]["hp"] = json!(65536);
    assert!(build_items::generate(&data).is_err());
    let mut data = catalog();
    data["items"][2]["recovery"]["handler"] = json!("execute");
    assert!(build_items::generate(&data).is_err());
    let mut data = catalog();
    data["items"][1]["vnum"] = data["items"][0]["vnum"].clone();
    assert!(build_items::generate(&data).is_err());
    let mut data = catalog();
    data["items"][1]["source"]["sha256"] = json!("invalid");
    assert!(build_items::generate(&data).is_err());
}

#[test]
fn item_links_cannot_disagree_with_combat_or_reward_contracts() {
    let original: Value =
        serde_json::from_str(include_str!("../content/p0-warrior-dog/actions.v1.json")).unwrap();
    assert!(build_items::validate_links(&original).is_ok());
    let mut changed = original.clone();
    changed["item_catalog"]["items"][0]["weapon"]["power_max"] = json!(20);
    assert!(build_items::validate_links(&changed).is_err());
    let mut changed = original;
    changed["item_catalog"]["items"][2]["stack_limit"] = json!(10);
    assert!(build_items::validate_links(&changed).is_err());
}

#[test]
fn recovery_fixture_requires_explicit_isolated_default_deny_configuration() {
    let check = build_items::recovery_fixture_enabled;
    let issuer = "http://127.0.0.1:8186/auth";
    assert!(!check("", "https://game.example/auth", true, "", false, "").unwrap());
    assert!(check("recovery", issuer, false, "", false, "").unwrap());
    for bad in [
        "https://game.example/auth",
        "http://127.0.0.1:0/auth",
        "http://127.0.0.1:8186@evil/auth",
        "http://127.0.0.1:8186/auth/extra",
        "http://127.0.0.1:+8186/auth",
    ] {
        assert!(check("recovery", bad, false, "", false, "").is_err());
    }
    assert!(check("other", issuer, false, "", false, "").is_err());
    assert!(check("recovery", issuer, true, "", false, "").is_err());
    assert!(check("recovery", issuer, false, "finisher", false, "").is_err());
    assert!(check("recovery", issuer, false, "", true, "").is_err());
    assert!(check("recovery", issuer, false, "", false, "privileged").is_err());
}
