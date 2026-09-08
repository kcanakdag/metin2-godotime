#[path = "../build_mob_physical.rs"]
mod compiler;
use serde_json::{Value, json};

fn fixture() -> Value {
    json!({"schema_version":1,"compiler_version":"mob-content-v1",
        "actors":[{"id":"actor.mob.wild-boar-108","vnum":108,"kind":"mob"}],
        "mob_catalog":[{"id":"actor.mob.wild-boar-108","vnum":108,"battle_type":"MELEE",
        "stats":{"level":7,"st":14,"ht":10,"dx":7,"def":11,"damage_min":30,"damage_max":37,"damage_multiplier":1.0},
        "combat_modifiers":{"resist_sword":0,"resist_fan":0,"enchant_critical":5,"enchant_poison":0}}]})
}

#[test]
fn preserves_boar_stats_and_critical_enchantment() {
    let result = compiler::generate(&fixture()).unwrap();
    assert!(result.contains("vnum: 108"));
    assert!(result.contains("power_min: 30, power_max: 37"));
    assert!(result.contains("critical_percent: 5"));
    let mut power = fixture();
    power["mob_catalog"][0]["battle_type"] = json!("POWER");
    assert!(compiler::generate(&power).is_ok());
}

#[test]
fn rejects_unlinked_duplicate_invalid_or_unsupported_definitions() {
    for (pointer, value) in [
        ("/mob_catalog/0/stats/level", json!(0)),
        ("/mob_catalog/0/stats/damage_min", json!(38)),
        ("/mob_catalog/0/stats/damage_multiplier", json!("NaN")),
        ("/mob_catalog/0/stats/damage_multiplier", json!(1e-100)),
        (
            "/mob_catalog/0/combat_modifiers/enchant_critical",
            json!(101),
        ),
        ("/mob_catalog/0/combat_modifiers/enchant_poison", json!(5)),
        ("/mob_catalog/0/battle_type", json!("RANGE")),
        ("/actors/0/vnum", json!(101)),
    ] {
        let mut root = fixture();
        *root.pointer_mut(pointer).unwrap() = value;
        assert!(compiler::generate(&root).is_err(), "{pointer}");
    }
    let mut root = fixture();
    let mob = root["mob_catalog"][0].clone();
    root["mob_catalog"].as_array_mut().unwrap().push(mob);
    assert!(compiler::generate(&root).is_err());
}
