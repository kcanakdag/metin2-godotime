use serde_json::{Map, Value};
use std::collections::HashSet;

pub const PLAYER_GENERAL_ACTION_ID: &str = "actor.player.warrior-male.general.normal_attack.v1";
pub const PLAYER_COMBO_ACTION_IDS: [&str; 2] = [
    "actor.player.warrior-male.onehand.combo_1",
    "actor.player.warrior-male.onehand.combo_2",
];
pub const MOB_ACTION_ID: &str = "actor.mob.wild-dog-101.general.normal_attack.v1";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ComboInput {
    pub pre_input_us: i64,
    pub direct_input_us: i64,
    pub input_limit_us: i64,
    pub link_us: i64,
}

fn object<'a>(value: &'a Value, label: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| format!("{label} must be an object"))
}

fn exact_u64(row: &Map<String, Value>, name: &str, label: &str) -> Result<u64, String> {
    row.get(name)
        .and_then(Value::as_u64)
        .ok_or_else(|| format!("{label}.{name} must be an unsigned integer"))
}

fn exact_text<'a>(row: &'a Map<String, Value>, name: &str, label: &str) -> Result<&'a str, String> {
    row.get(name)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{label}.{name} must be a nonempty string"))
}

fn checked_combo_input(row: &Map<String, Value>) -> Result<ComboInput, String> {
    let duration_us = exact_u64(row, "duration_us", "action")?;
    if duration_us == 0 || duration_us > 60_000_000 {
        return Err("action.duration_us must be in 1..=60000000".to_owned());
    }
    let combo = object(
        row.get("combo_input")
            .ok_or_else(|| "selected combo action requires combo_input".to_owned())?,
        "combo_input",
    )?;
    let expected: HashSet<&str> = [
        "pre_input_us",
        "direct_input_us",
        "input_limit_us",
        "link_us",
    ]
    .into_iter()
    .collect();
    if combo.len() != expected.len()
        || combo.keys().map(String::as_str).collect::<HashSet<_>>() != expected
    {
        return Err("combo_input must contain exactly the four selected timing fields".to_owned());
    }
    let bounded = |name| -> Result<i64, String> {
        let value = exact_u64(combo, name, "combo_input")?;
        if value > 60_000_000 {
            return Err(format!("combo_input.{name} must be in 0..=60000000"));
        }
        i64::try_from(value).map_err(|_| format!("combo_input.{name} is outside i64"))
    };
    let result = ComboInput {
        pre_input_us: bounded("pre_input_us")?,
        direct_input_us: bounded("direct_input_us")?,
        input_limit_us: bounded("input_limit_us")?,
        link_us: bounded("link_us")?,
    };
    if !(result.pre_input_us < result.direct_input_us
        && result.direct_input_us < result.input_limit_us
        && result.input_limit_us <= duration_us as i64)
    {
        return Err("combo_input must satisfy pre < direct < limit <= duration".to_owned());
    }
    Ok(result)
}

pub fn validate(root: &Map<String, Value>) -> Result<[ComboInput; 2], String> {
    let actors = root
        .get("actors")
        .and_then(Value::as_array)
        .ok_or_else(|| "root.actors must be an array".to_owned())?;
    let player_rows = actors
        .iter()
        .map(|value| object(value, "actor"))
        .collect::<Result<Vec<_>, _>>()?;
    let player_rows = player_rows
        .iter()
        .filter(|row| row.get("id").and_then(Value::as_str) == Some("actor.player.warrior-male"))
        .collect::<Vec<_>>();
    if player_rows.len() != 1 {
        return Err("actors must contain exactly one selected player".to_owned());
    }
    let primary = object(
        player_rows[0]
            .get("primary_actions")
            .ok_or_else(|| "player.primary_actions is required".to_owned())?,
        "player.primary_actions",
    )?;
    if exact_text(primary, "onehand", "player.primary_actions")? != PLAYER_COMBO_ACTION_IDS[0] {
        return Err("player onehand primary action must be the combo prefix head".to_owned());
    }
    let actions = root
        .get("actions")
        .and_then(Value::as_array)
        .ok_or_else(|| "root.actions must be an array".to_owned())?;
    let mut rows = Vec::with_capacity(actions.len());
    let mut ids = HashSet::new();
    for value in actions {
        let row = object(value, "action")?;
        let id = row
            .get("id")
            .and_then(Value::as_str)
            .filter(|id| !id.is_empty())
            .ok_or_else(|| "action.id must be a nonempty string".to_owned())?;
        if !ids.insert(id) {
            return Err("action ids must be unique".to_owned());
        }
        rows.push((id, row));
    }
    let expected: HashSet<&str> = [
        PLAYER_GENERAL_ACTION_ID,
        PLAYER_COMBO_ACTION_IDS[0],
        PLAYER_COMBO_ACTION_IDS[1],
        MOB_ACTION_ID,
    ]
    .into_iter()
    .collect();
    if ids.len() != 4 || ids != expected {
        return Err("actions must contain exactly the four selected definitions".to_owned());
    }
    let prefix = root
        .get("base_combo_prefix")
        .and_then(Value::as_array)
        .ok_or_else(|| "root.base_combo_prefix must be an array".to_owned())?;
    if prefix.len() != 2
        || prefix[0].as_str() != Some(PLAYER_COMBO_ACTION_IDS[0])
        || prefix[1].as_str() != Some(PLAYER_COMBO_ACTION_IDS[1])
    {
        return Err("base_combo_prefix must be combo_1 then combo_2".to_owned());
    }
    for (id, row) in &rows {
        let is_combo = PLAYER_COMBO_ACTION_IDS.contains(id);
        let expected_actor = if *id == MOB_ACTION_ID {
            "actor.mob.wild-dog-101"
        } else {
            "actor.player.warrior-male"
        };
        let expected_mode = if is_combo { "onehand" } else { "general" };
        let expected_action = match *id {
            value if value == PLAYER_COMBO_ACTION_IDS[0] => "combo_1",
            value if value == PLAYER_COMBO_ACTION_IDS[1] => "combo_2",
            _ => "normal_attack",
        };
        if exact_text(row, "actor_id", "action")? != expected_actor
            || exact_text(row, "mode", "action")? != expected_mode
            || exact_text(row, "action", "action")? != expected_action
        {
            return Err(format!(
                "action {id:?} does not match the selected actor/mode/action"
            ));
        }
        let required = row
            .get("required_item_vnums")
            .and_then(Value::as_array)
            .ok_or_else(|| "action.required_item_vnums must be an array".to_owned())?;
        let valid_required = if is_combo {
            required.len() == 1 && required[0].as_u64() == Some(10)
        } else {
            required.is_empty()
        };
        if !valid_required {
            return Err(format!(
                "action {id:?} has unexpected equipment requirements"
            ));
        }
    }
    let mut combo = Vec::with_capacity(2);
    for id in PLAYER_COMBO_ACTION_IDS {
        let row = rows
            .iter()
            .find_map(|(candidate, row)| (*candidate == id).then_some(*row))
            .expect("exact action set was checked");
        combo.push(checked_combo_input(row)?);
    }
    for id in [PLAYER_GENERAL_ACTION_ID, MOB_ACTION_ID] {
        let row = rows
            .iter()
            .find_map(|(candidate, row)| (*candidate == id).then_some(*row))
            .expect("exact action set was checked");
        if row.contains_key("combo_input") {
            return Err("non-prefix action must omit combo_input".to_owned());
        }
    }
    combo
        .try_into()
        .map_err(|_| "base combo prefix must contain exactly two inputs".to_owned())
}
