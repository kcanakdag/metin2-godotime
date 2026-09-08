//! Offline authoring check: validates a candidate catalog and emits typed Rust definitions.
#[path = "../build_class_skills.rs"]
mod compiler;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 3 {
        return Err("Usage: compile_class_skills <catalog.json> <definitions.rs>".into());
    }
    let root = serde_json::from_slice(&std::fs::read(&args[1])?)?;
    std::fs::write(&args[2], compiler::generate(&root)?)?;
    println!("Validated and compiled the complete class skill catalog.");
    Ok(())
}
