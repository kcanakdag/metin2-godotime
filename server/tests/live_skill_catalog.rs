#[path = "../build_skills.rs"]
mod compiler;

#[test]
fn installed_catalog_compiles_without_changing_its_event_contract() {
    let bytes = include_bytes!("../../client/assets/imported/skills/catalog.v1.json");
    assert_eq!(compiler::generate(bytes).unwrap(), compiler::build());
}
