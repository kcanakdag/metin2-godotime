use serde_json::{Map, Value};
use std::collections::HashSet;

pub const PLAYER_GENERAL_ACTION_ID: &str = "actor.player.warrior-male.general.normal_attack.v1";
pub const PLAYER_COMBO_ACTION_IDS: [&str; 3] = [
    "actor.player.warrior-male.onehand.combo_1",
    "actor.player.warrior-male.onehand.combo_2",
    "actor.player.warrior-male.onehand.combo_3",
];
pub const MOB_ACTION_ID: &str = "actor.mob.wild-dog-101.general.normal_attack.v1";

const POLICY_ID: &str = "linear-endpoint-approx-v1";
const COORDINATE_CONVERSION: &str = "source-cm-(x,z,-y)/100-then-fixture-yaw-180";
const CARBON_COMMIT: &str = "8cba23114bf1d30c9da597c1ecf49271e00b939d";
const CARBON_READER_SHA256: &str =
    "c3c8698c5987b6783586cc312e291e63eb315f8a5b0968b4f556219688a0fdce";
const MSA_COMPONENT_TOLERANCE_M: f64 = 0.00005;
const MAX_ROOT_DURATION_US: u64 = 1_600_000;
const MAX_ROOT_COMPONENT_M: f64 = 2.0;
const MAX_SOURCE_COMPONENT_CM: f64 = 200.0;

struct InputPin {
    action_id: &'static str,
    gr2_path: &'static str,
    gr2_sha256: &'static str,
    gr2_bytes: u64,
    msa_path: &'static str,
    msa_sha256: &'static str,
    msa_bytes: u64,
}

const INPUT_PINS: [InputPin; 3] = [
    InputPin {
        action_id: PLAYER_COMBO_ACTION_IDS[0],
        gr2_path: "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_01.gr2",
        gr2_sha256: "520fa66815e9757e44ec7f0a7edb12fcd100a149ed9693521fb97b74d728193c",
        gr2_bytes: 34_235,
        msa_path: "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_01.msa",
        msa_sha256: "3659a78e07801bca57a38864092331743b7f30bb269c31d40b92595993d9ccfe",
        msa_bytes: 1_954,
    },
    InputPin {
        action_id: PLAYER_COMBO_ACTION_IDS[1],
        gr2_path: "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_02.gr2",
        gr2_sha256: "8fa914f7d83041c002d7a3b020dfe52091e1cf3793602e65df46a69b9c2cccaa",
        gr2_bytes: 34_765,
        msa_path: "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_02.msa",
        msa_sha256: "fa25fb6ed11338dfac1ff00e673157a766e39fec2b814e1dacb962259d8c7308",
        msa_bytes: 1_784,
    },
    InputPin {
        action_id: PLAYER_COMBO_ACTION_IDS[2],
        gr2_path: "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_03.gr2",
        gr2_sha256: "f1882194129c6c0a17212be8dfe3299e20dbed98035dc3bbdd5e3be52f0ce3b9",
        gr2_bytes: 34_658,
        msa_path: "bin/pack/PC/ymir work/pc/warrior/onehand_sword/combo_03.msa",
        msa_sha256: "69f4e729aea572006b1ed2d826f1f9a35108c06cb608f8e68ec97f42cef13961",
        msa_bytes: 4_444,
    },
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ComboInput {
    pub pre_input_us: i64,
    pub direct_input_us: i64,
    pub input_limit_us: i64,
    pub link_us: i64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RootMotion {
    pub endpoint_x_m: f64,
    pub endpoint_z_m: f64,
    pub duration_us: i64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ComboAction {
    pub combo_input: ComboInput,
    pub root_motion: RootMotion,
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

fn exact_fields(row: &Map<String, Value>, fields: &[&str], label: &str) -> Result<(), String> {
    let expected: HashSet<_> = fields.iter().copied().collect();
    if row.len() != expected.len()
        || row.keys().map(String::as_str).collect::<HashSet<_>>() != expected
    {
        return Err(format!("{label} contains unexpected or missing fields"));
    }
    Ok(())
}

fn bounded_f64(value: &Value, bound: f64, label: &str) -> Result<f64, String> {
    value
        .as_f64()
        .filter(|number| number.is_finite() && number.abs() <= bound)
        .ok_or_else(|| format!("{label} must be a finite bounded number"))
}

fn decimal_f64(value: &Value, bound: f64, label: &str) -> Result<f64, String> {
    let text = value
        .as_str()
        .filter(|text| !text.is_empty() && text.trim() == *text && text.len() <= 32)
        .ok_or_else(|| format!("{label} must be a bounded decimal string"))?;
    text.parse::<f64>()
        .ok()
        .filter(|number| number.is_finite() && number.abs() <= bound)
        .ok_or_else(|| format!("{label} must be a finite bounded decimal string"))
}

fn decimal_vector<const N: usize>(
    value: &Value,
    bound: f64,
    label: &str,
) -> Result<[f64; N], String> {
    let values = value
        .as_array()
        .filter(|values| values.len() == N)
        .ok_or_else(|| format!("{label} must contain exactly {N} decimal strings"))?;
    let mut result = [0.0; N];
    for (index, value) in values.iter().enumerate() {
        result[index] = decimal_f64(value, bound, label)?;
    }
    Ok(result)
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
    exact_fields(
        combo,
        &[
            "pre_input_us",
            "direct_input_us",
            "input_limit_us",
            "link_us",
        ],
        "combo_input",
    )?;
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

fn checked_root_motion(row: &Map<String, Value>) -> Result<RootMotion, String> {
    let root = object(
        row.get("root_motion")
            .ok_or_else(|| "selected combo action requires root_motion".to_owned())?,
        "root_motion",
    )?;
    exact_fields(
        root,
        &["endpoint_x_m", "endpoint_z_m", "duration_us"],
        "root_motion",
    )?;
    let duration_us = exact_u64(root, "duration_us", "root_motion")?;
    let action_duration_us = exact_u64(row, "duration_us", "action")?;
    if duration_us == 0 || duration_us > MAX_ROOT_DURATION_US || duration_us != action_duration_us {
        return Err("root_motion.duration_us must equal the bounded action duration".to_owned());
    }
    Ok(RootMotion {
        endpoint_x_m: bounded_f64(
            root.get("endpoint_x_m").expect("exact fields checked"),
            MAX_ROOT_COMPONENT_M,
            "root_motion.endpoint_x_m",
        )?,
        endpoint_z_m: bounded_f64(
            root.get("endpoint_z_m").expect("exact fields checked"),
            MAX_ROOT_COMPONENT_M,
            "root_motion.endpoint_z_m",
        )?,
        duration_us: duration_us as i64,
    })
}

fn checked_policy(root: &Map<String, Value>) -> Result<(), String> {
    let policy = object(
        root.get("root_motion_policy")
            .ok_or_else(|| "root.root_motion_policy is required".to_owned())?,
        "root_motion_policy",
    )?;
    exact_fields(
        policy,
        &[
            "id",
            "source_endpoint",
            "coordinate_conversion",
            "msa_role",
            "msa_component_tolerance_micrometers",
            "granny_within_cycle_parity",
            "granny_transition_blend_parity",
        ],
        "root_motion_policy",
    )?;
    if exact_text(policy, "id", "root_motion_policy")? != POLICY_ID
        || exact_text(policy, "source_endpoint", "root_motion_policy")?
            != "raw-gr2-loop-translation"
        || exact_text(policy, "coordinate_conversion", "root_motion_policy")?
            != COORDINATE_CONVERSION
        || exact_text(policy, "msa_role", "root_motion_policy")? != "rounded-corroboration-only"
        || policy
            .get("msa_component_tolerance_micrometers")
            .and_then(Value::as_u64)
            != Some(50)
        || policy
            .get("granny_within_cycle_parity")
            .and_then(Value::as_bool)
            != Some(false)
        || policy
            .get("granny_transition_blend_parity")
            .and_then(Value::as_bool)
            != Some(false)
    {
        return Err("root-motion policy or limitation record changed".to_owned());
    }
    Ok(())
}

fn checked_provenance(source: &Map<String, Value>, pin: &InputPin) -> Result<(), String> {
    let check = |name: &str,
                 expected_path: &str,
                 expected_sha: &str,
                 expected_bytes: u64|
     -> Result<(), String> {
        let input = object(
            source
                .get(name)
                .ok_or_else(|| format!("root-motion source {name} is required"))?,
            name,
        )?;
        exact_fields(input, &["path", "sha256", "bytes"], name)?;
        if exact_text(input, "path", name)? != expected_path
            || exact_text(input, "sha256", name)? != expected_sha
            || exact_u64(input, "bytes", name)? != expected_bytes
        {
            return Err(format!("{name} provenance does not match the pinned input"));
        }
        Ok(())
    };
    check("source_gr2", pin.gr2_path, pin.gr2_sha256, pin.gr2_bytes)?;
    check("source_msa", pin.msa_path, pin.msa_sha256, pin.msa_bytes)?;
    let carbon = object(
        source
            .get("carbon_reader")
            .ok_or_else(|| "root-motion Carbon reader provenance is required".to_owned())?,
        "carbon_reader",
    )?;
    exact_fields(carbon, &["commit", "sha256"], "carbon_reader")?;
    if exact_text(carbon, "commit", "carbon_reader")? != CARBON_COMMIT
        || exact_text(carbon, "sha256", "carbon_reader")? != CARBON_READER_SHA256
    {
        return Err("Carbon raw reader provenance does not match the pin".to_owned());
    }
    Ok(())
}

fn checked_source(value: &Value, pin: &InputPin, root_motion: RootMotion) -> Result<(), String> {
    let source = object(value, "root_motion_source")?;
    exact_fields(
        source,
        &[
            "action_id",
            "source_gr2",
            "source_msa",
            "carbon_reader",
            "animation_count",
            "animation_duration_s_raw_decimal",
            "animation_duration_us_rounded",
            "track_group_count",
            "track_group_name",
            "accumulation_flags",
            "loop_translation_source_cm_decimal",
            "endpoint_output_actor_local_godot_m_decimal",
            "periodic_loop",
            "root_motion",
            "initial_placement",
            "msa_accumulation_output_actor_local_godot_m_decimal",
        ],
        "root_motion_source",
    )?;
    if exact_text(source, "action_id", "root_motion_source")? != pin.action_id {
        return Err("root-motion source action is missing, duplicate, or reordered".to_owned());
    }
    checked_provenance(source, pin)?;
    if exact_u64(source, "animation_count", "root_motion_source")? != 1
        || exact_u64(source, "track_group_count", "root_motion_source")? != 1
        || exact_text(source, "track_group_name", "root_motion_source")? != "Bip01"
        || exact_u64(source, "accumulation_flags", "root_motion_source")? != 3
        || !source.get("periodic_loop").is_some_and(Value::is_null)
        || !source.get("root_motion").is_some_and(Value::is_null)
    {
        return Err("raw GR2 accumulation metadata is unsupported".to_owned());
    }
    let raw_duration = decimal_f64(
        source
            .get("animation_duration_s_raw_decimal")
            .expect("exact fields checked"),
        MAX_ROOT_DURATION_US as f64 / 1_000_000.0,
        "root_motion_source.animation_duration_s_raw",
    )?;
    let rounded = (raw_duration * 1_000_000.0).round();
    if raw_duration <= 0.0
        || rounded != root_motion.duration_us as f64
        || exact_u64(
            source,
            "animation_duration_us_rounded",
            "root_motion_source",
        )? != root_motion.duration_us as u64
    {
        return Err("raw GR2 duration does not match the action duration".to_owned());
    }
    let raw = decimal_vector::<3>(
        source
            .get("loop_translation_source_cm_decimal")
            .expect("exact fields checked"),
        MAX_SOURCE_COMPONENT_CM,
        "root_motion_source.loop_translation_source_cm_decimal",
    )?;
    let endpoint = decimal_vector::<3>(
        source
            .get("endpoint_output_actor_local_godot_m_decimal")
            .expect("exact fields checked"),
        MAX_ROOT_COMPONENT_M,
        "root_motion_source.endpoint_output_actor_local_godot_m_decimal",
    )?;
    let converted = [-raw[0] / 100.0, raw[2] / 100.0, raw[1] / 100.0];
    if endpoint != converted
        || endpoint[1] != 0.0
        || root_motion.endpoint_x_m != endpoint[0]
        || root_motion.endpoint_z_m != endpoint[2]
    {
        return Err("root-motion endpoint coordinate conversion is invalid".to_owned());
    }
    let msa = decimal_vector::<3>(
        source
            .get("msa_accumulation_output_actor_local_godot_m_decimal")
            .expect("exact fields checked"),
        MAX_ROOT_COMPONENT_M,
        "root_motion_source.msa_accumulation_output_actor_local_godot_m_decimal",
    )?;
    let differences = [
        msa[0] - endpoint[0],
        msa[1] - endpoint[1],
        msa[2] - endpoint[2],
    ];
    if differences
        .iter()
        .any(|value| value.abs() > MSA_COMPONENT_TOLERANCE_M)
    {
        return Err("MSA accumulation does not corroborate the raw GR2 endpoint".to_owned());
    }
    let placement = object(
        source
            .get("initial_placement")
            .ok_or_else(|| "root-motion InitialPlacement is required".to_owned())?,
        "initial_placement",
    )?;
    exact_fields(
        placement,
        &[
            "flags",
            "position_source_cm_decimal",
            "orientation_xyzw_decimal",
        ],
        "initial_placement",
    )?;
    if exact_u64(placement, "flags", "initial_placement")? > u32::MAX.into() {
        return Err("InitialPlacement.flags is outside the supported bound".to_owned());
    }
    decimal_vector::<3>(
        placement
            .get("position_source_cm_decimal")
            .expect("exact fields checked"),
        MAX_SOURCE_COMPONENT_CM,
        "initial_placement.position_source_cm_decimal",
    )?;
    decimal_vector::<4>(
        placement
            .get("orientation_xyzw_decimal")
            .expect("exact fields checked"),
        2.0,
        "initial_placement.orientation_xyzw_decimal",
    )?;
    Ok(())
}

pub fn validate(root: &Map<String, Value>) -> Result<[ComboAction; 3], String> {
    checked_policy(root)?;
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
        PLAYER_COMBO_ACTION_IDS[2],
        MOB_ACTION_ID,
    ]
    .into_iter()
    .collect();
    if ids.len() != 5 || ids != expected {
        return Err("actions must contain exactly the five selected definitions".to_owned());
    }
    let prefix = root
        .get("base_combo_prefix")
        .and_then(Value::as_array)
        .ok_or_else(|| "root.base_combo_prefix must be an array".to_owned())?;
    if prefix.len() != 3
        || prefix[0].as_str() != Some(PLAYER_COMBO_ACTION_IDS[0])
        || prefix[1].as_str() != Some(PLAYER_COMBO_ACTION_IDS[1])
        || prefix[2].as_str() != Some(PLAYER_COMBO_ACTION_IDS[2])
    {
        return Err("base_combo_prefix must be combo_1 then combo_2 then combo_3".to_owned());
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
            value if value == PLAYER_COMBO_ACTION_IDS[2] => "combo_3",
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
    let sources = root
        .get("root_motion_sources")
        .and_then(Value::as_array)
        .filter(|sources| sources.len() == 3)
        .ok_or_else(|| "root_motion_sources must contain exactly three records".to_owned())?;
    let mut combo = Vec::with_capacity(3);
    for (index, id) in PLAYER_COMBO_ACTION_IDS.into_iter().enumerate() {
        let row = rows
            .iter()
            .find_map(|(candidate, row)| (*candidate == id).then_some(*row))
            .expect("exact action set was checked");
        let action = ComboAction {
            combo_input: checked_combo_input(row)?,
            root_motion: checked_root_motion(row)?,
        };
        checked_source(&sources[index], &INPUT_PINS[index], action.root_motion)?;
        combo.push(action);
    }
    for id in [PLAYER_GENERAL_ACTION_ID, MOB_ACTION_ID] {
        let row = rows
            .iter()
            .find_map(|(candidate, row)| (*candidate == id).then_some(*row))
            .expect("exact action set was checked");
        if row.contains_key("combo_input") || row.contains_key("root_motion") {
            return Err("non-prefix action must omit combo_input and root_motion".to_owned());
        }
    }
    combo
        .try_into()
        .map_err(|_| "base combo prefix must contain exactly three actions".to_owned())
}
