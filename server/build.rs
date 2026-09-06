use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

const PROFILE: &str = "p0-warrior-dog";
const DEFINITIONS: &str = "content/p0-warrior-dog/actions.v1.json";

fn fail(message: impl AsRef<str>) -> ! {
    panic!(
        "trusted action definitions are invalid: {}\nRun `python3 tools/content_compile.py compile` from the repository root.",
        message.as_ref()
    )
}

fn object<'a>(value: &'a Value, label: &str) -> &'a Map<String, Value> {
    value
        .as_object()
        .unwrap_or_else(|| fail(format!("{label} must be an object")))
}

fn array<'a>(value: &'a Value, label: &str) -> &'a [Value] {
    value
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or_else(|| fail(format!("{label} must be an array")))
}

fn field<'a>(row: &'a Map<String, Value>, name: &str, label: &str) -> &'a Value {
    row.get(name)
        .unwrap_or_else(|| fail(format!("{label}.{name} is required")))
}

fn text<'a>(row: &'a Map<String, Value>, name: &str, label: &str) -> &'a str {
    field(row, name, label)
        .as_str()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| fail(format!("{label}.{name} must be a nonempty string")))
}

fn u64_value(row: &Map<String, Value>, name: &str, label: &str) -> u64 {
    field(row, name, label)
        .as_u64()
        .unwrap_or_else(|| fail(format!("{label}.{name} must be an unsigned integer")))
}

fn positive_f32(row: &Map<String, Value>, name: &str, label: &str) -> f32 {
    let value = field(row, name, label)
        .as_f64()
        .unwrap_or_else(|| fail(format!("{label}.{name} must be a number")));
    if !value.is_finite() || value <= 0.0 || value > f64::from(f32::MAX) {
        fail(format!("{label}.{name} must be finite and positive"));
    }
    let converted = value as f32;
    if !converted.is_finite() || converted <= 0.0 {
        fail(format!("{label}.{name} is outside the supported f32 range"));
    }
    converted
}

fn bounded_u32(row: &Map<String, Value>, name: &str, label: &str, maximum: u32) -> u32 {
    let value = u64_value(row, name, label);
    if value == 0 || value > u64::from(maximum) {
        fail(format!("{label}.{name} must be in 1..={maximum}"));
    }
    value as u32
}

fn actor<'a>(actors: &'a [Value], id: &str) -> &'a Map<String, Value> {
    actors
        .iter()
        .map(|value| object(value, "actor"))
        .find(|row| text(row, "id", "actor") == id)
        .unwrap_or_else(|| fail(format!("actor {id:?} is missing")))
}

fn action<'a>(actions: &'a [Value], id: &str) -> &'a Map<String, Value> {
    actions
        .iter()
        .map(|value| object(value, "action"))
        .find(|row| text(row, "id", "action") == id)
        .unwrap_or_else(|| fail(format!("action {id:?} is missing")))
}

#[derive(Clone, Copy)]
struct Attack<'a> {
    id: &'a str,
    duration_us: i64,
    cooldown_us: i64,
    hit_start_us: i64,
    hit_end_us: i64,
    range_m: f32,
}

fn checked_attack<'a>(
    actions: &'a [Value],
    id: &'a str,
    actor_id: &str,
    mode: &str,
    expected_action: &str,
    required_item: Option<u32>,
) -> Attack<'a> {
    let row = action(actions, id);
    if text(row, "actor_id", "action") != actor_id {
        fail(format!("action {id:?} belongs to the wrong actor"));
    }
    if text(row, "mode", "action") != mode || text(row, "action", "action") != expected_action {
        fail(format!(
            "action {id:?} has an unexpected mode or action name"
        ));
    }
    let duration_us = bounded_u32(row, "duration_us", "action", 60_000_000) as i64;
    let cooldown_us = bounded_u32(row, "cooldown_us", "action", 60_000_000) as i64;
    let required = array(
        field(row, "required_item_vnums", "action"),
        "required_item_vnums",
    );
    let expected: Vec<u64> = required_item.into_iter().map(u64::from).collect();
    let actual: Vec<u64> = required
        .iter()
        .map(|value| {
            value
                .as_u64()
                .unwrap_or_else(|| fail("required item vnums must be unsigned integers"))
        })
        .collect();
    if actual != expected {
        fail(format!(
            "action {id:?} has unexpected equipment requirements"
        ));
    }
    let windows = array(field(row, "hit_windows", "action"), "hit_windows");
    if windows.len() != 1 {
        fail(format!(
            "action {id:?} must have exactly one hit window in this fixture"
        ));
    }
    let mut checked = Vec::with_capacity(windows.len());
    for value in windows {
        let window = object(value, "hit_window");
        let start = u64_value(window, "start_us", "hit_window");
        let end = u64_value(window, "end_us", "hit_window");
        if start >= end || end > duration_us as u64 {
            fail(format!(
                "action {id:?} has a hit window outside its duration"
            ));
        }
        let shape = text(window, "shape", "hit_window");
        if shape != "melee_reach" {
            fail(format!("action {id:?} has unsupported hit shape {shape:?}"));
        }
        checked.push((
            start as i64,
            end as i64,
            positive_f32(window, "range_m", "hit_window"),
        ));
    }
    checked.sort_by_key(|window| (window.0, window.1));
    let (hit_start_us, hit_end_us, range_m) = checked[0];
    Attack {
        id,
        duration_us,
        cooldown_us,
        hit_start_us,
        hit_end_us,
        range_m,
    }
}

fn rust_string(value: &str) -> String {
    format!("{value:?}")
}

fn emit_attack(output: &mut String, name: &str, attack: Attack<'_>) {
    writeln!(
        output,
        "pub const {name}: AttackDefinition = AttackDefinition {{ id: {}, duration_us: {}, cooldown_us: {}, hit_start_us: {}, hit_end_us: {}, range_m: {:?} }};",
        rust_string(attack.id),
        attack.duration_us,
        attack.cooldown_us,
        attack.hit_start_us,
        attack.hit_end_us,
        attack.range_m
    )
    .unwrap();
}

fn main() {
    println!("cargo:rerun-if-changed={DEFINITIONS}");
    let path = Path::new(DEFINITIONS);
    let bytes = fs::read(path).unwrap_or_else(|error| {
        fail(format!(
            "cannot read {} ({error}); the generated server artifact is a required build input",
            path.display()
        ))
    });
    let mut payload: Value = serde_json::from_slice(&bytes)
        .unwrap_or_else(|error| fail(format!("{} is not valid JSON ({error})", path.display())));
    let root = object(&payload, "root");
    if text(root, "schema", "root") != "mt2spacetime.trusted-action-definitions"
        || u64_value(root, "schema_version", "root") != 1
        || text(root, "profile_id", "root") != PROFILE
        || text(root, "time_unit", "root") != "microsecond"
        || text(root, "linear_unit", "root") != "meter"
    {
        fail("schema, profile, or unit contract does not match this server");
    }
    let claimed_hash = text(root, "gameplay_definition_hash", "root").to_owned();
    if claimed_hash.len() != 64 || !claimed_hash.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        fail("gameplay_definition_hash must be a SHA-256 hex digest");
    }
    object(&payload, "root");
    payload
        .as_object_mut()
        .expect("root was checked")
        .remove("gameplay_definition_hash");
    let canonical = serde_json::to_vec(&payload).expect("trusted definitions serialize");
    let actual_hash = format!("{:x}", Sha256::digest(canonical));
    if actual_hash != claimed_hash {
        fail(format!(
            "gameplay_definition_hash mismatch: claimed {claimed_hash}, computed {actual_hash}"
        ));
    }
    let payload: Value = serde_json::from_slice(&bytes).expect("payload was checked");
    let root = object(&payload, "root");
    let content_hash = text(root, "content_hash", "root");
    if content_hash.len() != 64 || !content_hash.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        fail("content_hash must be a SHA-256 hex digest");
    }
    let actors = array(field(root, "actors", "root"), "actors");
    let actions = array(field(root, "actions", "root"), "actions");
    let items = array(field(root, "items", "root"), "items");
    let mut action_ids = HashSet::new();
    for value in actions {
        let row = object(value, "action");
        if !action_ids.insert(text(row, "id", "action")) {
            fail("action ids must be unique");
        }
    }

    let player_id = "actor.player.warrior-male";
    let player = actor(actors, player_id);
    if u64_value(player, "race_id", "player") != 0 {
        fail("selected player race_id must be 0");
    }
    if text(player, "model_key", "player") != "warrior_m" {
        fail("selected player model_key must be warrior_m");
    }
    let player_base_damage = bounded_u32(player, "base_damage", "player", u16::MAX.into()) as u16;
    let player_cooldown = bounded_u32(player, "attack_cooldown_us", "player", 60_000_000) as i64;
    let player_range = positive_f32(player, "attack_range_m", "player");
    let primary = object(
        field(player, "primary_actions", "player"),
        "primary_actions",
    );
    let general_id = text(primary, "general", "primary_actions");
    let onehand_id = text(primary, "onehand", "primary_actions");
    let general = checked_attack(
        actions,
        general_id,
        player_id,
        "general",
        "normal_attack",
        None,
    );
    let onehand = checked_attack(
        actions,
        onehand_id,
        player_id,
        "onehand",
        "combo_1",
        Some(10),
    );
    if general.cooldown_us != player_cooldown
        || onehand.cooldown_us != player_cooldown
        || general.range_m != player_range
        || onehand.range_m != player_range
    {
        fail("player actions disagree with the authoritative player definition");
    }

    let mob_id = "actor.mob.wild-dog-101";
    let mob = actor(actors, mob_id);
    let mob_vnum = bounded_u32(mob, "vnum", "mob", u32::MAX);
    if mob_vnum != 101 || text(mob, "actor_id", "mob") != mob_id {
        fail("selected mob must be Wild Dog vnum 101");
    }
    let mob_action_id = text(mob, "primary_action_id", "mob");
    let mob_attack = checked_attack(
        actions,
        mob_action_id,
        mob_id,
        "general",
        "normal_attack",
        None,
    );
    if mob_attack.cooldown_us != bounded_u32(mob, "attack_cooldown_us", "mob", 60_000_000) as i64 {
        fail("mob action cooldown disagrees with the authoritative mob definition");
    }
    if mob_attack.range_m != positive_f32(mob, "attack_range_m", "mob") {
        fail("mob action range disagrees with the authoritative mob definition");
    }
    let damage_min = bounded_u32(mob, "damage_min", "mob", u16::MAX.into()) as u16;
    let damage_max = bounded_u32(mob, "damage_max", "mob", u16::MAX.into()) as u16;
    if damage_min > damage_max {
        fail("mob damage_min exceeds damage_max");
    }
    let reward_gold_min = bounded_u32(mob, "reward_gold_min", "mob", u32::MAX);
    let reward_gold_max = bounded_u32(mob, "reward_gold_max", "mob", u32::MAX);
    if reward_gold_min > reward_gold_max {
        fail("mob reward_gold_min exceeds reward_gold_max");
    }

    let item = items
        .iter()
        .map(|value| object(value, "item"))
        .find(|row| u64_value(row, "vnum", "item") == 10)
        .unwrap_or_else(|| fail("starter sword vnum 10 is missing"));
    let attack_bonus = bounded_u32(item, "attack_bonus", "item", u16::MAX.into()) as u16;
    if text(item, "equipment_mode", "item") != "onehand" {
        fail("starter sword must select onehand actions");
    }
    let allowed = array(
        field(item, "allowed_actor_ids", "item"),
        "allowed_actor_ids",
    );
    if allowed.len() != 1 || allowed[0].as_str() != Some(player_id) {
        fail("starter sword must be restricted to the selected player actor");
    }

    let mut output = String::from(
        "// Generated at build time from server/content/p0-warrior-dog/actions.v1.json.\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct AttackDefinition {\n\
         \tpub id: &'static str,\n\
         \tpub duration_us: i64,\n\
         \tpub cooldown_us: i64,\n\
         \tpub hit_start_us: i64,\n\
         \tpub hit_end_us: i64,\n\
         \tpub range_m: f32,\n\
         }\n",
    );
    writeln!(
        output,
        "pub const PROFILE_ID: &str = {};",
        rust_string(PROFILE)
    )
    .unwrap();
    writeln!(
        output,
        "pub const DEFINITION_HASH: &str = {};",
        rust_string(&claimed_hash)
    )
    .unwrap();
    writeln!(
        output,
        "pub const PLAYER_BASE_DAMAGE: u16 = {player_base_damage};"
    )
    .unwrap();
    emit_attack(&mut output, "PLAYER_GENERAL_ATTACK", general);
    emit_attack(&mut output, "PLAYER_ONEHAND_ATTACK", onehand);
    writeln!(output, "pub const WEAPON_VNUM: u32 = 10;").unwrap();
    writeln!(
        output,
        "pub const WEAPON_ATTACK_BONUS: u16 = {attack_bonus};"
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_ACTOR_ID: &str = {};",
        rust_string(mob_id)
    )
    .unwrap();
    writeln!(output, "pub const MOB_VNUM: u32 = {mob_vnum};").unwrap();
    writeln!(
        output,
        "pub const MOB_NAME: &str = {};",
        rust_string(text(mob, "name", "mob"))
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_MODEL_KEY: &str = {};",
        rust_string(text(mob, "model_key", "mob"))
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_MOTION_SET: &str = {};",
        rust_string(text(mob, "motion_set", "mob"))
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_MAX_HEALTH: u16 = {};",
        bounded_u32(mob, "max_health", "mob", u16::MAX.into())
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_MOVE_SPEED_MPS: f32 = {:?};",
        positive_f32(mob, "move_speed_mps", "mob")
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_ACQUISITION_RANGE_M: f32 = {:?};",
        positive_f32(mob, "acquisition_range_m", "mob")
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_CHASE_HOME_RANGE_M: f32 = {:?};",
        positive_f32(mob, "chase_home_range_m", "mob")
    )
    .unwrap();
    writeln!(output, "pub const MOB_DAMAGE_MIN: u16 = {damage_min};").unwrap();
    writeln!(output, "pub const MOB_DAMAGE_MAX: u16 = {damage_max};").unwrap();
    writeln!(
        output,
        "pub const MOB_RESPAWN_US: i64 = {};",
        bounded_u32(mob, "respawn_us", "mob", 600_000_000) as i64
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_REWARD_GOLD_MIN: u32 = {reward_gold_min};"
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_REWARD_GOLD_MAX: u32 = {reward_gold_max};"
    )
    .unwrap();
    emit_attack(&mut output, "MOB_ATTACK", mob_attack);

    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").expect("Cargo sets OUT_DIR"));
    fs::write(out_dir.join("trusted_definitions.rs"), output)
        .unwrap_or_else(|error| fail(format!("cannot write generated Rust definitions ({error})")));
}
