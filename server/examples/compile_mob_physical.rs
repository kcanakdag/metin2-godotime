//! Validate converted wildlife physical definitions without installing a partial registry.
#[path = "../build_mob_physical.rs"]
mod compiler;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 3 {
        return Err("Usage: compile_mob_physical <normalized.json> <definitions.rs>".into());
    }
    let input = serde_json::from_slice(&std::fs::read(&args[1])?)?;
    let generated = compiler::generate(&input)?;
    std::fs::write(&args[2], generated)?;
    println!(
        "Compiled {} mob physical definitions",
        input["mob_catalog"].as_array().unwrap().len()
    );
    Ok(())
}
