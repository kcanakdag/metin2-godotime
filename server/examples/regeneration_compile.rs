//! Emit typed regeneration entries from a hash-verified original inventory.
#[path = "../build_original_population.rs"]
mod build_original_population;

fn compile() -> Result<String, String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 1 {
        return Err("Usage: regeneration_compile POPULATION_JSON".into());
    }
    let bytes = std::fs::read(&args[0]).map_err(|e| e.to_string())?;
    build_original_population::compile(&bytes, None)
}

fn main() {
    match compile() {
        Ok(output) => print!("{output}"),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
