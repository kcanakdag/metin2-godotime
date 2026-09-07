use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

const PROFILE: &str = "p0-warrior-dog";
const DEFINITIONS: &str = "content/p0-warrior-dog/actions.v1.json";
const TARGET_FIXTURE: &str = "fixtures/p2-target-dual-wild-dog.v1.json";
const TARGET_FIXTURE_ENV: &str = "MT2_COMBAT_TEST_FIXTURE";

#[derive(Clone, Copy)]
struct MonsterSpawn {
    id: u32,
    home_x: f32,
    home_z: f32,
}

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

fn selected_monster_spawns(mob_vnum: u32) -> (Vec<MonsterSpawn>, &'static str) {
    let selector = std::env::var(TARGET_FIXTURE_ENV).unwrap_or_default();
    if selector.is_empty() {
        let home = if std::env::var_os("CARGO_FEATURE_YONGAN").is_some() {
            (675.0, 575.0)
        } else {
            (3.0, 3.0)
        };
        return (
            vec![MonsterSpawn {
                id: 1,
                home_x: home.0,
                home_z: home.1,
            }],
            "",
        );
    }
    if selector != "dual-wild-dog-v1" {
        fail(format!(
            "{TARGET_FIXTURE_ENV} must be empty or exactly dual-wild-dog-v1"
        ));
    }
    if std::env::var_os("CARGO_FEATURE_YONGAN").is_some() {
        fail(
            "dual-wild-dog-v1 is a training-map-only test fixture and cannot be built with yongan",
        );
    }
    let bytes = fs::read(TARGET_FIXTURE)
        .unwrap_or_else(|error| fail(format!("cannot read {TARGET_FIXTURE} ({error})")));
    let payload: Value = serde_json::from_slice(&bytes)
        .unwrap_or_else(|error| fail(format!("{TARGET_FIXTURE} is not valid JSON ({error})")));
    let root = object(&payload, "combat_spawn_fixture");
    if text(root, "schema", "combat_spawn_fixture") != "mt2spacetime.combat-spawn-fixture"
        || u64_value(root, "schema_version", "combat_spawn_fixture") != 1
        || text(root, "fixture_id", "combat_spawn_fixture") != "dual-wild-dog-v1"
        || text(root, "map_id", "combat_spawn_fixture") != "training"
    {
        fail("combat spawn fixture schema, identity, or map does not match this server");
    }
    let placements = array(
        field(root, "placements", "combat_spawn_fixture"),
        "combat_spawn_fixture.placements",
    );
    if placements.len() != 2 {
        fail("dual-wild-dog-v1 must contain exactly two placements");
    }
    let expected = [(1_u32, 3.0_f32, 3.0_f32), (2, 10.0, 3.0)];
    let mut result = Vec::with_capacity(2);
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
        if (id, home_x, home_z) != expected || definition_vnum != mob_vnum {
            fail(format!(
                "combat spawn fixture placement {index} does not match the reviewed dual Wild Dog fixture"
            ));
        }
        result.push(MonsterSpawn { id, home_x, home_z });
    }
    (result, "training-v2-dual-wild-dog-v1")
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
    println!("cargo:rerun-if-changed={TARGET_FIXTURE}");
    println!("cargo:rerun-if-env-changed=MT2_PROGRESSION_BOOTSTRAP_IDENTITIES");
    println!("cargo:rerun-if-env-changed={TARGET_FIXTURE_ENV}");
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
        || u64_value(root, "schema_version", "root") != 2
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
    let progression = object(field(root, "progression", "root"), "progression");
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
    let warrior_strength = exact_u32(warrior, "strength", "warrior_initial", 6);
    let warrior_vitality = exact_u32(warrior, "vitality", "warrior_initial", 4);
    let warrior_dexterity = exact_u32(warrior, "dexterity", "warrior_initial", 3);
    let warrior_intelligence = exact_u32(warrior, "intelligence", "warrior_initial", 3);
    let base_max_hp = exact_u32(warrior, "base_max_hp", "warrior_initial", 600);
    let base_max_sp = exact_u32(warrior, "base_max_sp", "warrior_initial", 200);
    let hp_per_vitality = exact_u32(warrior, "hp_per_vitality", "warrior_initial", 40);
    let sp_per_intelligence = exact_u32(warrior, "sp_per_intelligence", "warrior_initial", 20);
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
    let (monster_spawns, combat_fixture_content_hash) = selected_monster_spawns(mob_vnum);

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
        "pub const DEFAULT_LEVEL_CAP: u8 = {default_level_cap};"
    )
    .unwrap();
    writeln!(output, "pub const SUPPORTED_CHARACTER_CLASS: u8 = 0;").unwrap();
    writeln!(output, "pub const SUPPORTED_SEX: u8 = 0;").unwrap();
    writeln!(
        output,
        "pub const WARRIOR_STRENGTH: u8 = {warrior_strength};"
    )
    .unwrap();
    writeln!(
        output,
        "pub const WARRIOR_VITALITY: u8 = {warrior_vitality};"
    )
    .unwrap();
    writeln!(
        output,
        "pub const WARRIOR_DEXTERITY: u8 = {warrior_dexterity};"
    )
    .unwrap();
    writeln!(
        output,
        "pub const WARRIOR_INTELLIGENCE: u8 = {warrior_intelligence};"
    )
    .unwrap();
    writeln!(output, "pub const BASE_MAX_HP: u32 = {base_max_hp};").unwrap();
    writeln!(output, "pub const BASE_MAX_SP: u32 = {base_max_sp};").unwrap();
    writeln!(
        output,
        "pub const HP_PER_VITALITY: u32 = {hp_per_vitality};"
    )
    .unwrap();
    writeln!(
        output,
        "pub const SP_PER_INTELLIGENCE: u32 = {sp_per_intelligence};"
    )
    .unwrap();
    writeln!(output, "pub const HP_PER_LEVEL_MIN: u32 = {};", hp_roll[0]).unwrap();
    writeln!(output, "pub const HP_PER_LEVEL_MAX: u32 = {};", hp_roll[1]).unwrap();
    writeln!(output, "pub const SP_PER_LEVEL_MIN: u32 = {};", sp_roll[0]).unwrap();
    writeln!(output, "pub const SP_PER_LEVEL_MAX: u32 = {};", sp_roll[1]).unwrap();
    writeln!(output, "pub const STAT_CAP: u8 = 90;").unwrap();
    writeln!(
        output,
        "pub const STAT_POINT_LAST_LEVEL_EXCLUSIVE: u8 = 91;"
    )
    .unwrap();
    writeln!(output, "pub const QUARTER_REWARD_COUNT: u16 = 2;").unwrap();
    writeln!(output, "pub const ITEM_STACK_LIMIT: u16 = 200;").unwrap();
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
    writeln!(
        output,
        "pub const COMBAT_FIXTURE_CONTENT_HASH: &str = {};",
        rust_string(combat_fixture_content_hash)
    )
    .unwrap();
    writeln!(
        output,
        "#[derive(Clone, Copy, Debug)]\npub struct MonsterSpawnDefinition {{ pub id: u32, pub home_x: f32, pub home_z: f32 }}"
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
            "\tMonsterSpawnDefinition {{ id: {}, home_x: {:?}, home_z: {:?} }},",
            spawn.id, spawn.home_x, spawn.home_z
        )
        .unwrap();
    }
    writeln!(output, "];").unwrap();

    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").expect("Cargo sets OUT_DIR"));
    fs::write(out_dir.join("trusted_definitions.rs"), output)
        .unwrap_or_else(|error| fail(format!("cannot write generated Rust definitions ({error})")));
}
