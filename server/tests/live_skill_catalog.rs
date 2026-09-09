#[path = "../build_skills.rs"]
mod compiler;

fn charge_candidate() -> serde_json::Value {
    use serde_json::{Value, json};
    let mut catalog: Value = serde_json::from_slice(include_bytes!(
        "../../client/assets/imported/skills/catalog.v1.json"
    ))
    .unwrap();
    catalog["skills"].as_array_mut().unwrap().truncate(1);
    let row = &mut catalog["skills"][0];
    row["vnum"] = json!(5);
    row["handler"] = json!("physical_charge_v1");
    row["weapon_class"] = json!("sword_or_two_handed");
    row["requires_target"] = json!(true);
    row["target_range_m"] = json!(1.7);
    row["hits_per_life"] = json!(1);
    row["charge"] = json!({"duration_us":3_000_000,"speed_bonus":150,
                          "push_distance_m":2.0,"main_target_stun_us":4_000_000});
    for variant in row["variants"].as_array_mut().unwrap() {
        variant["action_id"] = json!(format!(
            "{}.general.skill_5",
            variant["actor_id"].as_str().unwrap()
        ));
        for field in [
            "hit_start_us",
            "hit_end_us",
            "hit_windows_us",
            "hit_geometry",
        ] {
            variant.as_object_mut().unwrap().remove(field);
        }
        variant["source_hit_events"] = json!([]);
    }
    catalog
}

#[test]
fn charge_compiles_policy_and_animation_without_damage_windows() {
    let generated = compiler::generate(charge_candidate().to_string().as_bytes()).unwrap();
    assert!(generated.contains(
        "duration_us:3000000,speed_bonus:150,push_distance_m:2.0,main_target_stun_us:4000000"
    ));
    assert!(generated.contains("hit_start_us:0,hit_end_us:0"));
    assert!(generated.contains("(5,\"actor.player.warrior-male\",&[])"));
    assert!(generated.contains("(5,\"actor.player.warrior-female\",&[])"));
}

#[test]
fn charge_rejects_unsafe_policy_or_an_animation_damage_schedule() {
    use serde_json::json;
    let candidate = charge_candidate();
    for (field, value) in [
        ("duration_us", json!(0)),
        ("duration_us", json!(600_000_001)),
        ("speed_bonus", json!(-1)),
        ("speed_bonus", json!(1001)),
        ("push_distance_m", json!(-1)),
        ("push_distance_m", json!(21)),
        ("main_target_stun_us", json!(-1)),
        ("main_target_stun_us", json!(600_000_001)),
    ] {
        let mut bad = candidate.clone();
        bad["skills"][0]["charge"][field] = value;
        assert!(
            compiler::generate(bad.to_string().as_bytes()).is_err(),
            "{field}"
        );
    }
    for (field, value) in [
        ("requires_target", json!(false)),
        ("target_range_m", json!(0)),
        ("hits_per_life", json!(2)),
        ("weapon_class", json!("sword")),
    ] {
        let mut bad = candidate.clone();
        bad["skills"][0][field] = value;
        assert!(
            compiler::generate(bad.to_string().as_bytes()).is_err(),
            "{field}"
        );
    }
    for field in [
        "hit_start_us",
        "hit_end_us",
        "hit_windows_us",
        "hit_geometry",
    ] {
        let mut bad = candidate.clone();
        bad["skills"][0]["variants"][0][field] = json!(0);
        assert!(
            compiler::generate(bad.to_string().as_bytes()).is_err(),
            "{field}"
        );
    }
}

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

#[test]
fn fixed_areas_require_one_valid_shape_per_event() {
    use serde_json::{Value, json};
    let mut catalog: Value = serde_json::from_slice(include_bytes!(
        "../../client/assets/imported/skills/catalog.v1.json"
    ))
    .unwrap();
    // This malformed-input fixture starts from the explicit single-window skill,
    // independent of installed catalog ordering or additional playable skills.
    catalog["skills"]
        .as_array_mut()
        .unwrap()
        .retain(|row| row["vnum"] == 2);
    catalog["skills"][0]["handler"] = json!("physical_area_v1");
    let area = json!({"kind":"attack_area", "coordinate_space":"output_actor_local_godot",
        "hitting_type":2,"invisible_us":100000,"stiffen_us":0,"external_force":0,
        "attack_type":0,"collision_type":4,
        "spheres":[{"position_m":[0,1,-2],"radius_m":1.2}]});
    for variant in catalog["skills"][0]["variants"].as_array_mut().unwrap() {
        variant["hit_geometry"] = json!([area.clone()]);
    }
    let generated = compiler::generate(catalog.to_string().as_bytes()).unwrap();
    assert!(generated.contains("position_m:[0.0, 1.0, -2.0],radius_m:1.2"));
    for invalid in [
        json!([]),
        json!([area.clone(), area.clone()]),
        json!([{"kind":"attack_window","coordinate_space":"output_actor_local_godot",
            "bone":"", "weapon_length_m":0}]),
    ] {
        let mut bad = catalog.clone();
        bad["skills"][0]["variants"][0]["hit_geometry"] = invalid;
        assert!(compiler::generate(bad.to_string().as_bytes()).is_err());
    }
    for (field, value) in [
        ("hitting_type", json!(0)),
        ("hitting_type", json!(3)),
        ("invisible_us", json!(-1)),
        ("invisible_us", json!(10_000_001)),
        ("stiffen_us", json!(1)),
        ("external_force", json!(-1)),
        ("external_force", json!(21)),
        ("external_force", json!(5)),
        ("attack_type", json!(1)),
        ("collision_type", json!(0)),
    ] {
        let mut bad = catalog.clone();
        bad["skills"][0]["variants"][0]["hit_geometry"][0][field] = value;
        assert!(
            compiler::generate(bad.to_string().as_bytes()).is_err(),
            "{field}"
        );
    }
    let mut great = catalog.clone();
    for variant in great["skills"][0]["variants"].as_array_mut().unwrap() {
        variant["hit_geometry"][0]["hitting_type"] = json!(1);
        variant["hit_geometry"][0]["external_force"] = json!(5);
        variant["hit_geometry"][0]["invisible_us"] = json!(500000);
    }
    assert!(
        compiler::generate(great.to_string().as_bytes())
            .unwrap()
            .contains("hit_type:1,invulnerability_us:500000,external_force:5.0")
    );
    catalog["skills"][0]["handler"] = json!("physical_splash_v1");
    assert!(compiler::generate(catalog.to_string().as_bytes()).is_err());
}

#[test]
fn target_policy_is_typed_and_bounded() {
    use serde_json::{Value, json};
    let mut catalog: Value = serde_json::from_slice(include_bytes!(
        "../../client/assets/imported/skills/catalog.v1.json"
    ))
    .unwrap();
    catalog["skills"][0]["requires_target"] = json!(true);
    catalog["skills"][0]["target_range_m"] = json!(0);
    assert!(
        compiler::generate(catalog.to_string().as_bytes())
            .unwrap()
            .contains("requires_target:true,target_range_m:0.0")
    );
    for (key, value) in [
        ("requires_target", json!(1)),
        ("target_range_m", json!(-1)),
        ("target_range_m", json!(101)),
    ] {
        let mut bad = catalog.clone();
        bad["skills"][0][key] = value;
        assert!(compiler::generate(bad.to_string().as_bytes()).is_err());
    }
    catalog["skills"][0]["requires_target"] = json!(false);
    catalog["skills"][0]["target_range_m"] = json!(2);
    assert!(compiler::generate(catalog.to_string().as_bytes()).is_err());
}
