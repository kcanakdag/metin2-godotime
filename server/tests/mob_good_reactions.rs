#[path = "../build_mob_reactions.rs"]
mod compiler;

#[test]
fn installed_and_fixture_reactions_compile() {
    for bytes in [
        include_bytes!("../../client/assets/imported/mobs/presentation.v1.json").as_slice(),
        include_bytes!("../../client/assets/imported/content/p0-warrior-dog/manifest.v1.json")
            .as_slice(),
    ] {
        let root = serde_json::from_slice(bytes).unwrap();
        let output = compiler::generate(&root).unwrap();
        assert!(output.contains("GOOD_REACTIONS"));
        assert!(output.contains("front_damage"));
        assert!(output.contains("back_damage"));
    }
}

#[test]
fn malformed_reactions_reject_and_missing_back_uses_empty_list() {
    use serde_json::json;
    let motion = json!({"action":"front_damage", "action_id":"actor.mob.test.general.front_damage",
        "duration_us":500000,"weight":100,"loop":false,"events":[]});
    let root = json!({"actors":[{"kind":"mob","vnum":101,"id":"actor.mob.test",
        "modes":[{"id":"general","motions":[motion]}]}]});
    assert!(compiler::generate(&root).unwrap().contains(",&[])"));
    for (key, value) in [
        ("duration_us", json!(0)),
        ("weight", json!(99)),
        ("action_id", json!("actor.mob.foreign.general.front_damage")),
        ("loop", json!(true)),
        ("events", json!([{}])),
    ] {
        let mut bad = root.clone();
        bad["actors"][0]["modes"][0]["motions"][0][key] = value;
        assert!(compiler::generate(&bad).is_err());
    }
    let mut duplicate = root.clone();
    duplicate["actors"]
        .as_array_mut()
        .unwrap()
        .push(root["actors"][0].clone());
    assert!(compiler::generate(&duplicate).is_err());
}
