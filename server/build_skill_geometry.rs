//! Independently authored validation/emission of converted skill collision shapes.
use serde_json::Value;

pub const TYPES: &str = "#[derive(Clone,Copy,Debug,PartialEq)] pub struct SkillHitSphere {pub position_m:[f32;3],pub radius_m:f32}\n#[derive(Clone,Copy,Debug,PartialEq)] pub enum SkillHitGeometry { Area {spheres:&'static [SkillHitSphere]}, Weapon {bone:&'static str,length_m:f32} }\n";

fn number(value: &Value, low: f64, high: f64) -> Result<f32, String> {
    value
        .as_f64()
        .filter(|v| v.is_finite() && (low..=high).contains(v))
        .map(|v| v as f32)
        .ok_or("Skill collision number is outside bounds".into())
}

pub fn generate(hit: &Value) -> Result<String, String> {
    if hit["coordinate_space"] != "output_actor_local_godot" {
        return Err("Unknown skill collision coordinate space".into());
    }
    match hit["kind"].as_str() {
        Some("attack_area") => {
            let spheres = hit["spheres"]
                .as_array()
                .filter(|v| !v.is_empty() && v.len() <= 32)
                .ok_or("Invalid skill collision sphere list")?;
            let mut output = Vec::new();
            for sphere in spheres {
                let position = sphere["position_m"]
                    .as_array()
                    .filter(|v| v.len() == 3)
                    .ok_or("Invalid skill collision position")?;
                let position = position
                    .iter()
                    .map(|v| number(v, -20.0, 20.0))
                    .collect::<Result<Vec<_>, _>>()?;
                let radius = number(&sphere["radius_m"], 0.0001, 20.0)?;
                output.push(format!(
                    "SkillHitSphere{{position_m:{position:?},radius_m:{radius:?}}}"
                ));
            }
            Ok(format!(
                "SkillHitGeometry::Area{{spheres:&[{}]}}",
                output.join(",")
            ))
        }
        Some("attack_window") => {
            let bone = hit["bone"]
                .as_str()
                .filter(|v| v.len() <= 128 && !v.chars().any(char::is_control))
                .ok_or("Invalid skill weapon bone")?;
            // Zero-length source windows are retained, not turned into invented areas.
            let length = number(&hit["weapon_length_m"], 0.0, 20.0)?;
            Ok(format!(
                "SkillHitGeometry::Weapon{{bone:{bone:?},length_m:{length:?}}}"
            ))
        }
        _ => Err("Unknown skill collision geometry".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn source_geometry_and_zero_length_windows_are_preserved() {
        let area = json!({"kind":"attack_area","coordinate_space":"output_actor_local_godot",
            "spheres":[{"position_m":[0,1,-2],"radius_m":1.2}]});
        assert!(
            generate(&area)
                .unwrap()
                .contains("position_m:[0.0, 1.0, -2.0]")
        );
        let weapon = json!({"kind":"attack_window","coordinate_space":"output_actor_local_godot",
            "bone":"","weapon_length_m":0});
        assert!(generate(&weapon).unwrap().contains("length_m:0.0"));
    }

    #[test]
    fn invalid_geometry_is_rejected() {
        let valid = json!({"kind":"attack_area","coordinate_space":"output_actor_local_godot",
            "spheres":[{"position_m":[0,1,-2],"radius_m":1.2}]});
        for radius in [json!(0), json!(-1), json!(21), json!(true), Value::Null] {
            let mut hit = valid.clone();
            hit["spheres"][0]["radius_m"] = radius;
            assert!(generate(&hit).is_err());
        }
        for position in [json!([0, 1]), json!([21, 0, 0]), json!([0, "1", 0])] {
            let mut hit = valid.clone();
            hit["spheres"][0]["position_m"] = position;
            assert!(generate(&hit).is_err());
        }
        let mut hit = valid.clone();
        hit["coordinate_space"] = json!("source");
        assert!(generate(&hit).is_err());
        hit = valid;
        hit["spheres"] = json!([]);
        assert!(generate(&hit).is_err());
    }
}
