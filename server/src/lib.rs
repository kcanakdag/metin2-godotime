//! Authoritative shared development map for the Godot client.
mod accounts;
mod admin;
mod appearance;
mod area_lifecycle;
mod attack_timing;
mod characters;
mod charge_geometry;
pub mod charge_lifecycle;
mod charges;
mod combat;
mod combat_geometry;
mod combo;
mod content;
pub mod crush;
mod inventory;
mod item_catalog;
mod item_effects;
mod item_security;
mod knockback;
mod mob_actions;
mod mob_affects;
mod mob_aggro;
pub mod mob_damage;
mod mob_regeneration;
pub mod mob_threat;
mod monster_allocation;
mod monster_spawns;
mod movement;
pub mod npc_placement;
mod npc_spawns;
mod npcs;
mod physical_damage;
mod progression;
pub mod regeneration;
mod root_motion;
mod skill_area;
mod skill_hits;
mod skill_reactions;
mod skill_target;
mod skills;
mod training_targets;

const PROTOCOL_VERSION: u32 = 29;
mod special_area;
mod targeting;

mod selected_mobs {
    include!(concat!(env!("OUT_DIR"), "/selected_mobs.rs"));
}

mod definitions {
    include!(concat!(env!("OUT_DIR"), "/trusted_definitions.rs"));
}

use movement::{Bounds, HALF_SIZE, PLAYER_RADIUS, step, valid_direction};
use spacetimedb::{ConnectionId, Identity, ReducerContext, ScheduleAt, Table, Timestamp};
use std::time::Duration;

const TICK_MS: u32 = 50;
const INPUT_TIMEOUT_US: i64 = 600_000;

#[spacetimedb::table(accessor = player, public)]
pub struct Player {
    #[primary_key]
    pub identity: Identity,
    pub name: String,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub heading: f32,
    pub activity: u8,
    pub online: bool,
    pub attack_sequence: u32,
    pub attack_speed_percent: u16,
    pub life_sequence: u32,
    pub health: u16,
    pub max_health: u16,
    pub gold: u32,
    pub respawn_at_us: i64,
    pub attack_action_id: String,
    pub action_started_at_us: i64,
    pub action_ends_at_us: i64,
}

#[spacetimedb::table(accessor = obstacle, public)]
pub struct Obstacle {
    #[primary_key]
    pub id: u32,
    pub x: f32,
    pub z: f32,
    pub half_x: f32,
    pub half_z: f32,
    pub height: f32,
    pub kind: String,
}

#[spacetimedb::table(accessor = world_info, public)]
#[derive(PartialEq)]
pub struct WorldInfo {
    #[primary_key]
    pub id: u8,
    pub protocol_version: u32,
    pub npc_catalog_hash: String,
    pub mob_catalog_hash: String,
    pub character_catalog_hash: String,
    pub skill_catalog_hash: String,
    pub training_target_hash: String,
    pub map_name: String,
    pub map_id: String,
    pub content_hash: String,
    pub definition_profile: String,
    pub definition_hash: String,
    pub tick_ms: u32,
    pub half_size: f32,
}

#[spacetimedb::table(accessor = chat_message, public)]
pub struct ChatMessage {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub sender: Identity,
    pub name: String,
    pub message: String,
    pub sent_at: Timestamp,
}

#[spacetimedb::table(accessor = session)]
pub struct Session {
    #[primary_key]
    pub connection_id: ConnectionId,
    pub identity: Identity,
}

#[spacetimedb::table(accessor = controller)]
#[derive(Clone)]
pub struct Controller {
    #[primary_key]
    pub identity: Identity,
    pub connection_id: ConnectionId,
    pub direction_x: f32,
    pub direction_z: f32,
    pub target_x: f32,
    pub target_z: f32,
    /// 0: stopped, 1: held direction, 2: destination.
    pub mode: u8,
    pub last_input_us: i64,
    pub attack_until_us: i64,
    pub attack_speed_percent: u16,
    pub next_attack_us: i64,
    pub action_revision: u64,
    pub pending_attack_target_id: u32,
    pub pending_attack_target_generation: u32,
    pub pending_attack_source_generation: u32,
    pub pending_attack_hit_at_us: i64,
    pub pending_attack_hit_until_us: i64,
    pub pending_attack_damage: u16,
    pub pending_attack_range: f32,
    pub pending_attack_invulnerability_us: i64,
    pub pending_attack_target_revision: u64,
    pub pending_attack_can_select_target: bool,
    pub pending_attack_action_revision: u64,
    pub combat_target_id: u32,
    pub combat_target_life_sequence: u32,
    pub combat_target_change_not_before_us: i64,
    pub combat_target_revision: u64,
    /// 0: no combo; 1..=4: the bounded default one-hand chain.
    pub combo_step: u8,
    pub combo_chain_revision: u64,
    pub combo_action_started_at_us: i64,
    pub combo_action_ends_at_us: i64,
    pub combo_target_id: u32,
    pub combo_target_life_sequence: u32,
    pub combo_target_can_be_selected: bool,
    pub combo_equipped_item_id: u64,
    pub combo_equipped_vnum: u32,
    pub combo_link_queued: bool,
    pub combo_transition_boundary_us: i64,
    /// 0: no root displacement; otherwise one-based index in the selected combo prefix.
    pub root_motion_step: u8,
    pub root_motion_action_revision: u64,
    pub root_motion_started_at_us: i64,
    pub root_motion_consumed_elapsed_us: i64,
    pub root_motion_heading: f32,
    pub next_chat_us: i64,
}

#[spacetimedb::table(accessor = simulation_clock, public)]
pub struct SimulationClock {
    #[primary_key]
    pub id: u8,
    pub last_tick: Timestamp,
}

#[spacetimedb::table(accessor = tick_schedule, scheduled(simulate))]
pub struct TickSchedule {
    #[primary_key]
    #[auto_inc]
    pub scheduled_id: u64,
    pub scheduled_at: ScheduleAt,
}

fn compiled_world_info() -> WorldInfo {
    WorldInfo {
        id: 1,
        protocol_version: PROTOCOL_VERSION,
        npc_catalog_hash: definitions::NPC_CATALOG_HASH.into(),
        character_catalog_hash: definitions::CHARACTER_CATALOG_HASH.into(),
        skill_catalog_hash: definitions::SKILL_CATALOG_HASH.into(),
        training_target_hash: definitions::TRAINING_TARGET_HASH.into(),
        map_name: if content::YONGAN {
            "Yongan"
        } else {
            "Training Grounds"
        }
        .into(),
        map_id: if content::YONGAN {
            "metin2_map_a1"
        } else {
            "training"
        }
        .into(),
        tick_ms: TICK_MS,
        content_hash: if definitions::ITEM_RECOVERY_TEST_STARTER {
            "training-item-recovery-v1"
        } else if definitions::COMBAT_FIXTURE_CONTENT_HASH.is_empty() {
            content::HASH
        } else {
            definitions::COMBAT_FIXTURE_CONTENT_HASH
        }
        .into(),
        definition_profile: definitions::PROFILE_ID.into(),
        definition_hash: definitions::DEFINITION_HASH.into(),
        mob_catalog_hash: definitions::MOB_CATALOG_HASH.into(),
        half_size: HALF_SIZE,
    }
}

fn refresh_world_info(ctx: &ReducerContext) -> Result<(), String> {
    let compiled = compiled_world_info();
    if let Some(previous) = ctx.db.world_info().id().find(compiled.id) {
        if previous.map_id != compiled.map_id {
            return Err("Changing maps requires an explicit migration or a new database.".into());
        }
        if previous != compiled {
            ctx.db.world_info().id().update(compiled);
        }
    } else {
        ctx.db.world_info().insert(compiled);
    }
    Ok(())
}

#[spacetimedb::reducer(init)]
pub fn init(ctx: &ReducerContext) {
    ctx.db.world_info().insert(compiled_world_info());
    for (index, (x, z, half_x, half_z, height, kind)) in
        movement::TRAINING_OBSTACLES.iter().copied().enumerate()
    {
        if content::YONGAN {
            break;
        }
        ctx.db.obstacle().insert(Obstacle {
            id: index as u32 + 1,
            x,
            z,
            half_x,
            half_z,
            height,
            kind: kind.into(),
        });
    }
    ctx.db.simulation_clock().insert(SimulationClock {
        id: 1,
        last_tick: ctx.timestamp,
    });
    ctx.db.tick_schedule().insert(TickSchedule {
        scheduled_id: 0,
        scheduled_at: Duration::from_millis(u64::from(TICK_MS)).into(),
    });
    combat::initialize(ctx);
    npcs::validate_content();
    npc_spawns::validate_content();
    npc_spawns::maintain(ctx).expect("Initialize area NPC placement");
    admin::initialize();
}

#[spacetimedb::reducer(client_connected)]
pub fn client_connected(ctx: &ReducerContext) -> Result<(), String> {
    accounts::authorize_connection(ctx)?;
    let connection_id = ctx
        .connection_id()
        .ok_or("A WebSocket connection is required.")?;
    ctx.db.session().insert(Session {
        connection_id,
        identity: ctx.sender(),
    });
    Ok(())
}

#[spacetimedb::reducer(client_disconnected)]
pub fn client_disconnected(ctx: &ReducerContext) {
    let Some(connection_id) = ctx.connection_id() else {
        return;
    };
    ctx.db.session().connection_id().delete(connection_id);
    accounts::disconnected(ctx, connection_id);
}

#[spacetimedb::reducer]
pub fn enter_world(ctx: &ReducerContext, name: String) -> Result<(), String> {
    accounts::require_guest(ctx)?;
    let name = valid_name(&name)?;
    if ctx.db.player().identity().find(ctx.sender()).is_none() {
        accounts::unique_name(ctx, name)?;
        create_player(ctx, ctx.sender(), name, false);
    }
    accounts::ensure_guest_access(ctx, ctx.sender());
    enter_character(ctx, ctx.sender())
}

fn create_player(ctx: &ReducerContext, character: Identity, name: &str, online: bool) {
    let slot = ctx.db.player().count() % 32;
    let x = content::SPAWN.0 + (slot % 4) as f32 * 1.2;
    ctx.db.player().insert(Player {
        identity: character,
        name: name.into(),
        x,
        y: content::height(x, content::SPAWN.1),
        z: content::SPAWN.1,
        heading: 0.0,
        activity: 0,
        online,
        attack_sequence: 0,
        attack_speed_percent: 100,
        life_sequence: 0,
        health: 100,
        max_health: 100,
        gold: 0,
        respawn_at_us: 0,
        attack_action_id: String::new(),
        action_started_at_us: 0,
        action_ends_at_us: 0,
    });
}

fn enter_character(ctx: &ReducerContext, character: Identity) -> Result<(), String> {
    let connection_id = active_session(ctx)?;
    let previous_controller = ctx.db.controller().identity().find(character);
    if let Some(controller) = &previous_controller
        && controller.connection_id != connection_id
        && ctx
            .db
            .player()
            .identity()
            .find(character)
            .is_some_and(|player| player.online)
        && ctx
            .db
            .session()
            .connection_id()
            .find(controller.connection_id)
            .is_some()
    {
        return Err("This character is already playing in another connection.".into());
    }
    progression::rebuild_projection(ctx, character)?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Select an existing character first.")?;
    npcs::clear(ctx, character);
    player.online = true;
    player.activity = if player.health == 0 { 3 } else { 0 };
    ctx.db.player().identity().update(player);
    inventory::ensure_starter(ctx, character)?;
    appearance::sync(ctx, character);
    if let Some(mut controller) = previous_controller {
        controller.connection_id = connection_id;
        controller.direction_x = 0.0;
        controller.direction_z = 0.0;
        controller.mode = 0;
        controller.last_input_us = now_us(ctx);
        combo::clear_chain(&mut controller);
        root_motion::clear(&mut controller);
        special_area::clear(ctx, character);
        targeting::clear_character_target(ctx, &mut controller)
            .unwrap_or_else(|error| panic!("cannot clear re-entered character target: {error}"));
        ctx.db.controller().identity().update(controller);
    } else {
        ctx.db.controller().insert(Controller {
            identity: character,
            connection_id,
            direction_x: 0.0,
            direction_z: 0.0,
            target_x: 0.0,
            target_z: 0.0,
            mode: 0,
            last_input_us: now_us(ctx),
            attack_until_us: 0,
            attack_speed_percent: 100,
            next_attack_us: 0,
            action_revision: 0,
            pending_attack_target_id: 0,
            pending_attack_target_generation: 0,
            pending_attack_source_generation: 0,
            pending_attack_hit_at_us: 0,
            pending_attack_hit_until_us: 0,
            pending_attack_damage: 0,
            pending_attack_range: 0.0,
            pending_attack_invulnerability_us: 0,
            pending_attack_target_revision: 0,
            pending_attack_can_select_target: false,
            pending_attack_action_revision: 0,
            combat_target_id: 0,
            combat_target_life_sequence: 0,
            combat_target_change_not_before_us: 0,
            combat_target_revision: 0,
            combo_step: 0,
            combo_chain_revision: 0,
            combo_action_started_at_us: 0,
            combo_action_ends_at_us: 0,
            combo_target_id: 0,
            combo_target_life_sequence: 0,
            combo_target_can_be_selected: false,
            combo_equipped_item_id: 0,
            combo_equipped_vnum: 0,
            combo_link_queued: false,
            combo_transition_boundary_us: 0,
            root_motion_step: 0,
            root_motion_action_revision: 0,
            root_motion_started_at_us: 0,
            root_motion_consumed_elapsed_us: 0,
            root_motion_heading: 0.0,
            next_chat_us: 0,
        });
    }
    Ok(())
}

#[spacetimedb::reducer]
pub fn set_move_input(
    ctx: &ReducerContext,
    direction_x: f32,
    direction_z: f32,
) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    valid_direction(direction_x, direction_z)?;
    npcs::clear(ctx, controller.identity);
    controller.direction_x = direction_x;
    controller.direction_z = direction_z;
    controller.mode = u8::from(direction_x != 0.0 || direction_z != 0.0);
    controller.last_input_us = now_us(ctx);
    combo::cancel_queued_link(&mut controller);
    ctx.db.controller().identity().update(controller);
    Ok(())
}

#[spacetimedb::reducer]
pub fn move_to(ctx: &ReducerContext, x: f32, z: f32) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    content::valid_target(x, z)?;
    if collision_bounds(ctx)
        .iter()
        .any(|bounds| bounds.contains(x, z))
    {
        return Err("Destination is inside an obstacle.".into());
    }
    npcs::clear(ctx, controller.identity);
    controller.target_x = x;
    controller.target_z = z;
    controller.mode = 2;
    controller.last_input_us = now_us(ctx);
    combo::cancel_queued_link(&mut controller);
    ctx.db.controller().identity().update(controller);
    Ok(())
}

#[spacetimedb::reducer]
pub fn stop_moving(ctx: &ReducerContext) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    controller.mode = 0;
    controller.direction_x = 0.0;
    controller.direction_z = 0.0;
    combo::cancel_queued_link(&mut controller);
    ctx.db.controller().identity().update(controller);
    Ok(())
}

#[spacetimedb::reducer]
pub fn perform_attack(ctx: &ReducerContext) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    npcs::clear(ctx, controller.identity);
    let now = now_us(ctx);
    let character = accounts::selected_character(ctx)?;
    if combo::handle_follow_up(ctx, &mut controller, now)? {
        ctx.db.controller().identity().update(controller);
        return Ok(());
    }
    root_motion::advance_for_replacement(ctx, &mut controller, now)?;
    if now < controller.next_attack_us {
        return Err("Attack is cooling down.".into());
    }
    let plan = combat::plan_player_attack(ctx, character, &controller)?;
    let is_first_combo = characters::combo_start(plan.definition.id);
    let chain_target_id = plan.target_id;
    let chain_target_life_sequence = plan.target_generation;
    let chain_can_select_target = plan.can_select_target;
    let equipped = inventory::equipped_weapon_item(ctx, character);
    combat::start_player_action(ctx, &mut controller, plan, now)?;
    if is_first_combo {
        let (item_id, vnum) = equipped.ok_or("The equipped combo weapon is missing.")?;
        let action_ends_at_us = controller.attack_until_us;
        combo::begin_chain(
            &mut controller,
            combo::ChainStart {
                action_started_at_us: now,
                action_ends_at_us,
                target_id: chain_target_id,
                target_life_sequence: chain_target_life_sequence,
                target_can_be_selected: chain_can_select_target,
                equipped_item_id: item_id,
                equipped_vnum: vnum,
            },
        )?;
    } else {
        combo::clear_chain(&mut controller);
    }
    ctx.db.controller().identity().update(controller);
    Ok(())
}

#[spacetimedb::reducer]
pub fn send_chat(ctx: &ReducerContext, message: String) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    let message = valid_chat(&message)?;
    if message.starts_with('/') {
        return Err("Use the dedicated command controls for slash commands.".into());
    }
    if now_us(ctx) < controller.next_chat_us {
        return Err("Wait one second between messages.".into());
    }
    controller.next_chat_us = now_us(ctx).saturating_add(1_000_000);
    ctx.db.controller().identity().update(controller);
    let player = ctx
        .db
        .player()
        .identity()
        .find(accounts::selected_character(ctx)?)
        .ok_or("Enter the world first.")?;
    ctx.db.chat_message().insert(ChatMessage {
        id: 0,
        sender: accounts::selected_character(ctx)?,
        name: player.name,
        message: message.into(),
        sent_at: ctx.timestamp,
    });
    let mut ids: Vec<u64> = ctx.db.chat_message().iter().map(|row| row.id).collect();
    ids.sort_unstable();
    for id in ids.iter().take(ids.len().saturating_sub(100)) {
        ctx.db.chat_message().id().delete(*id);
    }
    Ok(())
}

#[spacetimedb::reducer]
pub fn simulate(ctx: &ReducerContext, _schedule: TickSchedule) -> Result<(), String> {
    if ctx.sender() != ctx.database_identity() {
        return Err("Only the database scheduler may advance the world.".into());
    }
    // 2.8.3 has no update lifecycle hook. Refresh static metadata after publication
    // from this existing authorized schedule, without resetting any gameplay tables.
    refresh_world_info(ctx)?;
    accounts::maintain(ctx);
    let mut clock = ctx
        .db
        .simulation_clock()
        .id()
        .find(1)
        .ok_or("Simulation clock is missing.")?;
    let previous_tick_us = clock.last_tick.to_micros_since_unix_epoch();
    let now = now_us(ctx);
    let elapsed = now.saturating_sub(previous_tick_us).max(0) as f32 / 1_000_000.0;
    clock.last_tick = ctx.timestamp;
    ctx.db.simulation_clock().id().update(clock);
    special_area::activate_due(ctx, now)?;
    skills::activate_due(ctx, now)?;
    root_motion::advance_all(ctx, now)?;
    combat::resolve_due_hits(ctx, now);
    knockback::advance_all(ctx, now)?;
    special_area::scan(ctx, now)?;
    skills::simulate(ctx, now)?;
    combo::resolve_due_transitions(ctx, now);
    let bounds = collision_bounds(ctx);
    for mut controller in ctx.db.controller().iter() {
        let Some(mut player) = ctx.db.player().identity().find(controller.identity) else {
            continue;
        };
        if !player.online || player.health == 0 {
            continue;
        }
        let before = (player.x, player.z, player.heading, player.activity);
        if now < controller.attack_until_us {
            player.activity = 2;
        } else {
            player.action_started_at_us = 0;
            player.action_ends_at_us = 0;
            let effect = charges::movement_effect(ctx, &controller, &player);
            apply_player_movement(
                &mut controller,
                &mut player,
                previous_tick_us,
                now,
                &bounds,
                effect,
            )?;
        }
        if before != (player.x, player.z, player.heading, player.activity) {
            ctx.db.player().identity().update(player);
        }
        ctx.db.controller().identity().update(controller);
    }
    charges::maintain(ctx, now);
    combat::simulate(ctx, elapsed)?;
    item_effects::simulate(ctx, now);
    npcs::maintain(ctx, now);
    npc_spawns::maintain(ctx)?;
    Ok(())
}

/// Account for ordinary travel before replacing its interval with an attack lock.
/// Callers commit the updated controller with the accepted attack; rejection rolls
/// back the root/movement update as part of the same reducer transaction.
pub(crate) fn advance_movement_for_attack(
    ctx: &ReducerContext,
    controller: &mut Controller,
    through_us: i64,
) -> Result<(), String> {
    let previous_us = ctx
        .db
        .simulation_clock()
        .id()
        .find(1)
        .ok_or("Simulation clock is missing")?
        .last_tick
        .to_micros_since_unix_epoch();
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(controller.identity)
        .ok_or("Enter the world first")?;
    if !player.online
        || player.health == 0
        || !accounts::controller_has_active_lease(ctx, controller)
    {
        return Err("Movement requires a living character and active controller lease".into());
    }
    let bounds = collision_bounds(ctx);
    let effect = charges::movement_effect(ctx, controller, &player);
    apply_player_movement(
        controller,
        &mut player,
        previous_us,
        through_us,
        &bounds,
        effect,
    )?;
    ctx.db.player().identity().update(player);
    Ok(())
}

fn apply_player_movement(
    controller: &mut Controller,
    player: &mut Player,
    previous_tick_us: i64,
    now: i64,
    bounds: &[Bounds],
    effect: Option<movement::SpeedEffect>,
) -> Result<(), String> {
    if controller.mode == 1 && now - controller.last_input_us > INPUT_TIMEOUT_US {
        controller.mode = 0;
    }
    let travel = movement::Travel::tick(
        previous_tick_us,
        now,
        controller.attack_until_us,
        movement::BASE_SPEED_POINTS,
        effect,
    )?;
    let (dx, dz) = match controller.mode {
        1 => step(controller.direction_x, controller.direction_z, travel)?,
        2 => movement::target_step(
            player.x,
            player.z,
            controller.target_x,
            controller.target_z,
            travel,
        ),
        _ => (0.0, 0.0),
    };
    let (x, z) = content::slide(player.x, player.z, dx, dz, bounds);
    let actual_x = x - player.x;
    let actual_z = z - player.z;
    player.activity = if actual_x.hypot(actual_z) > 0.00001 {
        1
    } else {
        0
    };
    if player.activity == 1 {
        player.heading = (-actual_x).atan2(-actual_z);
    }
    player.x = x;
    player.z = z;
    player.y = content::height(x, z);
    if controller.mode == 2 && (controller.target_x - x).hypot(controller.target_z - z) < 0.02 {
        controller.mode = 0;
    }
    Ok(())
}

fn now_us(ctx: &ReducerContext) -> i64 {
    ctx.timestamp.to_micros_since_unix_epoch()
}

fn active_session(ctx: &ReducerContext) -> Result<ConnectionId, String> {
    let connection_id = ctx
        .connection_id()
        .ok_or("Use an active WebSocket connection.")?;
    let session = ctx
        .db
        .session()
        .connection_id()
        .find(connection_id)
        .ok_or("Connection is not active.")?;
    if session.identity != ctx.sender() {
        return Err("Connection identity does not match.".into());
    }
    Ok(connection_id)
}

fn active_controller(ctx: &ReducerContext) -> Result<Controller, String> {
    let connection_id = active_session(ctx)?;
    let character = accounts::selected_character(ctx)?;
    let controller = ctx
        .db
        .controller()
        .identity()
        .find(character)
        .ok_or("Enter the world first.")?;
    if controller.connection_id != connection_id {
        return Err("This identity is controlled by another connection.".into());
    }
    if !ctx
        .db
        .player()
        .identity()
        .find(character)
        .is_some_and(|p| p.online)
    {
        return Err("Enter the world first.".into());
    }
    if ctx
        .db
        .player()
        .identity()
        .find(character)
        .is_some_and(|p| p.health == 0)
    {
        return Err("You are defeated. Wait for respawn.".into());
    }
    Ok(controller)
}

fn collision_bounds(ctx: &ReducerContext) -> Vec<Bounds> {
    ctx.db
        .obstacle()
        .iter()
        .map(|row| Bounds {
            min_x: row.x - row.half_x - PLAYER_RADIUS,
            max_x: row.x + row.half_x + PLAYER_RADIUS,
            min_z: row.z - row.half_z - PLAYER_RADIUS,
            max_z: row.z + row.half_z + PLAYER_RADIUS,
        })
        .collect()
}

fn valid_name(name: &str) -> Result<&str, String> {
    let name = name.trim();
    if !(2..=16).contains(&name.chars().count())
        || !name.chars().all(|c| c.is_alphanumeric() || c == '_')
    {
        return Err("Use 2–16 letters, digits, or underscores.".into());
    }
    Ok(name)
}

fn valid_chat(message: &str) -> Result<&str, String> {
    let message = message.trim();
    if message.is_empty() || message.chars().count() > 160 || message.chars().any(char::is_control)
    {
        return Err("Use 1–160 printable characters.".into());
    }
    Ok(message)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names_are_bounded_and_trimmed() {
        assert_eq!(valid_name("  Warrior_2  ").unwrap(), "Warrior_2");
        for name in ["", "a", "a b", "a\nb", "<script>", "abcdefghijklmnopq"] {
            assert!(valid_name(name).is_err(), "{name:?}");
        }
        assert_eq!(valid_name("Savaşçı").unwrap(), "Savaşçı");
    }
    #[test]
    fn chat_rejects_control_characters_and_oversize_messages() {
        assert_eq!(valid_chat(" hello ").unwrap(), "hello");
        for message in ["", "  ", "hello\nworld", "hello\0world"] {
            assert!(valid_chat(message).is_err());
        }
        assert!(valid_chat(&"x".repeat(161)).is_err());
        assert!(valid_chat(&"ş".repeat(160)).is_ok());
    }

    #[test]
    fn ordinary_movement_uses_only_the_tick_remainder_after_attack() {
        let previous = 1_000_000;
        let now = previous + 50_000;
        let displacement = |previous, now, blocked| {
            step(
                1.0,
                0.0,
                movement::Travel::tick(previous, now, blocked, movement::BASE_SPEED_POINTS, None)
                    .unwrap(),
            )
            .unwrap()
            .0
        };
        assert_eq!(displacement(previous, now, previous), 0.25);
        assert_eq!(displacement(previous, now, previous + 25_000), 0.125);
        assert_eq!(displacement(previous, now, now), 0.0);
        assert_eq!(displacement(previous, now, now + 25_000), 0.0);
        assert_eq!(displacement(now, previous, previous), 0.0);
        assert_eq!(displacement(previous, previous + 1_000_000, previous), 0.5);
    }
}
