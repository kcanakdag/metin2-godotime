#[path = "../build_class_skills.rs"]
mod compiler;
#[path = "../src/skill_formula.rs"]
mod runtime;

#[test]
fn compiler_rejects_stack_underflow_unknown_instructions_and_injected_fields() {
    for value in [
        serde_json::json!([]),
        serde_json::json!([{"op":"add"}]),
        serde_json::json!([{"op":"execute","code":"anything"}]),
        serde_json::json!([{"op":"variable","index":10}]),
        serde_json::json!([{"op":"constant","value":1,"script":"anything"}]),
        serde_json::json!([{"op":"constant","value":1},{"op":"constant","value":2}]),
    ] {
        assert!(compiler::program(&value).is_err());
    }
    assert!(
        compiler::validate(&serde_json::json!({"schema":"mt2spacetime.skills","version":1}))
            .is_err()
    );
    assert!(compiler::generate(&serde_json::json!({})).is_err());
    assert_eq!(compiler::program(&serde_json::json!([{"op":"constant","value":50},{"op":"constant","value":130},{"op":"variable","index":4},{"op":"mul"},{"op":"add"}])).unwrap(), "&[Op::Constant(50.0),Op::Constant(130.0),Op::Variable(4),Op::Mul,Op::Add]");
}
