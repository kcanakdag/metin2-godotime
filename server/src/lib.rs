//! Authoritative shared development map for the Godot client.
mod accounts;
mod appearance;
mod combat;
mod content;
mod inventory;
mod movement;

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
    pub next_attack_us: i64,
    pub pending_attack_target_id: u32,
    pub pending_attack_target_generation: u32,
    pub pending_attack_hit_at_us: i64,
    pub pending_attack_hit_until_us: i64,
    pub pending_attack_damage: u16,
    pub pending_attack_range: f32,
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
        protocol_version: 4,
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
        content_hash: content::HASH.into(),
        definition_profile: definitions::PROFILE_ID.into(),
        definition_hash: definitions::DEFINITION_HASH.into(),
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
    for (index, (x, z, half_x, half_z, height, kind)) in [
        (-8.0, -5.0, 1.6, 1.3, 2.2, "stone"),
        (8.0, -5.0, 1.3, 1.7, 2.7, "stone"),
        (-11.0, 7.0, 3.0, 0.5, 1.2, "wall"),
        (11.0, 7.0, 3.0, 0.5, 1.2, "wall"),
        (0.0, -13.0, 2.0, 1.0, 3.8, "metin"),
    ]
    .into_iter()
    .enumerate()
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
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Select an existing character first.")?;
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
            next_attack_us: 0,
            pending_attack_target_id: 0,
            pending_attack_target_generation: 0,
            pending_attack_hit_at_us: 0,
            pending_attack_hit_until_us: 0,
            pending_attack_damage: 0,
            pending_attack_range: 0.0,
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
    controller.direction_x = direction_x;
    controller.direction_z = direction_z;
    controller.mode = u8::from(direction_x != 0.0 || direction_z != 0.0);
    controller.last_input_us = now_us(ctx);
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
    controller.target_x = x;
    controller.target_z = z;
    controller.mode = 2;
    controller.last_input_us = now_us(ctx);
    ctx.db.controller().identity().update(controller);
    Ok(())
}

#[spacetimedb::reducer]
pub fn stop_moving(ctx: &ReducerContext) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    controller.mode = 0;
    controller.direction_x = 0.0;
    controller.direction_z = 0.0;
    ctx.db.controller().identity().update(controller);
    Ok(())
}

#[spacetimedb::reducer]
pub fn perform_attack(ctx: &ReducerContext) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    let now = now_us(ctx);
    if now < controller.next_attack_us {
        return Err("Attack is cooling down.".into());
    }
    let character = accounts::selected_character(ctx)?;
    let plan = combat::plan_player_attack(ctx, character);
    controller.mode = 0;
    controller.direction_x = 0.0;
    controller.direction_z = 0.0;
    controller.attack_until_us = now.saturating_add(plan.definition.duration_us);
    controller.next_attack_us = now.saturating_add(plan.definition.cooldown_us);
    controller.pending_attack_target_id = plan.target_id;
    controller.pending_attack_target_generation = plan.target_generation;
    controller.pending_attack_hit_at_us = if plan.target_id == 0 {
        0
    } else {
        now.saturating_add(plan.definition.hit_start_us)
    };
    controller.pending_attack_hit_until_us = if plan.target_id == 0 {
        0
    } else {
        now.saturating_add(plan.definition.hit_end_us)
    };
    controller.pending_attack_damage = if plan.target_id == 0 { 0 } else { plan.damage };
    controller.pending_attack_range = if plan.target_id == 0 {
        0.0
    } else {
        plan.definition.range_m
    };
    ctx.db.controller().identity().update(controller);
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Enter the world first.")?;
    player.activity = 2;
    if let Some(heading) = plan.heading {
        player.heading = heading;
    }
    player.attack_sequence = player.attack_sequence.wrapping_add(1);
    player.attack_action_id = plan.definition.id.into();
    player.action_started_at_us = now;
    player.action_ends_at_us = now.saturating_add(plan.definition.duration_us);
    ctx.db.player().identity().update(player);
    Ok(())
}

#[spacetimedb::reducer]
pub fn send_chat(ctx: &ReducerContext, message: String) -> Result<(), String> {
    let mut controller = active_controller(ctx)?;
    let message = valid_chat(&message)?;
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
    let elapsed = (now_us(ctx) - clock.last_tick.to_micros_since_unix_epoch()) as f32 / 1_000_000.0;
    clock.last_tick = ctx.timestamp;
    ctx.db.simulation_clock().id().update(clock);
    combat::resolve_due_hits(ctx, now_us(ctx));
    let bounds = collision_bounds(ctx);
    for mut controller in ctx.db.controller().iter() {
        let Some(mut player) = ctx.db.player().identity().find(controller.identity) else {
            continue;
        };
        if !player.online || player.health == 0 {
            continue;
        }
        let before = (player.x, player.z, player.heading, player.activity);
        if now_us(ctx) < controller.attack_until_us {
            player.activity = 2;
        } else {
            player.action_started_at_us = 0;
            player.action_ends_at_us = 0;
            if controller.mode == 1 && now_us(ctx) - controller.last_input_us > INPUT_TIMEOUT_US {
                controller.mode = 0;
            }
            let (dx, dz) = match controller.mode {
                1 => step(controller.direction_x, controller.direction_z, elapsed)?,
                2 => movement::target_step(
                    player.x,
                    player.z,
                    controller.target_x,
                    controller.target_z,
                    elapsed,
                ),
                _ => (0.0, 0.0),
            };
            let (x, z) = content::slide(player.x, player.z, dx, dz, &bounds);
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
            if controller.mode == 2
                && (controller.target_x - x).hypot(controller.target_z - z) < 0.02
            {
                controller.mode = 0;
            }
        }
        if before != (player.x, player.z, player.heading, player.activity) {
            ctx.db.player().identity().update(player);
        }
        ctx.db.controller().identity().update(controller);
    }
    combat::simulate(ctx, elapsed);
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
}
