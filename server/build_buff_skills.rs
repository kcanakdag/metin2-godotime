//! Generate trusted runtime buff programs using the same arithmetic validator.
#[path = "build_skill_program.rs"]
mod arithmetic;
use serde_json::Value;
use std::collections::BTreeSet;

fn program(value: &Value) -> Result<String, String> {
    if value
        .as_array()
        .is_some_and(|ops| ops.iter().any(|op| op["op"] == "number"))
    {
        return Err("Random self-buff programs are unsupported".into());
    }
    arithmetic::program(value)
}

pub fn generate(id: u64, value: &Value) -> Result<String, String> {
    if value.as_object().is_none_or(|fields| fields.len() != 3) {
        return Err("Invalid self-buff definition fields".into());
    }
    let cost = program(&value["sp_cost"])?;
    let cooldown = program(&value["cooldown"])?;
    let rows = value["modifiers"]
        .as_array()
        .filter(|rows| !rows.is_empty() && rows.len() <= 4)
        .ok_or("Invalid self-buff modifier count")?;
    let mut points = BTreeSet::new();
    let mut modifiers = Vec::new();
    for row in rows {
        if row.as_object().is_none_or(|fields| fields.len() != 3) {
            return Err("Invalid self-buff modifier fields".into());
        }
        let point = match row["point"].as_str() {
            Some("attack_speed") => "AttackSpeed",
            Some("movement_speed") => "MovementSpeed",
            Some("attack_grade") => "AttackGrade",
            Some("normal_damage_taken_percent") => "NormalDamageTakenPercent",
            _ => return Err("Unsupported self-buff point".into()),
        };
        if !points.insert(point) {
            return Err("Duplicate self-buff point".into());
        }
        let duration = program(&row["duration"])?;
        let formula = if let Some(factor) = row.get("power_percent_factor") {
            let factor = factor
                .as_u64()
                .filter(|factor| *factor <= 1000)
                .ok_or("Invalid self-buff integer power factor")?;
            format!("crate::buff_capture::ModifierValue::PowerPercent({factor})")
        } else {
            let expression = program(&row["value"])?;
            format!("crate::buff_capture::ModifierValue::Formula({expression})")
        };
        modifiers.push(format!("crate::buff_capture::ModifierProgram{{point:crate::buff_lifecycle::Point::{point},value:{formula},duration:{duration}}}"));
    }
    Ok(format!(
        "{{use crate::skill_formula::Op; crate::buff_capture::Definition{{skill_vnum:{id},sp_cost:{cost},cooldown:{cooldown},modifiers:&[{}]}}}}",
        modifiers.join(",")
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn definition() -> Value {
        json!({"sp_cost":[{"op":"constant","value":57}],
            "cooldown":[{"op":"constant","value":67}],
            "modifiers":[{"point":"attack_speed",
                "value":[{"op":"constant","value":2}],
                "duration":[{"op":"constant","value":64}]}]})
    }

    #[test]
    fn malformed_or_ambiguous_modifiers_reject() {
        assert!(generate(3, &definition()).is_ok());
        for point in ["", "client_damage", "HP"] {
            let mut value = definition();
            value["modifiers"][0]["point"] = json!(point);
            assert!(generate(3, &value).is_err());
        }
        let mut value = definition();
        let duplicate = value["modifiers"][0].clone();
        value["modifiers"].as_array_mut().unwrap().push(duplicate);
        assert!(generate(3, &value).is_err());
        let mut value = definition();
        value["modifiers"][0]["power_percent_factor"] = json!(25);
        assert!(generate(3, &value).is_err());
    }

    #[test]
    fn random_and_invalid_programs_do_not_enter_deterministic_runtime() {
        for program in [
            json!([{"op":"variable","index":10}]),
            json!([{"op":"add"}]),
            json!([{"op":"constant","value":1},{"op":"constant","value":2},{"op":"number"}]),
        ] {
            let mut value = definition();
            value["sp_cost"] = program;
            assert!(generate(3, &value).is_err());
        }
    }
}
