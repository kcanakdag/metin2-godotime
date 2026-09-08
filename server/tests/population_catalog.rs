#[path = "../src/population_catalog.rs"]
mod population_catalog;
use population_catalog::Catalog;
use serde_json::{Value, json};

fn fixture() -> Value {
    json!({"schema":"mt2spacetime.original-mob-population","version":1,
      "groups":[{"vnum":10,"members":[{"slot":0,"leader":true,"vnum":101},
        {"slot":1,"leader":false,"vnum":171}]}],
      "group_selectors":[{"vnum":20,"variants":[{"slot":1,"group_vnum":10,"effective_weight":1}]}],
      "entries":[{"source_line":1,"family":"r","reference_vnum":20,"bounds_cm":[0,0,100,100],
        "interval_us":5000000,"enabled":true,"max_live_units":1,"forced_aggressive":false}]})
}

#[test]
fn preserves_leader_order_selector_and_disabled_or_forced_entries() {
    let mut input = fixture();
    let catalog = Catalog::parse(&input).unwrap();
    assert_eq!(catalog.groups[&10], [101, 171]);
    assert_eq!(catalog.selectors[&20], [10]);
    let e = &catalog.entries[0];
    assert!(e.selector);
    assert_eq!((e.source_line, e.reference, e.capacity), (1, 20, 1));
    assert_eq!(e.bounds_cm, [0, 0, 100, 100]);
    assert_eq!(e.interval_us, 5000000);
    input["entries"][0]["family"] = json!("ga");
    input["entries"][0]["reference_vnum"] = json!(10);
    input["entries"][0]["forced_aggressive"] = json!(true);
    input["entries"][0]["interval_us"] = json!(0);
    input["entries"][0]["enabled"] = json!(false);
    let catalog = Catalog::parse(&input).unwrap();
    assert!(!catalog.entries[0].selector);
    assert!(catalog.entries[0].forced_aggressive);
    assert_eq!(catalog.entries[0].interval_us, 0);
}

#[test]
fn rejects_broken_references_flags_order_and_bounds_before_spawning() {
    for (pointer, value) in [
        ("/entries/0/reference_vnum", json!(99)),
        ("/entries/0/source_line", json!(0)),
        ("/entries/0/family", json!("m")),
        ("/entries/0/forced_aggressive", json!(true)),
        ("/entries/0/enabled", json!(false)),
        ("/entries/0/interval_us", json!(-1)),
        ("/entries/0/max_live_units", json!(1001)),
        ("/entries/0/bounds_cm", json!([100, 0, 0, 100])),
        ("/groups/0/members/1/leader", json!(true)),
        ("/groups/0/members/1/slot", json!(2)),
        ("/group_selectors/0/variants/0/group_vnum", json!(99)),
        ("/group_selectors/0/variants/0/effective_weight", json!(2)),
    ] {
        let mut input = fixture();
        *input.pointer_mut(pointer).unwrap() = value;
        assert!(Catalog::parse(&input).is_err(), "{pointer}");
    }
    for key in ["groups", "group_selectors", "entries"] {
        let mut input = fixture();
        let duplicate = input[key][0].clone();
        input[key].as_array_mut().unwrap().push(duplicate);
        assert!(Catalog::parse(&input).is_err(), "duplicate {key}");
    }
}
