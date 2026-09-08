//! Validate a candidate live catalog without replacing installed client content.
#[path = "../build_skills.rs"]
mod compiler;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 3 {
        return Err(
            "Usage: compile_live_skills <catalog.json|--installed> <definitions.rs>".into(),
        );
    }
    let generated = if args[1] == "--installed" {
        compiler::build()
    } else {
        compiler::generate(&std::fs::read(&args[1])?)?
    };
    std::fs::write(&args[2], generated)?;
    println!("Validated and compiled the candidate live skill catalog.");
    Ok(())
}
