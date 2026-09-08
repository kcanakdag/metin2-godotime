//! Compile original GOOD-reaction clips from a verified presentation catalog.
use serde_json::Value;
use std::collections::BTreeSet;

pub fn generate(root: &Value) -> Result<String, String> {
    let mut rows = Vec::new();
    let mut vnums = BTreeSet::new();
    for actor in root["actors"].as_array().ok_or("Missing reaction actors")? {
        if actor["kind"] != "mob" {
            continue;
        }
        let vnum = actor["vnum"]
            .as_u64()
            .filter(|n| *n > 0 && *n <= u32::MAX as u64)
            .ok_or("Invalid reaction actor vnum")?;
        if !vnums.insert(vnum) {
            return Err("Duplicate reaction actor vnum".into());
        }
        let id = actor["id"].as_str().ok_or("Missing reaction actor ID")?;
        let modes = actor["modes"].as_array().ok_or("Missing reaction modes")?;
        let mode = modes
            .iter()
            .find(|m| m["id"] == "general")
            .ok_or("Missing general reactions")?;
        let motions = mode["motions"]
            .as_array()
            .ok_or("Missing reaction motions")?;
        let mut directions = Vec::new();
        for action in ["front_damage", "back_damage"] {
            let mut clips = Vec::new();
            let mut ids = BTreeSet::new();
            let mut weight_sum = 0;
            for motion in motions.iter().filter(|m| m["action"] == action) {
                let action_id = motion["action_id"]
                    .as_str()
                    .filter(|s| s.starts_with(&format!("{id}.general.{action}")))
                    .ok_or("Reaction belongs to another actor")?;
                if !ids.insert(action_id) {
                    return Err("Duplicate reaction motion".into());
                }
                let duration = motion["duration_us"]
                    .as_u64()
                    .filter(|n| (1..=60_000_000).contains(n))
                    .ok_or("Invalid reaction duration")?;
                let weight = motion["weight"]
                    .as_u64()
                    .filter(|n| (1..=100).contains(n))
                    .ok_or("Invalid reaction weight")?;
                if motion["loop"] != false
                    || motion["events"].as_array().is_none_or(|e| !e.is_empty())
                {
                    return Err("GOOD reaction must be nonlooping without deferred events".into());
                }
                weight_sum += weight;
                clips.push(format!("(crate::definitions::MonsterReactionDefinition{{id:{action_id:?},duration_us:{duration}}},{weight})"));
            }
            if (action == "front_damage" && clips.is_empty())
                || (!clips.is_empty() && weight_sum != 100)
                || clips.len() > 16
            {
                return Err("Invalid GOOD reaction distribution".into());
            }
            directions.push(format!("&[{}]", clips.join(",")));
        }
        rows.push(format!("({vnum},{},{})", directions[0], directions[1]));
    }
    if rows.is_empty() {
        return Err("Missing mob reactions".into());
    }
    Ok(format!(
        "pub type GoodReactionClips = &'static [(crate::definitions::MonsterReactionDefinition,u8)];\npub type GoodReactionEntry = (u32,GoodReactionClips,GoodReactionClips);\npub const GOOD_REACTIONS:&[GoodReactionEntry]=&[{}];\n",
        rows.join(",")
    ))
}
