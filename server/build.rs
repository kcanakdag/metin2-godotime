use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

mod build_classes;
mod build_combo;
mod build_items;
mod build_npcs;
mod build_population;
mod build_regeneration;
mod build_skills;
mod build_training;
use build_combo::{
    ComboInput, MOB_ACTION_ID, PLAYER_COMBO_ACTION_IDS, PLAYER_GENERAL_ACTION_ID, RootMotion,
};
use build_population::MonsterSpawn;

const PROFILE: &str = "p0-warrior-dog";
const DEFINITIONS: &str = "content/p0-warrior-dog/actions.v1.json";
const COMBO_VALIDATOR: &str = "build_combo.rs";
const DUAL_TARGET_FIXTURE: &str = "fixtures/p2-target-dual-wild-dog.v1.json";
const REGENERATING_TARGET_FIXTURE: &str = "fixtures/p2-regenerating-wild-dog.v1.json";
const ALLOCATED_TARGET_FIXTURE: &str = "fixtures/p2-allocated-wild-dog.v1.json";
const PASSIVE_TARGET_FIXTURE: &str = "fixtures/p2-passive-wild-dog.v1.json";
const FINISHER_TARGET_FIXTURE: &str = "fixtures/p2-finisher-triple-wild-dog.v1.json";
const TARGET_FIXTURE_ENV: &str = "MT2_COMBAT_TEST_FIXTURE";

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

fn u32_from_value(value: &Value, label: &str) -> u32 {
    let value = value
        .as_u64()
        .unwrap_or_else(|| fail(format!("{label} must be an unsigned integer")));
    u32::try_from(value).unwrap_or_else(|_| fail(format!("{label} is outside u32")))
}

fn exact_u32(row: &Map<String, Value>, name: &str, label: &str, expected: u32) -> u32 {
    let value = u32_from_value(field(row, name, label), &format!("{label}.{name}"));
    if value != expected {
        fail(format!("{label}.{name} must be {expected}"));
    }
    value
}

fn exact_zero_i16(row: &Map<String, Value>, name: &str, label: &str) -> i16 {
    if field(row, name, label).as_i64() != Some(0) {
        fail(format!("{label}.{name} must be integer zero"));
    }
    0
}

fn exact_one_f32(row: &Map<String, Value>, name: &str, label: &str) -> f32 {
    let value = field(row, name, label)
        .as_f64()
        .unwrap_or_else(|| fail(format!("{label}.{name} must be a number")));
    let converted = value as f32;
    if converted.to_bits() != 1.0_f32.to_bits() || value != 1.0 {
        fail(format!("{label}.{name} must be exact binary32 1.0"));
    }
    converted
}

fn u32_array(value: &Value, label: &str, expected_len: usize) -> Vec<u32> {
    let values = array(value, label);
    if values.len() != expected_len {
        fail(format!("{label} must contain {expected_len} values"));
    }
    values
        .iter()
        .enumerate()
        .map(|(index, value)| u32_from_value(value, &format!("{label}[{index}]")))
        .collect()
}

fn emit_u32_array(output: &mut String, name: &str, values: &[u32]) {
    writeln!(output, "pub const {name}: [u32; {}] = [", values.len()).unwrap();
    for chunk in values.chunks(8) {
        writeln!(
            output,
            "\t{},",
            chunk
                .iter()
                .map(u32::to_string)
                .collect::<Vec<_>>()
                .join(", ")
        )
        .unwrap();
    }
    writeln!(output, "];").unwrap();
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
    ordinary_hit_invulnerability_us: i64,
    hit_start_us: i64,
    hit_end_us: i64,
    range_m: f32,
    combo_input: Option<ComboInput>,
    root_motion: Option<RootMotion>,
    special_area: bool,
    screen_wave: bool,
}

#[derive(Clone, Copy)]
struct AttackContract<'a> {
    actor_id: &'a str,
    mode: &'a str,
    action: &'a str,
    required_item: Option<u32>,
    combo_input: Option<ComboInput>,
    root_motion: Option<RootMotion>,
    special_area: bool,
    screen_wave: bool,
}

fn checked_attack<'a>(
    actions: &'a [Value],
    id: &'a str,
    contract: AttackContract<'_>,
) -> Attack<'a> {
    let row = action(actions, id);
    if text(row, "actor_id", "action") != contract.actor_id {
        fail(format!("action {id:?} belongs to the wrong actor"));
    }
    if text(row, "mode", "action") != contract.mode
        || text(row, "action", "action") != contract.action
    {
        fail(format!(
            "action {id:?} has an unexpected mode or action name"
        ));
    }
    let duration_us = bounded_u32(row, "duration_us", "action", 60_000_000) as i64;
    let cooldown_us = bounded_u32(row, "cooldown_us", "action", 60_000_000) as i64;
    let expected_invisible = match id {
        PLAYER_GENERAL_ACTION_ID => 500_000,
        value if value == PLAYER_COMBO_ACTION_IDS[0] => 100_000,
        value if value == PLAYER_COMBO_ACTION_IDS[1] => 100_000,
        value if value == PLAYER_COMBO_ACTION_IDS[2] => 200_000,
        value if value == PLAYER_COMBO_ACTION_IDS[3] => 0,
        MOB_ACTION_ID => 300_000,
        _ => fail("unsupported action id"),
    };
    if u64_value(row, "ordinary_hit_invulnerability_us", "action") != expected_invisible as u64 {
        fail(format!(
            "action {id:?} ordinary hit invulnerability changed"
        ));
    }
    let required = array(
        field(row, "required_item_vnums", "action"),
        "required_item_vnums",
    );
    let expected: Vec<u64> = contract.required_item.into_iter().map(u64::from).collect();
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
    let expected_windows = usize::from(!contract.special_area);
    if windows.len() != expected_windows {
        fail(format!(
            "action {id:?} has an unexpected ordinary hit-window count"
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
    let (hit_start_us, hit_end_us, range_m) = checked.first().copied().unwrap_or((0, 0, 0.0));
    if contract.special_area {
        let expected = json!({
            "authored_start_us": 659316,
            "legacy_dispatch_frame": 39,
            "activation_offset_us": 666667,
            "duration_us": 200000,
            "local_center_x_m": 0.0,
            "local_center_z_m": -1.2,
            "radius_m": 1.0,
            "max_targets": 16,
            "hit_once_per_life": true,
            "hit_type": 1,
            "invulnerability_us": 300000,
            "knockback": {
                "source_external_force": 17.0,
                "unobstructed_distance_m": 4.732,
                "duration_us": 1000000
            }
        });
        if row.get("special_area") != Some(&expected) {
            fail("terminal combo_4 special area changed");
        }
    } else if row.contains_key("special_area") {
        fail("only terminal combo_4 may define special_area");
    }
    if contract.screen_wave {
        let expected = json!({
            "authored_start_us": 630086,
            "legacy_dispatch_frame": 37,
            "activation_offset_us": 633334,
            "duration_us": 200000,
            "viewer_range_m": 2.0,
            "source_power": 300,
            "source_component_step_m": 0.001,
            "source_component_exclusive_max_m": 0.3
        });
        if row.get("screen_wave") != Some(&expected) {
            fail("terminal combo_4 screen wave changed");
        }
    } else if row.contains_key("screen_wave") {
        fail("only terminal combo_4 may define screen_wave");
    }
    Attack {
        id,
        duration_us,
        cooldown_us,
        ordinary_hit_invulnerability_us: expected_invisible,
        hit_start_us,
        hit_end_us,
        range_m,
        combo_input: contract.combo_input,
        root_motion: contract.root_motion,
        special_area: contract.special_area,
        screen_wave: contract.screen_wave,
    }
}

fn rust_string(value: &str) -> String {
    format!("{value:?}")
}

fn selected_monster_spawns(mob_vnum: u32) -> (Vec<MonsterSpawn>, &'static str) {
    let selector = std::env::var(TARGET_FIXTURE_ENV).unwrap_or_default();
    if selector.is_empty() {
        let (map_id, default_path) = if std::env::var_os("CARGO_FEATURE_YONGAN").is_some() {
            ("metin2_map_a1", "../content/worlds/yongan.population.json")
        } else {
            ("training", "../content/worlds/training.population.json")
        };
        let path = std::env::var("MT2_POPULATION_PROFILE").unwrap_or_else(|_| default_path.into());
        println!("cargo:rerun-if-changed={path}");
        let value: Value = serde_json::from_slice(
            &fs::read(&path)
                .unwrap_or_else(|error| fail(format!("Cannot read population {path}: {error}"))),
        )
        .unwrap_or_else(|error| fail(format!("Invalid population JSON: {error}")));
        return (
            build_population::parse(&value, map_id, &[mob_vnum])
                .unwrap_or_else(|error| fail(error)),
            "",
        );
    }
    if std::env::var_os("MT2_POPULATION_PROFILE").is_some() {
        fail("Population overrides cannot be combined with combat test fixtures");
    }
    if selector != "dual-wild-dog-v1"
        && selector != "triple-wild-dog-finisher-v1"
        && selector != "passive-wild-dog-v1"
        && selector != "allocated-wild-dog-v1"
        && selector != "regenerating-wild-dog-v1"
    {
        fail(format!(
            "{TARGET_FIXTURE_ENV} must be empty, dual-wild-dog-v1, triple-wild-dog-finisher-v1, passive-wild-dog-v1, allocated-wild-dog-v1, or regenerating-wild-dog-v1"
        ));
    }
    if std::env::var_os("CARGO_FEATURE_YONGAN").is_some() {
        fail("combat test fixtures are training-map-only and cannot be built with yongan");
    }
    let (fixture_path, expected): (&str, &[(u32, f32, f32)]) = if selector == "dual-wild-dog-v1" {
        (DUAL_TARGET_FIXTURE, &[(1, 3.0, 3.0), (2, 10.0, 3.0)])
    } else if selector == "regenerating-wild-dog-v1" {
        (
            REGENERATING_TARGET_FIXTURE,
            &[(1, 3.0, 3.0), (2, 10.0, 3.0)],
        )
    } else if selector == "allocated-wild-dog-v1" {
        (ALLOCATED_TARGET_FIXTURE, &[(1, 3.0, 3.0)])
    } else if selector == "passive-wild-dog-v1" {
        (PASSIVE_TARGET_FIXTURE, &[(1, 3.0, 3.0)])
    } else {
        (
            FINISHER_TARGET_FIXTURE,
            &[(1, 3.0, 3.0), (2, 3.25, 3.0), (3, 11.5, 3.0)],
        )
    };
    let bytes = fs::read(fixture_path)
        .unwrap_or_else(|error| fail(format!("cannot read {fixture_path} ({error})")));
    let payload: Value = serde_json::from_slice(&bytes)
        .unwrap_or_else(|error| fail(format!("{fixture_path} is not valid JSON ({error})")));
    let root = object(&payload, "combat_spawn_fixture");
    if text(root, "schema", "combat_spawn_fixture") != "mt2spacetime.combat-spawn-fixture"
        || u64_value(root, "schema_version", "combat_spawn_fixture") != 1
        || text(root, "fixture_id", "combat_spawn_fixture") != selector
        || text(root, "map_id", "combat_spawn_fixture") != "training"
    {
        fail("combat spawn fixture schema, identity, or map does not match this server");
    }
    let placements = array(
        field(root, "placements", "combat_spawn_fixture"),
        "combat_spawn_fixture.placements",
    );
    if placements.len() != expected.len() {
        fail("selected combat fixture has an unexpected placement count");
    }
    let mut result = Vec::with_capacity(expected.len());
    for (index, (value, expected)) in placements.iter().zip(expected).enumerate() {
        let row = object(value, "combat_spawn_fixture.placement");
        let id = bounded_u32(row, "id", "combat_spawn_fixture.placement", u32::MAX);
        let definition_vnum = bounded_u32(
            row,
            "definition_vnum",
            "combat_spawn_fixture.placement",
            u32::MAX,
        );
        let home_x = positive_f32(row, "home_x", "combat_spawn_fixture.placement");
        let home_z = positive_f32(row, "home_z", "combat_spawn_fixture.placement");
        if (id, home_x, home_z) != *expected || definition_vnum != mob_vnum {
            fail(format!(
                "combat spawn fixture placement {index} does not match the reviewed dual Wild Dog fixture"
            ));
        }
        result.push(MonsterSpawn {
            id,
            definition_vnum,
            home_x,
            home_z,
        });
    }
    let content_hash = if selector == "dual-wild-dog-v1" {
        "training-v2-dual-wild-dog-v1"
    } else if selector == "passive-wild-dog-v1" {
        "training-v4-passive-wild-dog-v1"
    } else if selector == "allocated-wild-dog-v1" {
        "training-v5-allocated-wild-dog-v1"
    } else if selector == "regenerating-wild-dog-v1" {
        "training-v6-regenerating-wild-dog-v1"
    } else {
        "training-v3-triple-wild-dog-finisher-v1"
    };
    (result, content_hash)
}

fn attack_expression(attack: Attack<'_>) -> String {
    let combo_input = match attack.combo_input {
        Some(combo) => format!(
            "Some(ComboInputDefinition {{ pre_input_us: {}, direct_input_us: {}, input_limit_us: {}, link_us: {} }})",
            combo.pre_input_us, combo.direct_input_us, combo.input_limit_us, combo.link_us
        ),
        None => "None".to_owned(),
    };
    let root_motion = match attack.root_motion {
        Some(root) => format!(
            "Some(RootMotionDefinition {{ endpoint_x_m: {:?}, endpoint_z_m: {:?}, duration_us: {} }})",
            root.endpoint_x_m, root.endpoint_z_m, root.duration_us
        ),
        None => "None".to_owned(),
    };
    let special_area = if attack.special_area {
        "Some(SpecialAreaDefinition { authored_start_us: 659316, legacy_dispatch_frame: 39, activation_offset_us: 666667, duration_us: 200000, local_center_x_m: 0.0, local_center_z_m: -1.2, radius_m: 1.0, max_targets: 16, hit_once_per_life: true, hit_type: 1, invulnerability_us: 300000, knockback: KnockbackDefinition { source_external_force: 17.0, unobstructed_distance_m: 4.732, duration_us: 1000000 } })"
    } else {
        "None"
    };
    let screen_wave = if attack.screen_wave {
        "Some(ScreenWaveDefinition { authored_start_us: 630086, legacy_dispatch_frame: 37, activation_offset_us: 633334, duration_us: 200000, viewer_range_m: 2.0, source_power: 300, source_component_step_m: 0.001, source_component_exclusive_max_m: 0.3 })"
    } else {
        "None"
    };
    format!(
        "AttackDefinition {{ id: {}, duration_us: {}, cooldown_us: {}, ordinary_hit_invulnerability_us: {}, hit_start_us: {}, hit_end_us: {}, range_m: {:?}, combo_input: {}, root_motion: {}, special_area: {}, screen_wave: {}, ordinary_knockback: None }}",
        rust_string(attack.id),
        attack.duration_us,
        attack.cooldown_us,
        attack.ordinary_hit_invulnerability_us,
        attack.hit_start_us,
        attack.hit_end_us,
        attack.range_m,
        combo_input,
        root_motion,
        special_area,
        screen_wave,
    )
}

fn emit_attack(output: &mut String, name: &str, attack: Attack<'_>) {
    writeln!(
        output,
        "pub const {name}: AttackDefinition = {};",
        attack_expression(attack),
    )
    .unwrap();
}

fn main() {
    println!("cargo:rerun-if-changed={DEFINITIONS}");
    println!("cargo:rerun-if-changed={COMBO_VALIDATOR}");
    println!("cargo:rerun-if-changed=build_items.rs");
    println!("cargo:rerun-if-changed=build_population.rs");
    println!("cargo:rerun-if-changed=build_regeneration.rs");
    println!("cargo:rerun-if-env-changed=MT2_POPULATION_PROFILE");
    println!("cargo:rerun-if-changed={DUAL_TARGET_FIXTURE}");
    println!("cargo:rerun-if-changed={PASSIVE_TARGET_FIXTURE}");
    println!("cargo:rerun-if-changed={ALLOCATED_TARGET_FIXTURE}");
    println!("cargo:rerun-if-changed={REGENERATING_TARGET_FIXTURE}");
    println!("cargo:rerun-if-changed={FINISHER_TARGET_FIXTURE}");
    println!("cargo:rerun-if-env-changed=MT2_PROGRESSION_BOOTSTRAP_IDENTITIES");
    println!("cargo:rerun-if-env-changed={TARGET_FIXTURE_ENV}");
    println!("cargo:rerun-if-env-changed=MT2_ITEM_TEST_FIXTURE");
    println!("cargo:rerun-if-env-changed=MT2_AUTH_ISSUER");
    println!("cargo:rerun-if-env-changed=MT2_ALLOW_GUESTS");
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
        || u64_value(root, "schema_version", "root") != 8
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
    let combo_actions = build_combo::validate(root).unwrap_or_else(|error| fail(error));
    if root.get("special_area_policy")
        != Some(&json!({
            "id": "legacy-60hz-fixed-sphere-once-per-life-v1",
            "dispatch_fps": 60,
            "activation_uses_frame_floor_then_next_tick": true,
            "sphere_space": "action-start-actor-local-to-world-at-activation",
            "victim_filter": "live-exact-life-same-map-attackable",
            "hit_once_scope": "area-instance-and-victim-life",
            "force_policy": "linear-unobstructed-distance-approx-v1",
            "legacy_physics_collision_parity": false
        }))
        || root.get("screen_wave_policy")
            != Some(&json!({
                "id": "legacy-60hz-viewer-range-metadata-v1",
                "dispatch_fps": 60,
                "activation_uses_frame_floor_then_next_tick": true,
                "camera_randomization_runtime_parity": false
            }))
        || root.get("defending_sphere_policy")
            != Some(&json!({
                "id": "static-full-3d-swept-sphere-v1",
                "source_collision_type": 3,
                "bone": "Bip01"
            }))
    {
        fail("Slice D event or defending-sphere policy changed");
    }
    let items = array(field(root, "items", "root"), "items");
    let progression = object(field(root, "progression", "root"), "progression");
    let physical = object(field(root, "physical_damage", "root"), "physical_damage");
    if physical.len() != 3 {
        fail("physical_damage must contain exactly policy, weapons, and mobs");
    }
    let policy = object(
        field(physical, "policy", "physical_damage"),
        "physical_damage.policy",
    );
    if text(policy, "formula_id", "physical_damage.policy") != "combat.physical.normal-melee.v1"
        || text(policy, "rating_policy_id", "physical_damage.policy")
            != "combat.attack-rating.attacker-level-victim-term.v1"
        || text(policy, "rng_policy_id", "physical_damage.policy")
            != "combat.rng.accepted-action-area-per-victim.v1"
    {
        fail("selected physical policy IDs changed");
    }
    let zero_fields = [
        "attack_grade_bonus",
        "party_attack_bonus",
        "attack_percent",
        "melee_magic_attack_percent",
        "defense_grade_bonus",
        "party_defender_bonus",
        "defense_percent",
        "npc_attacker_marriage_defense_bonus",
        "calc_att_bonus_percent",
        "block_percent",
        "normal_affect_damage",
        "reflect_percent",
        "critical_percent",
        "resist_critical_percent",
        "penetrate_percent",
        "resist_penetrate_percent",
        "hp_steal_percent",
        "sp_steal_percent",
        "gold_steal_percent",
        "hit_hp_recovery",
        "hit_sp_recovery",
        "mana_burn_percent",
        "normal_hit_damage_bonus_percent",
        "normal_hit_defense_bonus_percent",
    ];
    if policy.len() != 3 + zero_fields.len() + 2 {
        fail("selected physical policy fields changed");
    }
    for field_name in zero_fields {
        exact_zero_i16(policy, field_name, "physical_damage.policy");
    }
    let selected_final_multiplier =
        exact_one_f32(policy, "final_multiplier", "physical_damage.policy");
    if policy.get("sources")
        != Some(&json!([
            {
                "path": "src/game/src/battle.cpp",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "d30fd28ee37eb82d6a9fcb709cbcc9a2f01ccb05",
                "sha256": "5b8f66250b5ed7248c870540f9ffaa44813ce3c5a77d0d4b16f62e2659ac4521"
            },
            {
                "path": "src/game/src/char.cpp",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "ef6cd03e865dc66fe4c26a967ba81292c3c4b0d4",
                "sha256": "a34bf8a855d49ae488d16dd326f4b6aa69d65dfb5c327bd42264eb39aa633cbc"
            },
            {
                "path": "src/game/src/char_battle.cpp",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "799708a78195a7a30bf7ecfb0263dbb628de6f48",
                "sha256": "5d7e5bbd4da565fbe8c4ee873044748963846a6abfc224af8370c003b3a276d4"
            },
            {
                "path": "src/game/src/input_main.cpp",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "32fecde8b876ccad724efe46ddd42b478ec987ab",
                "sha256": "981b04aa02e27e6d1788824b263eb60cd834f72238694143a79b84a03d5fc59b"
            },
            {
                "path": "src/game/src/packet.h",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "46aa288727c1ad0bce11eca67b4f6a56af6d4e2b",
                "sha256": "ecb19942ed8a0fc19a1d7db0ad698edfbce51ae307efa60919d2872ab2d99b2f"
            }
        ]))
    {
        fail("selected physical source provenance changed");
    }
    let physical_weapons = array(
        field(physical, "weapons", "physical_damage"),
        "physical_damage.weapons",
    );
    if physical_weapons.len() != 1 {
        fail("physical_damage.weapons must contain exactly Sword+0");
    }
    let sword = object(&physical_weapons[0], "physical_damage.weapon");
    if sword.len() != 8
        || text(sword, "item_id", "physical_damage.weapon") != "item.weapon.sword-10"
        || exact_u32(sword, "vnum", "physical_damage.weapon", 10) != 10
        || text(sword, "class", "physical_damage.weapon") != "sword"
    {
        fail("selected Sword+0 identity or fields changed");
    }
    let sword_power_min = exact_u32(sword, "power_min", "physical_damage.weapon", 13) as u16;
    let sword_power_max = exact_u32(sword, "power_max", "physical_damage.weapon", 15) as u16;
    let sword_refine_attack = exact_u32(sword, "refine_attack", "physical_damage.weapon", 0) as u16;
    if sword_power_min > sword_power_max
        || sword.get("source")
            != Some(&json!({
                "path": "gamefiles/conf/item_proto.txt",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "f199abcc1077916c3496d84c58240cbc095ac033",
                "sha256": "b16190baa1b37425eb372339f81eb188e37ecd0bdb06530f0a9a63f0fb045292",
                "row_number": 4,
                "columns": {"power_min": "VALUE3", "power_max": "VALUE4", "refine_attack": "VALUE5"}
            }))
    {
        fail("selected Sword+0 range or provenance changed");
    }
    if sword.get("display_source")
        != Some(&json!({
            "path": "src/UserInterface/PythonPlayer.cpp",
            "revision": "bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7",
            "git_sha": "be48be6b4b8249bed84da70390b4e255b90170c1",
            "sha256": "cc9f8397642ea33f67c132e78516a5085cf5f2c6110bf15719a430330502ae71"
        }))
    {
        fail("selected Sword+0 display source provenance changed");
    }
    let physical_mobs = array(
        field(physical, "mobs", "physical_damage"),
        "physical_damage.mobs",
    );
    if physical_mobs.len() != 1 {
        fail("physical_damage.mobs must contain exactly Wild Dog 101");
    }
    let dog = object(&physical_mobs[0], "physical_damage.mob");
    if dog.len() != 13
        || text(dog, "actor_id", "physical_damage.mob") != "actor.mob.wild-dog-101"
        || exact_u32(dog, "vnum", "physical_damage.mob", 101) != 101
    {
        fail("selected Wild Dog identity or fields changed");
    }
    let dog_level = exact_u32(dog, "level", "physical_damage.mob", 1) as u8;
    let dog_strength = exact_u32(dog, "strength", "physical_damage.mob", 3) as u8;
    let dog_vitality = exact_u32(dog, "vitality", "physical_damage.mob", 5) as u8;
    let dog_dexterity = exact_u32(dog, "dexterity", "physical_damage.mob", 6) as u8;
    let dog_proto_defense = exact_u32(dog, "proto_defense", "physical_damage.mob", 4) as u16;
    let dog_power_min = exact_u32(dog, "power_min", "physical_damage.mob", 20) as u16;
    let dog_power_max = exact_u32(dog, "power_max", "physical_damage.mob", 24) as u16;
    let dog_damage_multiplier = exact_one_f32(dog, "damage_multiplier", "physical_damage.mob");
    let dog_sword_resistance =
        exact_u32(dog, "sword_resistance_percent", "physical_damage.mob", 0) as u8;
    let dog_fan_resistance =
        exact_u32(dog, "fan_resistance_percent", "physical_damage.mob", 0) as u8;
    if dog_power_min > dog_power_max
        || dog.get("source")
            != Some(&json!({
                "path": "gamefiles/conf/mob_proto.txt",
                "revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318",
                "git_sha": "002c00106dec10dcde3e8e292d6f1e242bf1c4d9",
                "sha256": "9aeb98db989ed64ec51dcd1e0df844d7cbd52004779747156017b1617c6be3fa",
                "row_number": 2,
                "columns": {
                    "level": "LEVEL", "strength": "ST", "vitality": "HT", "dexterity": "DX",
                    "proto_defense": "DEF", "power_min": "DAMAGE_MIN", "power_max": "DAMAGE_MAX",
                    "damage_multiplier": "DAM_MULTIPLY", "sword_resistance_percent": "RESIST_SWORD", "fan_resistance_percent": "RESIST_FAN"
                }
            }))
    {
        fail("selected Wild Dog range or provenance changed");
    }
    if text(progression, "schema", "progression") != "mt2spacetime.progression-definitions"
        || u64_value(progression, "schema_version", "progression") != 1
    {
        fail("progression schema does not match this server");
    }
    exact_u32(progression, "compiled_max_level", "progression", 120);
    let default_level_cap = exact_u32(progression, "default_level_cap", "progression", 99);
    let experience_table = u32_array(
        field(
            progression,
            "experience_to_next_level_by_current_level",
            "progression",
        ),
        "progression.experience_to_next_level_by_current_level",
        121,
    );
    if experience_table[0] != 0 || experience_table[1..].contains(&0) {
        fail("progression EXP table must be zero only at index 0");
    }
    let level_delta = u32_array(
        field(progression, "normal_level_delta_percent", "progression"),
        "progression.normal_level_delta_percent",
        31,
    );
    if level_delta.iter().any(|percent| *percent > 1000) {
        fail("progression normal level-delta percents must be in 0..=1000");
    }
    let quarter_rows = array(
        field(
            progression,
            "quarter_thresholds_by_current_level",
            "progression",
        ),
        "progression.quarter_thresholds_by_current_level",
    );
    if quarter_rows.len() != 121 {
        fail("progression quarter table must contain levels 0..120");
    }
    let mut quarter_thresholds: Vec<[u32; 4]> = Vec::with_capacity(121);
    for (level, value) in quarter_rows.iter().enumerate() {
        let row = object(value, "quarter_threshold");
        if u64_value(row, "level", "quarter_threshold") != level as u64
            || u32_from_value(
                field(row, "next_experience", "quarter_threshold"),
                "quarter_threshold.next_experience",
            ) != experience_table[level]
        {
            fail("progression quarter row level/EXP mismatch");
        }
        let thresholds = u32_array(
            field(row, "thresholds", "quarter_threshold"),
            "quarter_threshold.thresholds",
            4,
        );
        let experience = experience_table[level];
        let quarter = (experience as f32 / 4.0) as u32;
        let expected = [quarter, quarter * 2, quarter * 3, experience];
        if thresholds != expected {
            fail("progression quarter thresholds do not match the selected float32 formula");
        }
        quarter_thresholds.push(thresholds.try_into().expect("length checked"));
    }
    let warrior = object(
        field(progression, "warrior_initial", "progression"),
        "progression.warrior_initial",
    );
    exact_u32(warrior, "strength", "warrior_initial", 6);
    exact_u32(warrior, "vitality", "warrior_initial", 4);
    exact_u32(warrior, "dexterity", "warrior_initial", 3);
    exact_u32(warrior, "intelligence", "warrior_initial", 3);
    exact_u32(warrior, "base_max_hp", "warrior_initial", 600);
    exact_u32(warrior, "base_max_sp", "warrior_initial", 200);
    exact_u32(warrior, "hp_per_vitality", "warrior_initial", 40);
    exact_u32(warrior, "sp_per_intelligence", "warrior_initial", 20);
    let hp_roll = u32_array(
        field(warrior, "hp_per_level_inclusive", "warrior_initial"),
        "warrior_initial.hp_per_level_inclusive",
        2,
    );
    let sp_roll = u32_array(
        field(warrior, "sp_per_level_inclusive", "warrior_initial"),
        "warrior_initial.sp_per_level_inclusive",
        2,
    );
    if hp_roll != [36, 44] || sp_roll != [18, 22] {
        fail("selected Warrior random growth ranges changed");
    }
    exact_u32(warrior, "initial_max_hp", "warrior_initial", 760);
    exact_u32(warrior, "initial_max_sp", "warrior_initial", 260);
    let selected = object(
        field(progression, "selected_profile", "progression"),
        "progression.selected_profile",
    );
    let selected_constants = [
        ("supported_character_class", 0),
        ("supported_sex", 0),
        ("mob_exp_rate_percent", 100),
        ("stat_cap", 90),
        ("stat_point_last_level_exclusive", 91),
        ("low_level_death_loss_exclusive", 10),
        ("quarter_reward_count", 2),
        ("small_potion_vnum", 27001),
        ("medium_potion_vnum", 27002),
        ("small_potion_resulting_level_max", 10),
        ("item_stack_limit", 200),
        ("automatic_drop_reservation_us", 60_000_000),
        ("automatic_drop_expiry_us", 300_000_000),
        ("eligibility_distance_source_cm", 5000),
    ];
    for (name, expected) in selected_constants {
        exact_u32(selected, name, "progression.selected_profile", expected);
    }
    if text(
        selected,
        "selected_modifiers",
        "progression.selected_profile",
    ) != "all-zero-or-disabled"
    {
        fail("selected progression modifiers changed");
    }
    let monster_reward = object(
        field(progression, "monster_reward", "progression"),
        "progression.monster_reward",
    );
    exact_u32(monster_reward, "vnum", "progression.monster_reward", 101);
    let mob_level = exact_u32(monster_reward, "level", "progression.monster_reward", 1);
    let mob_experience = exact_u32(
        monster_reward,
        "experience",
        "progression.monster_reward",
        15,
    );
    let reward_items = array(
        field(progression, "reward_items", "progression"),
        "progression.reward_items",
    );
    if reward_items.len() != 2 {
        fail("progression must define exactly two quarter reward items");
    }
    for (index, expected_vnum, expected_name) in
        [(0, 27001, "Red Potion(S)"), (1, 27002, "Red Potion(M)")]
    {
        let row = object(&reward_items[index], "progression.reward_item");
        exact_u32(row, "vnum", "progression.reward_item", expected_vnum);
        exact_u32(row, "size", "progression.reward_item", 1);
        exact_u32(row, "stack_limit", "progression.reward_item", 200);
        if text(row, "source_name", "progression.reward_item") != expected_name {
            fail("progression reward item name changed");
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
    if player.contains_key("base_damage") {
        fail("legacy player.base_damage is forbidden in schema 6");
    }
    let player_cooldown = bounded_u32(player, "attack_cooldown_us", "player", 60_000_000) as i64;
    let player_range = positive_f32(player, "attack_range_m", "player");
    let primary = object(
        field(player, "primary_actions", "player"),
        "primary_actions",
    );
    let general_id = text(primary, "general", "primary_actions");
    let onehand_id = text(primary, "onehand", "primary_actions");
    if general_id != PLAYER_GENERAL_ACTION_ID || onehand_id != PLAYER_COMBO_ACTION_IDS[0] {
        fail("player primary actions do not match the selected fixture");
    }
    let general = checked_attack(
        actions,
        general_id,
        AttackContract {
            actor_id: player_id,
            mode: "general",
            action: "normal_attack",
            required_item: None,
            combo_input: None,
            root_motion: None,
            special_area: false,
            screen_wave: false,
        },
    );
    let combo_1 = checked_attack(
        actions,
        onehand_id,
        AttackContract {
            actor_id: player_id,
            mode: "onehand",
            action: "combo_1",
            required_item: Some(10),
            combo_input: combo_actions[0].combo_input,
            root_motion: Some(combo_actions[0].root_motion),
            special_area: false,
            screen_wave: false,
        },
    );
    let combo_2 = checked_attack(
        actions,
        PLAYER_COMBO_ACTION_IDS[1],
        AttackContract {
            actor_id: player_id,
            mode: "onehand",
            action: "combo_2",
            required_item: Some(10),
            combo_input: combo_actions[1].combo_input,
            root_motion: Some(combo_actions[1].root_motion),
            special_area: false,
            screen_wave: false,
        },
    );
    let combo_3 = checked_attack(
        actions,
        PLAYER_COMBO_ACTION_IDS[2],
        AttackContract {
            actor_id: player_id,
            mode: "onehand",
            action: "combo_3",
            required_item: Some(10),
            combo_input: combo_actions[2].combo_input,
            root_motion: Some(combo_actions[2].root_motion),
            special_area: false,
            screen_wave: false,
        },
    );
    let combo_4 = checked_attack(
        actions,
        PLAYER_COMBO_ACTION_IDS[3],
        AttackContract {
            actor_id: player_id,
            mode: "onehand",
            action: "combo_4",
            required_item: Some(10),
            combo_input: combo_actions[3].combo_input,
            root_motion: Some(combo_actions[3].root_motion),
            special_area: true,
            screen_wave: true,
        },
    );
    if general.cooldown_us != player_cooldown
        || combo_1.cooldown_us != player_cooldown
        || combo_2.cooldown_us != player_cooldown
        || combo_3.cooldown_us != player_cooldown
        || combo_4.cooldown_us != player_cooldown
        || general.range_m != player_range
        || combo_1.range_m != player_range
        || combo_2.range_m != player_range
        || combo_3.range_m != player_range
        || combo_4.range_m != 0.0
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
    if mob_action_id != MOB_ACTION_ID {
        fail("mob primary action does not match the selected fixture");
    }
    if mob.get("defending_sphere")
        != Some(&json!({
            "local_center_x_m": 0.0,
            "local_center_y_m": 0.8,
            "local_center_z_m": 0.1,
            "radius_m": 0.9
        }))
    {
        fail("Wild Dog defending sphere changed");
    }
    if mob.get("great_hit_reactions")
        != Some(&json!([
            {"id": "actor.mob.wild-dog-101.general.front_knockdown", "duration_us": 1166667},
            {"id": "actor.mob.wild-dog-101.general.front_standup", "duration_us": 1000000},
            {"id": "actor.mob.wild-dog-101.general.back_knockdown", "duration_us": 1166667}
        ]))
    {
        fail("Wild Dog GREAT hit reaction definitions changed");
    }
    let mob_attack = checked_attack(
        actions,
        mob_action_id,
        AttackContract {
            actor_id: mob_id,
            mode: "general",
            action: "normal_attack",
            required_item: None,
            combo_input: None,
            root_motion: None,
            special_area: false,
            screen_wave: false,
        },
    );
    if mob_attack.cooldown_us != bounded_u32(mob, "attack_cooldown_us", "mob", 60_000_000) as i64 {
        fail("mob action cooldown disagrees with the authoritative mob definition");
    }
    if mob_attack.range_m != positive_f32(mob, "attack_range_m", "mob") {
        fail("mob action range disagrees with the authoritative mob definition");
    }
    if mob.contains_key("damage_min") || mob.contains_key("damage_max") {
        fail("legacy mob damage_min/damage_max are forbidden in schema 6");
    }
    let reward_gold_min = bounded_u32(mob, "reward_gold_min", "mob", u32::MAX);
    let reward_gold_max = bounded_u32(mob, "reward_gold_max", "mob", u32::MAX);
    if reward_gold_min > reward_gold_max {
        fail("mob reward_gold_min exceeds reward_gold_max");
    }
    let (monster_spawns, combat_fixture_content_hash) = selected_monster_spawns(mob_vnum);

    let item = items
        .iter()
        .map(|value| object(value, "item"))
        .find(|row| u64_value(row, "vnum", "item") == 10)
        .unwrap_or_else(|| fail("starter sword vnum 10 is missing"));
    if item.contains_key("attack_bonus") {
        fail("legacy item attack_bonus is forbidden in schema 6");
    }
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
         pub struct ComboInputDefinition {\n\
         \tpub pre_input_us: i64,\n\
         \tpub direct_input_us: i64,\n\
         \tpub input_limit_us: i64,\n\
         \tpub link_us: i64,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct RootMotionDefinition {\n\
         \tpub endpoint_x_m: f64,\n\
         \tpub endpoint_z_m: f64,\n\
         \tpub duration_us: i64,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct KnockbackDefinition {\n\
         \tpub source_external_force: f64,\n\
         \tpub unobstructed_distance_m: f64,\n\
         \tpub duration_us: i64,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct SpecialAreaDefinition {\n\
         \tpub authored_start_us: i64,\n\
         \tpub legacy_dispatch_frame: u16,\n\
         \tpub activation_offset_us: i64,\n\
         \tpub duration_us: i64,\n\
         \tpub local_center_x_m: f64,\n\
         \tpub local_center_z_m: f64,\n\
         \tpub radius_m: f64,\n\
         \tpub max_targets: u8,\n\
         \tpub hit_once_per_life: bool,\n\
         \tpub hit_type: u8,\n\
         \tpub invulnerability_us: i64,\n\
         \tpub knockback: KnockbackDefinition,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct ScreenWaveDefinition {\n\
         \tpub authored_start_us: i64,\n\
         \tpub legacy_dispatch_frame: u16,\n\
         \tpub activation_offset_us: i64,\n\
         \tpub duration_us: i64,\n\
         \tpub viewer_range_m: f64,\n\
         \tpub source_power: u16,\n\
         \tpub source_component_step_m: f64,\n\
         \tpub source_component_exclusive_max_m: f64,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct MonsterReactionDefinition {\n\
         \tpub id: &'static str,\n\
         \tpub duration_us: i64,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct DefendingSphereDefinition {\n\
         \tpub local_center_x_m: f64,\n\
         \tpub local_center_y_m: f64,\n\
         \tpub local_center_z_m: f64,\n\
         \tpub radius_m: f64,\n\
         }\n\
         #[derive(Clone, Copy, Debug, PartialEq, Eq)]\n\
         pub enum PhysicalWeaponClass { Sword, Fan }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct WeaponPhysicalDefinition {\n\
         \tpub item_id: &'static str,\n\
         \tpub vnum: u32,\n\
         \tpub class: PhysicalWeaponClass,\n\
         \tpub power_min: u16,\n\
         \tpub power_max: u16,\n\
         \tpub refine_attack: u16,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct MobPhysicalDefinition {\n\
         \tpub actor_id: &'static str,\n\
         \tpub vnum: u32,\n\
         \tpub level: u8,\n\
         \tpub strength: u8,\n\
         \tpub vitality: u8,\n\
         \tpub dexterity: u8,\n\
         \tpub proto_defense: u16,\n\
         \tpub power_min: u16,\n\
         \tpub power_max: u16,\n\
         \tpub damage_multiplier: f32,\n\
         \tpub sword_resistance_percent: u8, pub fan_resistance_percent: u8, pub critical_percent: u8, pub penetrate_percent: u8,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct SelectedPhysicalPolicyDefinition {\n\
         \tpub formula_id: &'static str,\n\
         \tpub rating_policy_id: &'static str,\n\
         \tpub rng_policy_id: &'static str,\n\
         \tpub attack_grade_bonus: i16,\n\
         \tpub party_attack_bonus: i16,\n\
         \tpub attack_percent: i16,\n\
         \tpub melee_magic_attack_percent: i16,\n\
         \tpub defense_grade_bonus: i16,\n\
         \tpub party_defender_bonus: i16,\n\
         \tpub defense_percent: i16,\n\
         \tpub npc_attacker_marriage_defense_bonus: i16,\n\
         \tpub final_multiplier: f32,\n\
         \tpub calc_att_bonus_percent: i16,\n\
         \tpub block_percent: i16,\n\
         \tpub normal_affect_damage: i16,\n\
         \tpub reflect_percent: i16,\n\
         \tpub critical_percent: i16,\n\
         \tpub resist_critical_percent: i16,\n\
         \tpub penetrate_percent: i16,\n\
         \tpub resist_penetrate_percent: i16,\n\
         \tpub hp_steal_percent: i16,\n\
         \tpub sp_steal_percent: i16,\n\
         \tpub gold_steal_percent: i16,\n\
         \tpub hit_hp_recovery: i16,\n\
         \tpub hit_sp_recovery: i16,\n\
         \tpub mana_burn_percent: i16,\n\
         \tpub normal_hit_damage_bonus_percent: i16,\n\
         \tpub normal_hit_defense_bonus_percent: i16,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct AttackDefinition {\n\
         \tpub ordinary_knockback: Option<KnockbackDefinition>,\n\
         \tpub id: &'static str,\n\
         \tpub duration_us: i64,\n\
         \tpub cooldown_us: i64,\n\
         \tpub ordinary_hit_invulnerability_us: i64,\n\
         \tpub hit_start_us: i64,\n\
         \tpub hit_end_us: i64,\n\
         \tpub range_m: f32,\n\
         \tpub combo_input: Option<ComboInputDefinition>,\n\
         \tpub root_motion: Option<RootMotionDefinition>,\n\
         \tpub special_area: Option<SpecialAreaDefinition>,\n\
         \tpub screen_wave: Option<ScreenWaveDefinition>,\n\
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
        "pub const DEFAULT_LEVEL_CAP: u8 = {default_level_cap};"
    )
    .unwrap();
    writeln!(output, "pub const STAT_CAP: u8 = 90;").unwrap();
    writeln!(
        output,
        "pub const STAT_POINT_LAST_LEVEL_EXCLUSIVE: u8 = 91;"
    )
    .unwrap();
    writeln!(output, "pub const QUARTER_REWARD_COUNT: u16 = 2;").unwrap();
    writeln!(output, "pub const SMALL_POTION_VNUM: u32 = 27001;").unwrap();
    writeln!(output, "pub const MEDIUM_POTION_VNUM: u32 = 27002;").unwrap();
    writeln!(
        output,
        "pub const SMALL_POTION_RESULTING_LEVEL_MAX: u8 = 10;"
    )
    .unwrap();
    writeln!(
        output,
        "pub const AUTOMATIC_DROP_RESERVATION_US: i64 = 60_000_000;"
    )
    .unwrap();
    writeln!(
        output,
        "pub const AUTOMATIC_DROP_EXPIRY_US: i64 = 300_000_000;"
    )
    .unwrap();
    writeln!(output, "pub const EXP_ELIGIBILITY_DISTANCE_CM: i64 = 5000;").unwrap();
    writeln!(output, "pub const MOB_LEVEL: u8 = {mob_level};").unwrap();
    writeln!(output, "pub const MOB_EXPERIENCE: u32 = {mob_experience};").unwrap();
    emit_u32_array(&mut output, "EXPERIENCE_TABLE", &experience_table);
    emit_u32_array(&mut output, "NORMAL_LEVEL_DELTA_PERCENT", &level_delta);
    writeln!(output, "pub const QUARTER_THRESHOLDS: [[u32; 4]; 121] = [").unwrap();
    for thresholds in quarter_thresholds {
        writeln!(
            output,
            "\t[{}, {}, {}, {}],",
            thresholds[0], thresholds[1], thresholds[2], thresholds[3]
        )
        .unwrap();
    }
    writeln!(output, "];").unwrap();
    let bootstrap = std::env::var("MT2_PROGRESSION_BOOTSTRAP_IDENTITIES").unwrap_or_default();
    let mut bootstrap_identities = Vec::new();
    if !bootstrap.is_empty() {
        for (index, identity) in bootstrap.split(',').enumerate() {
            if identity.len() != 64
                || !identity
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            {
                fail(format!(
                    "MT2_PROGRESSION_BOOTSTRAP_IDENTITIES entry {index} must be canonical lowercase 64-hex"
                ));
            }
            if !bootstrap_identities
                .iter()
                .any(|existing| existing == identity)
            {
                bootstrap_identities.push(identity.to_owned());
            }
        }
    }
    bootstrap_identities.sort();
    writeln!(
        output,
        "pub const PROGRESSION_BOOTSTRAP_IDENTITIES: &[&str] = &["
    )
    .unwrap();
    for identity in bootstrap_identities {
        writeln!(output, "\t{},", rust_string(&identity)).unwrap();
    }
    writeln!(output, "];").unwrap();
    writeln!(output, "pub const SELECTED_PHYSICAL_POLICY: SelectedPhysicalPolicyDefinition = SelectedPhysicalPolicyDefinition {{ formula_id: {:?}, rating_policy_id: {:?}, rng_policy_id: {:?}, attack_grade_bonus: 0, party_attack_bonus: 0, attack_percent: 0, melee_magic_attack_percent: 0, defense_grade_bonus: 0, party_defender_bonus: 0, defense_percent: 0, npc_attacker_marriage_defense_bonus: 0, final_multiplier: {:?}, calc_att_bonus_percent: 0, block_percent: 0, normal_affect_damage: 0, reflect_percent: 0, critical_percent: 0, resist_critical_percent: 0, penetrate_percent: 0, resist_penetrate_percent: 0, hp_steal_percent: 0, sp_steal_percent: 0, gold_steal_percent: 0, hit_hp_recovery: 0, hit_sp_recovery: 0, mana_burn_percent: 0, normal_hit_damage_bonus_percent: 0, normal_hit_defense_bonus_percent: 0 }};", "combat.physical.normal-melee.v1", "combat.attack-rating.attacker-level-victim-term.v1", "combat.rng.accepted-action-area-per-victim.v1", selected_final_multiplier).unwrap();
    writeln!(output, "#[cfg(test)]\npub const SWORD_10_PHYSICAL: WeaponPhysicalDefinition = WeaponPhysicalDefinition {{ item_id: {:?}, vnum: 10, class: PhysicalWeaponClass::Sword, power_min: {sword_power_min}, power_max: {sword_power_max}, refine_attack: {sword_refine_attack} }};", "item.weapon.sword-10").unwrap();
    writeln!(output, "pub const WILD_DOG_101_PHYSICAL: MobPhysicalDefinition = MobPhysicalDefinition {{ actor_id: {:?}, vnum: 101, level: {dog_level}, strength: {dog_strength}, vitality: {dog_vitality}, dexterity: {dog_dexterity}, proto_defense: {dog_proto_defense}, power_min: {dog_power_min}, power_max: {dog_power_max}, damage_multiplier: {dog_damage_multiplier:?}, sword_resistance_percent: {dog_sword_resistance}, fan_resistance_percent: {dog_fan_resistance}, critical_percent: 0, penetrate_percent: 0 }};", "actor.mob.wild-dog-101").unwrap();
    output.push_str("pub const MOB_PHYSICAL_DEFINITIONS: &[MobPhysicalDefinition] = &[WILD_DOG_101_PHYSICAL];\n");
    emit_attack(&mut output, "PLAYER_GENERAL_ATTACK", general);
    writeln!(
        output,
        "pub const PLAYER_ONEHAND_COMBO: [AttackDefinition; 4] = ["
    )
    .unwrap();
    writeln!(output, "\t{},", attack_expression(combo_1)).unwrap();
    writeln!(output, "\t{},", attack_expression(combo_2)).unwrap();
    writeln!(output, "\t{},", attack_expression(combo_3)).unwrap();
    writeln!(output, "\t{},", attack_expression(combo_4)).unwrap();
    writeln!(output, "];").unwrap();
    writeln!(
        output,
        "pub const PLAYER_ONEHAND_ATTACK: AttackDefinition = PLAYER_ONEHAND_COMBO[0];"
    )
    .unwrap();
    writeln!(
        output,
        "#[cfg(test)]\npub const WEAPON_VNUM: u32 = SWORD_10_PHYSICAL.vnum;"
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_ACTOR_ID: &str = {};",
        rust_string(mob_id)
    )
    .unwrap();
    writeln!(output, "pub const MOB_VNUM: u32 = {mob_vnum};").unwrap();
    writeln!(output, "pub const MOB_STATIC_DEFENDING_SPHERE: DefendingSphereDefinition = DefendingSphereDefinition {{ local_center_x_m: 0.0, local_center_y_m: 0.8, local_center_z_m: 0.1, radius_m: 0.9 }};").unwrap();
    writeln!(output, "pub const MOB_GREAT_FRONT_KNOCKDOWN: MonsterReactionDefinition = MonsterReactionDefinition {{ id: {:?}, duration_us: 1166667 }};", "actor.mob.wild-dog-101.general.front_knockdown").unwrap();
    writeln!(output, "pub const MOB_GREAT_FRONT_STANDUP: MonsterReactionDefinition = MonsterReactionDefinition {{ id: {:?}, duration_us: 1000000 }};", "actor.mob.wild-dog-101.general.front_standup").unwrap();
    writeln!(output, "pub const MOB_GREAT_BACK_KNOCKDOWN: MonsterReactionDefinition = MonsterReactionDefinition {{ id: {:?}, duration_us: 1166667 }};", "actor.mob.wild-dog-101.general.back_knockdown").unwrap();
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
    writeln!(
        output,
        "pub const REGENERATING_MOB_FIXTURE: bool = {};",
        std::env::var(TARGET_FIXTURE_ENV).unwrap_or_default() == "regenerating-wild-dog-v1"
    )
    .unwrap();
    writeln!(
        output,
        "pub const ALLOCATED_MOB_FIXTURE: bool = {};",
        matches!(
            std::env::var(TARGET_FIXTURE_ENV)
                .unwrap_or_default()
                .as_str(),
            "allocated-wild-dog-v1" | "regenerating-wild-dog-v1"
        )
    )
    .unwrap();
    writeln!(
        output,
        "pub const MOB_PROXIMITY_AGGRESSION: bool = {};",
        std::env::var(TARGET_FIXTURE_ENV).unwrap_or_default() != "passive-wild-dog-v1"
    )
    .unwrap();
    output.push_str(
        r#"
#[derive(Clone, Copy, Debug)]
pub struct WeightedMobAttack { pub attack: AttackDefinition, pub weight: u8 }
#[derive(Clone, Copy, Debug)]
pub struct MobSpeciesDefinition {
    pub aggressive: bool,
    pub vnum: u32,
    pub actor_id: &'static str,
    pub name: &'static str,
    pub model_key: &'static str,
    pub motion_set: &'static str,
    pub level: u8,
    pub health: u16,
    pub attack_range_m: f32,
    pub move_speed_mps: f32,
    pub experience: u32,
    pub gold_min: u32,
    pub gold_max: u32,
    pub defending_sphere: DefendingSphereDefinition,
    pub front_knockdown: MonsterReactionDefinition,
    pub front_standup: MonsterReactionDefinition,
    pub back_knockdown: MonsterReactionDefinition,
}
#[derive(Clone, Copy, Debug)]
pub struct MobDefinition {
    pub species: MobSpeciesDefinition,
    pub damage_kind: crate::mob_damage::Kind,
    pub attacks: &'static [WeightedMobAttack],
    pub acquisition_range_m: f32,
    pub chase_home_range_m: f32,
    pub respawn_us: i64,
}
impl std::ops::Deref for MobDefinition {
    type Target = MobSpeciesDefinition;
    fn deref(&self) -> &Self::Target { &self.species }
}
pub const MOB_DEFINITIONS: &[MobDefinition] = &[MobDefinition {
    species: MobSpeciesDefinition {
        aggressive: MOB_PROXIMITY_AGGRESSION,
        vnum: MOB_VNUM, actor_id: MOB_ACTOR_ID, name: MOB_NAME,
        model_key: MOB_MODEL_KEY, motion_set: MOB_MOTION_SET,
        level: MOB_LEVEL, health: MOB_MAX_HEALTH,
        attack_range_m: MOB_ATTACK.range_m, move_speed_mps: MOB_MOVE_SPEED_MPS,
        experience: MOB_EXPERIENCE, gold_min: MOB_REWARD_GOLD_MIN, gold_max: MOB_REWARD_GOLD_MAX,
        defending_sphere: MOB_STATIC_DEFENDING_SPHERE,
        front_knockdown: MOB_GREAT_FRONT_KNOCKDOWN, front_standup: MOB_GREAT_FRONT_STANDUP,
        back_knockdown: MOB_GREAT_BACK_KNOCKDOWN,
    },
    damage_kind: crate::mob_damage::Kind::Normal,
    attacks: &[WeightedMobAttack { attack: MOB_ATTACK, weight: 100 }],
    acquisition_range_m: MOB_ACQUISITION_RANGE_M,
    chase_home_range_m: MOB_CHASE_HOME_RANGE_M, respawn_us: MOB_RESPAWN_US,
}];
"#,
    );
    writeln!(
        output,
        "pub const COMBAT_FIXTURE_CONTENT_HASH: &str = {};",
        rust_string(combat_fixture_content_hash)
    )
    .unwrap();
    writeln!(
        output,
        "#[derive(Clone, Copy, Debug)]\npub struct MonsterSpawnDefinition {{ pub id: u32, pub definition_vnum: u32, pub home_x: f32, pub home_z: f32 }}"
    )
    .unwrap();
    writeln!(
        output,
        "pub const MONSTER_SPAWNS: &[MonsterSpawnDefinition] = &["
    )
    .unwrap();
    for spawn in monster_spawns {
        writeln!(
            output,
            "\tMonsterSpawnDefinition {{ id: {}, definition_vnum: {}, home_x: {:?}, home_z: {:?} }},",
            spawn.id, spawn.definition_vnum, spawn.home_x, spawn.home_z
        )
        .unwrap();
    }
    writeln!(output, "];").unwrap();

    output.push_str("#[derive(Clone, Copy, Debug)]\npub struct RegenerationDefinition { pub id: u32, pub interval_us: i64, pub capacity: usize, pub startup_jitter_seconds: u8, pub templates: &'static [MonsterSpawnDefinition] }\n");
    if std::env::var(TARGET_FIXTURE_ENV).unwrap_or_default() == "regenerating-wild-dog-v1" {
        let payload: Value = serde_json::from_slice(
            &fs::read(REGENERATING_TARGET_FIXTURE).expect("regeneration fixture must exist"),
        )
        .expect("valid fixture JSON");
        let settings =
            build_regeneration::parse(&payload["regeneration"]).unwrap_or_else(|error| fail(error));
        let (id, interval, capacity, jitter) = (
            settings.id,
            settings.interval_us,
            settings.capacity,
            settings.startup_jitter_seconds,
        );
        writeln!(output, "pub const REGENERATION_DEFINITIONS: &[RegenerationDefinition] = &[RegenerationDefinition {{ id: {id}, interval_us: {interval}, capacity: {capacity}, startup_jitter_seconds: {jitter}, templates: MONSTER_SPAWNS }}];").unwrap();
    } else {
        output.push_str("pub const REGENERATION_DEFINITIONS: &[RegenerationDefinition] = &[];\n");
    }

    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").expect("Cargo sets OUT_DIR"));
    let item_fixture = build_items::recovery_fixture_enabled(
        &std::env::var("MT2_ITEM_TEST_FIXTURE").unwrap_or_default(),
        &std::env::var("MT2_AUTH_ISSUER").unwrap_or_default(),
        std::env::var_os("CARGO_FEATURE_YONGAN").is_some(),
        &std::env::var(TARGET_FIXTURE_ENV).unwrap_or_default(),
        std::env::var("MT2_ALLOW_GUESTS").is_ok_and(|value| value == "1"),
        &std::env::var("MT2_PROGRESSION_BOOTSTRAP_IDENTITIES").unwrap_or_default(),
    )
    .unwrap_or_else(|error| fail(error));
    writeln!(
        output,
        "pub const ITEM_RECOVERY_TEST_STARTER: bool = {item_fixture};"
    )
    .unwrap();
    output.push_str(
        &build_items::generate(field(root, "item_catalog", "root"))
            .unwrap_or_else(|error| fail(error)),
    );
    build_items::validate_links(&payload).unwrap_or_else(|error| fail(error));
    output.push_str(&build_npcs::build());
    output.push_str(&build_classes::build());
    output.push_str(&build_skills::build());
    output.push_str(&build_training::build());
    fs::write(out_dir.join("trusted_definitions.rs"), output)
        .unwrap_or_else(|error| fail(format!("cannot write generated Rust definitions ({error})")));
}
