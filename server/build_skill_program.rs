//! Shared validation and Rust generation for bounded skill arithmetic.
use serde_json::Value;

pub fn program(value: &Value) -> Result<String, String> {
    let ops = value
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 128)
        .ok_or("Invalid formula program length")?;
    let mut stack = 0_i32;
    let mut result = Vec::new();
    for instruction in ops {
        let fields = instruction
            .as_object()
            .ok_or("Formula instruction must be an object")?;
        let op = instruction["op"].as_str().ok_or("Missing formula opcode")?;
        let rendered = match op {
            "constant" => {
                if fields.len() != 2 {
                    return Err("Unexpected constant fields".into());
                }
                let v = instruction["value"]
                    .as_f64()
                    .filter(|v| v.is_finite() && v.abs() <= 1_000_000.0)
                    .ok_or("Invalid formula constant")?;
                stack += 1;
                format!("Op::Constant({v:?})")
            }
            "variable" => {
                if fields.len() != 2 {
                    return Err("Unexpected variable fields".into());
                }
                let index = instruction["index"]
                    .as_u64()
                    .filter(|index| *index <= 9)
                    .ok_or("Invalid skill variable index")?;
                stack += 1;
                format!("Op::Variable({index})")
            }
            "neg" | "floor" => {
                if fields.len() != 1 || stack < 1 {
                    return Err("Invalid unary instruction".into());
                }
                format!("Op::{}", if op == "neg" { "Neg" } else { "Floor" })
            }
            "add" | "sub" | "mul" | "div" | "number" => {
                if fields.len() != 1 || stack < 2 {
                    return Err("Invalid binary instruction".into());
                }
                stack -= 1;
                let name = match op {
                    "add" => "Add",
                    "sub" => "Sub",
                    "mul" => "Mul",
                    "div" => "Div",
                    _ => "Number",
                };
                format!("Op::{name}")
            }
            _ => return Err("Unsupported formula opcode".into()),
        };
        if stack > 32 {
            return Err("Formula stack exceeds bounds".into());
        }
        result.push(rendered);
    }
    if stack != 1 {
        return Err("Formula does not produce one result".into());
    }
    Ok(format!("&[{}]", result.join(",")))
}
