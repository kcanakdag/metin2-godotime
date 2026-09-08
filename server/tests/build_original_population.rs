#[path = "../build_original_population.rs"]
mod build_original_population;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

fn fixture() -> Value {
    json!({"schema":"mt2spacetime.original-mob-population","version":1,
      "groups":[{"vnum":10,"members":[{"slot":0,"leader":true,"vnum":101},
        {"slot":1,"leader":false,"vnum":171}]}],
      "group_selectors":[{"vnum":20,"variants":[{"slot":1,"group_vnum":10,"effective_weight":1}]}],
      "entries":[{"source_line":1,"family":"r","reference_vnum":20,"bounds_cm":[0,0,100,100],
        "interval_us":5000000,"enabled":true,"max_live_units":1,"forced_aggressive":false}]})
}

fn signed(mut value: Value) -> Vec<u8> {
    value.as_object_mut().unwrap().remove("content_hash");
    let hash = format!("{:x}", Sha256::digest(serde_json::to_vec(&value).unwrap()));
    value["content_hash"] = json!(hash);
    serde_json::to_vec(&value).unwrap()
}
fn inventory() -> Value {
    let mut value = fixture();
    value["map"] = json!("metin2_map_a1");
    value["runtime_policy"] = json!({"first_tick_jitter_us":[0,16000000],
        "first_tick_jitter_step_us":1000000,"unit_release":"owner-destruction",
        "zero_interval":"disabled-including-initial-spawn"});
    value
}
#[test]
fn compiles_valid_inventory_and_rejects_missing_species_or_changed_policy() {
    let registered = [101, 171].into();
    let bytes = signed(inventory());
    let output = build_original_population::compile(&bytes, Some(&registered)).unwrap();
    assert!(output.contains("groups: &[&[101, 171]]"));
    assert!(output.contains("startup_jitter_max_seconds: 16"));
    assert!(build_original_population::compile(&bytes, Some(&[101].into())).is_err());
    let mut changed = inventory();
    changed["runtime_policy"]["unit_release"] = json!("death");
    assert!(build_original_population::compile(&signed(changed), Some(&registered)).is_err());
    let mut corrupted: Value = serde_json::from_slice(&bytes).unwrap();
    corrupted["entries"][0]["max_live_units"] = json!(2);
    assert!(
        build_original_population::compile(
            &serde_json::to_vec(&corrupted).unwrap(),
            Some(&registered)
        )
        .is_err()
    );
}
