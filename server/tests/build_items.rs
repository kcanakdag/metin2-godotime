#[path = "../build_items.rs"]
mod build_items;
use serde_json::{Value, json};

fn catalog() -> Value {
    let root: Value =
        serde_json::from_str(include_str!("../content/p0-warrior-dog/actions.v1.json")).unwrap();
    root["item_catalog"].clone()
}

fn index_of(data: &Value, id: &str) -> usize {
    data["items"]
        .as_array()
        .unwrap()
        .iter()
        .position(|item| item["id"] == id)
        .unwrap_or_else(|| panic!("missing item {id}"))
}

#[test]
fn generated_registry_accepts_another_recovery_definition_without_a_new_handler() {
    let mut data = catalog();
    let index = index_of(&data, "item.consumable.red-potion-small");
    let mut extra = data["items"][index].clone();
    extra["vnum"] = json!(27003);
    extra["id"] = json!("item.consumable.red-potion-large");
    extra["recovery"]["hp"] = json!(1200);
    let items = data["items"].as_array_mut().unwrap();
    // The registry requires ascending vnums, so a new definition is inserted in
    // order rather than blindly appended.
    let position = items
        .iter()
        .position(|item| item["vnum"].as_u64().unwrap() > 27003)
        .unwrap_or(items.len());
    items.insert(position, extra);
    let generated = build_items::generate(&data).unwrap();
    assert!(generated.contains("hp: 1200"));
    assert!(generated.contains("vnum: 27003"));
}

#[test]
fn armor_and_narrative_kinds_generate_and_keep_their_declared_mechanic() {
    let data = catalog();
    let generated = build_items::generate(&data).unwrap();
    assert!(generated.contains("ItemKind::Armor { category: \"wrist\", position: \"wrist\" }"));
    assert!(generated.contains("ItemKind::Narrative"));
    assert!(generated.contains("name: \"Wooden Bracelet+0\""));

    let mut changed = data.clone();
    let armor = index_of(&changed, "item.armor.wooden-bracelet");
    changed["items"][armor]["recovery"] = json!({
        "handler": "item.recovery.pool.v1", "hp": 1, "sp": 0
    });
    assert!(build_items::generate(&changed).is_err());

    let mut changed = data.clone();
    let armor = index_of(&changed, "item.armor.wooden-bracelet");
    changed["items"][armor]["armor"]["category"] = json!("");
    assert!(build_items::generate(&changed).is_err());

    let mut changed = data;
    let narrative = index_of(&changed, "item.quest.bash-secret");
    changed["items"][narrative]["weapon"] = changed["items"][0]["weapon"].clone();
    assert!(build_items::generate(&changed).is_err());
}

#[test]
fn build_boundary_rejects_invalid_ranges_unknown_handlers_and_collisions() {
    let weapon = index_of(&catalog(), "item.weapon.fan-7000");
    let recovery = index_of(&catalog(), "item.consumable.red-potion-small");
    assert_ne!(weapon, recovery);
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
        data["items"][weapon][field] = bad;
        assert!(build_items::generate(&data).is_err(), "{field}");
    }
    let mut data = catalog();
    data["items"][recovery]["recovery"]["hp"] = json!(65536);
    assert!(build_items::generate(&data).is_err());
    let mut data = catalog();
    data["items"][recovery]["recovery"]["handler"] = json!("execute");
    assert!(build_items::generate(&data).is_err());
    let mut data = catalog();
    data["items"][weapon]["vnum"] = data["items"][0]["vnum"].clone();
    assert!(build_items::generate(&data).is_err());
    let mut data = catalog();
    data["items"][weapon]["source"]["sha256"] = json!("invalid");
    assert!(build_items::generate(&data).is_err());
}

#[test]
fn item_links_cannot_disagree_with_combat_or_reward_contracts() {
    let original: Value =
        serde_json::from_str(include_str!("../content/p0-warrior-dog/actions.v1.json")).unwrap();
    assert!(build_items::validate_links(&original).is_ok());
    let weapon = index_of(&original["item_catalog"], "item.weapon.sword-10");
    let potion = index_of(
        &original["item_catalog"],
        "item.consumable.red-potion-small",
    );
    let mut changed = original.clone();
    changed["item_catalog"]["items"][weapon]["weapon"]["power_max"] = json!(20);
    assert!(build_items::validate_links(&changed).is_err());
    let mut changed = original;
    changed["item_catalog"]["items"][potion]["stack_limit"] = json!(10);
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
