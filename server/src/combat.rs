//! PvE actions, delayed hit windows, damage, death, respawn and rewards.
use crate::definitions::{self, AttackDefinition};
use crate::{
    Controller, active_controller, collision_bounds, content, controller, inventory, now_us, player,
};
use spacetimedb::rand::Rng;
use spacetimedb::{Identity, ReducerContext, Table};
use std::cmp::Ordering;

const PLAYER_RESPAWN_US: i64 = 8_000_000;
const LOOT_RESERVED_US: i64 = 10_000_000;
const LOOT_EXPIRES_US: i64 = 60_000_000;

fn within_reach(a: (f32, f32, f32), b: (f32, f32, f32), range: f32) -> bool {
    (a.0 - b.0).hypot(a.2 - b.2) <= range && (a.1 - b.1).abs() < 2.0
}

#[spacetimedb::table(accessor = monster, public)]
pub struct Monster {
    #[primary_key]
    pub id: u32,
    pub definition_vnum: u32,
    pub actor_id: String,
    pub name: String,
    pub model_key: String,
    pub motion_set: String,
    pub attack_action_id: String,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub heading: f32,
    pub health: u16,
    pub max_health: u16,
    pub activity: u8,
    pub attack_sequence: u32,
    pub life_sequence: u32,
    pub respawn_at_us: i64,
    pub action_started_at_us: i64,
    pub action_ends_at_us: i64,
}

#[spacetimedb::table(accessor = monster_clock)]
pub struct MonsterClock {
    #[primary_key]
    pub id: u32,
    pub next_attack_us: i64,
    pub attack_until_us: i64,
    pub pending_target: Identity,
    pub pending_target_generation: u32,
    pub pending_hit_at_us: i64,
    pub pending_hit_until_us: i64,
    pub pending_damage: u16,
}

#[spacetimedb::table(accessor = loot, public)]
pub struct Loot {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub gold: u32,
    pub owner: Identity,
    pub reserved_until_us: i64,
    pub expires_at_us: i64,
}

pub struct PlayerAttackPlan {
    pub definition: &'static AttackDefinition,
    pub target_id: u32,
    pub target_generation: u32,
    pub damage: u16,
    pub heading: Option<f32>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PendingPlayerHit {
    target_id: u32,
    target_generation: u32,
    damage: u16,
    range_m: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct PendingMonsterHit {
    target: Identity,
    target_generation: u32,
    damage: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum DueHitSource {
    Player(Identity),
    Monster(u32),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct DueHitEvent {
    hit_at_us: i64,
    source: DueHitSource,
}

fn compare_due_hits(left: &DueHitEvent, right: &DueHitEvent) -> Ordering {
    left.hit_at_us
        .cmp(&right.hit_at_us)
        .then_with(|| match (left.source, right.source) {
            // Preserve player-first behavior only for exactly equal source times,
            // then use stable public source identities to make iteration deterministic.
            (DueHitSource::Player(left), DueHitSource::Player(right)) => {
                left.to_string().cmp(&right.to_string())
            }
            (DueHitSource::Player(_), DueHitSource::Monster(_)) => Ordering::Less,
            (DueHitSource::Monster(_), DueHitSource::Player(_)) => Ordering::Greater,
            (DueHitSource::Monster(left), DueHitSource::Monster(right)) => left.cmp(&right),
        })
}

fn visit_due_hits(events: &mut [DueHitEvent], mut visit: impl FnMut(DueHitEvent)) {
    events.sort_by(compare_due_hits);
    for event in events.iter().copied() {
        visit(event);
    }
}

pub fn initialize(ctx: &ReducerContext) {
    ctx.db.monster().insert(fresh_monster(0, 0));
    ctx.db.monster_clock().insert(fresh_monster_clock());
}

fn fresh_monster(life_sequence: u32, attack_sequence: u32) -> Monster {
    let (x, z) = content::MONSTER_HOME;
    Monster {
        id: 1,
        definition_vnum: definitions::MOB_VNUM,
        actor_id: definitions::MOB_ACTOR_ID.into(),
        name: definitions::MOB_NAME.into(),
        model_key: definitions::MOB_MODEL_KEY.into(),
        motion_set: definitions::MOB_MOTION_SET.into(),
        attack_action_id: definitions::MOB_ATTACK.id.into(),
        x,
        y: content::height(x, z),
        z,
        heading: 0.0,
        health: definitions::MOB_MAX_HEALTH,
        max_health: definitions::MOB_MAX_HEALTH,
        activity: 0,
        attack_sequence,
        life_sequence,
        respawn_at_us: 0,
        action_started_at_us: 0,
        action_ends_at_us: 0,
    }
}

fn fresh_monster_clock() -> MonsterClock {
    MonsterClock {
        id: 1,
        next_attack_us: 0,
        attack_until_us: 0,
        pending_target: Identity::ZERO,
        pending_target_generation: 0,
        pending_hit_at_us: 0,
        pending_hit_until_us: 0,
        pending_damage: 0,
    }
}

pub fn plan_player_attack(ctx: &ReducerContext, character: Identity) -> PlayerAttackPlan {
    let definition = if inventory::equipped_weapon(ctx, character) == definitions::WEAPON_VNUM {
        &definitions::PLAYER_ONEHAND_ATTACK
    } else {
        &definitions::PLAYER_GENERAL_ATTACK
    };
    let damage =
        definitions::PLAYER_BASE_DAMAGE.saturating_add(inventory::weapon_bonus(ctx, character));
    let bounds = collision_bounds(ctx);
    let Some(player) = ctx.db.player().identity().find(character) else {
        return PlayerAttackPlan {
            definition,
            target_id: 0,
            target_generation: 0,
            damage,
            heading: None,
        };
    };
    let target = ctx
        .db
        .monster()
        .iter()
        .filter(|monster| monster.health > 0)
        .filter(|monster| {
            within_reach(
                (player.x, player.y, player.z),
                (monster.x, monster.y, monster.z),
                definition.range_m,
            )
        })
        .filter(|monster| content::clear_path(player.x, player.z, monster.x, monster.z, &bounds))
        .min_by(|a, b| {
            (a.x - player.x)
                .hypot(a.z - player.z)
                .total_cmp(&(b.x - player.x).hypot(b.z - player.z))
        });
    PlayerAttackPlan {
        definition,
        target_id: target.as_ref().map_or(0, |monster| monster.id),
        target_generation: target.as_ref().map_or(0, |monster| monster.life_sequence),
        damage,
        heading: target.map(|monster| (player.x - monster.x).atan2(player.z - monster.z)),
    }
}

pub fn take_due_player_hit(controller: &mut Controller, now: i64) -> Option<PendingPlayerHit> {
    if controller.pending_attack_hit_at_us == 0 || now < controller.pending_attack_hit_at_us {
        return None;
    }
    let still_valid = now <= controller.pending_attack_hit_until_us
        && now <= controller.attack_until_us
        && controller.pending_attack_target_id != 0;
    let hit = still_valid.then_some(PendingPlayerHit {
        target_id: controller.pending_attack_target_id,
        target_generation: controller.pending_attack_target_generation,
        damage: controller.pending_attack_damage,
        range_m: controller.pending_attack_range,
    });
    cancel_player_attack(controller);
    hit
}

pub fn cancel_player_attack(controller: &mut Controller) {
    controller.pending_attack_target_id = 0;
    controller.pending_attack_target_generation = 0;
    controller.pending_attack_hit_at_us = 0;
    controller.pending_attack_hit_until_us = 0;
    controller.pending_attack_damage = 0;
    controller.pending_attack_range = 0.0;
}

pub fn cancel_attacks_targeting(ctx: &ReducerContext, character: Identity) {
    for mut clock in ctx
        .db
        .monster_clock()
        .iter()
        .filter(|clock| clock.pending_target == character)
    {
        cancel_monster_hit(&mut clock);
        ctx.db.monster_clock().id().update(clock);
    }
}

/// Resolve every action that reached its source hit time before movement or AI.
/// Events contain only source keys; each resolver re-reads authoritative pending
/// state so an earlier death, leave, or kill can cancel a later copied event.
pub fn resolve_due_hits(ctx: &ReducerContext, now: i64) {
    let mut events: Vec<_> = ctx
        .db
        .controller()
        .iter()
        .filter(|controller| {
            controller.pending_attack_hit_at_us != 0 && now >= controller.pending_attack_hit_at_us
        })
        .map(|controller| DueHitEvent {
            hit_at_us: controller.pending_attack_hit_at_us,
            source: DueHitSource::Player(controller.identity),
        })
        .chain(
            ctx.db
                .monster_clock()
                .iter()
                .filter(|clock| clock.pending_hit_at_us != 0 && now >= clock.pending_hit_at_us)
                .map(|clock| DueHitEvent {
                    hit_at_us: clock.pending_hit_at_us,
                    source: DueHitSource::Monster(clock.id),
                }),
        )
        .collect();
    visit_due_hits(&mut events, |event| match event.source {
        DueHitSource::Player(character) => {
            resolve_due_player_event(ctx, character, event.hit_at_us, now)
        }
        DueHitSource::Monster(monster_id) => {
            resolve_due_monster_event(ctx, monster_id, event.hit_at_us, now)
        }
    });
}

fn resolve_due_player_event(
    ctx: &ReducerContext,
    character: Identity,
    expected_hit_at_us: i64,
    now: i64,
) {
    let Some(mut controller) = ctx.db.controller().identity().find(character) else {
        return;
    };
    if controller.pending_attack_hit_at_us != expected_hit_at_us || now < expected_hit_at_us {
        return;
    }
    let hit = take_due_player_hit(&mut controller, now);
    ctx.db.controller().identity().update(controller);
    if let Some(hit) = hit {
        resolve_player_hit(ctx, character, hit);
    }
}

fn resolve_due_monster_event(
    ctx: &ReducerContext,
    monster_id: u32,
    expected_hit_at_us: i64,
    now: i64,
) {
    let Some(mut clock) = ctx.db.monster_clock().id().find(monster_id) else {
        return;
    };
    if clock.pending_hit_at_us != expected_hit_at_us || now < expected_hit_at_us {
        return;
    }
    let hit = take_due_monster_hit(&mut clock, now);
    ctx.db.monster_clock().id().update(clock);
    if let Some(hit) = hit {
        resolve_monster_hit(ctx, monster_id, hit, now);
    }
}

pub fn resolve_player_hit(ctx: &ReducerContext, character: Identity, hit: PendingPlayerHit) {
    if hit.damage == 0 || hit.range_m <= 0.0 {
        return;
    }
    let Some(mut player) = ctx.db.player().identity().find(character) else {
        return;
    };
    let Some(mut monster) = ctx.db.monster().id().find(hit.target_id) else {
        return;
    };
    if !player.online
        || player.health == 0
        || monster.health == 0
        || monster.life_sequence != hit.target_generation
        || !within_reach(
            (player.x, player.y, player.z),
            (monster.x, monster.y, monster.z),
            hit.range_m,
        )
        || !content::clear_path(
            player.x,
            player.z,
            monster.x,
            monster.z,
            &collision_bounds(ctx),
        )
    {
        return;
    }
    player.heading = (player.x - monster.x).atan2(player.z - monster.z);
    ctx.db.player().identity().update(player);
    if apply_damage(&mut monster.health, hit.damage) {
        kill_monster(ctx, &mut monster, character);
    }
    ctx.db.monster().id().update(monster);
}

fn kill_monster(ctx: &ReducerContext, monster: &mut Monster, character: Identity) {
    let now = now_us(ctx);
    monster.activity = 3;
    monster.action_started_at_us = now;
    monster.respawn_at_us = now.saturating_add(definitions::MOB_RESPAWN_US);
    monster.action_ends_at_us = monster.respawn_at_us;
    if let Some(mut clock) = ctx.db.monster_clock().id().find(monster.id) {
        clock.attack_until_us = 0;
        cancel_monster_hit(&mut clock);
        ctx.db.monster_clock().id().update(clock);
    }
    inventory::drop_potion(ctx, character, monster.x, monster.y, monster.z);
    ctx.db.loot().insert(Loot {
        id: 0,
        x: monster.x,
        y: monster.y,
        z: monster.z,
        gold: roll_u32(
            ctx,
            definitions::MOB_REWARD_GOLD_MIN,
            definitions::MOB_REWARD_GOLD_MAX,
        ),
        owner: character,
        reserved_until_us: now.saturating_add(LOOT_RESERVED_US),
        expires_at_us: now.saturating_add(LOOT_EXPIRES_US),
    });
}

fn apply_damage(health: &mut u16, damage: u16) -> bool {
    if *health == 0 {
        return false;
    }
    *health = health.saturating_sub(damage);
    *health == 0
}

fn roll_u16(ctx: &ReducerContext, minimum: u16, maximum: u16) -> u16 {
    if minimum == maximum {
        minimum
    } else {
        ctx.rng().gen_range(minimum..=maximum)
    }
}

fn roll_u32(ctx: &ReducerContext, minimum: u32, maximum: u32) -> u32 {
    if minimum == maximum {
        minimum
    } else {
        ctx.rng().gen_range(minimum..=maximum)
    }
}

#[spacetimedb::reducer]
pub fn pickup_loot(ctx: &ReducerContext, id: u64) -> Result<(), String> {
    active_controller(ctx)?;
    let loot = ctx
        .db
        .loot()
        .id()
        .find(id)
        .ok_or("That loot has already been collected.")?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(crate::accounts::selected_character(ctx)?)
        .ok_or("Enter the world first.")?;
    let now = now_us(ctx);
    if now >= loot.expires_at_us {
        return Err("That loot has expired.".into());
    }
    if loot.owner != crate::accounts::selected_character(ctx)? && now < loot.reserved_until_us {
        return Err("That loot is reserved for its slayer.".into());
    }
    if !within_reach(
        (player.x, player.y, player.z),
        (loot.x, loot.y, loot.z),
        2.5,
    ) || !content::clear_path(player.x, player.z, loot.x, loot.z, &collision_bounds(ctx))
    {
        return Err("Move closer to collect that loot.".into());
    }
    player.gold = player
        .gold
        .checked_add(loot.gold)
        .ok_or("Gold limit reached.")?;
    ctx.db.player().identity().update(player);
    ctx.db.loot().id().delete(id);
    Ok(())
}

pub fn simulate(ctx: &ReducerContext, elapsed: f32) {
    let now = now_us(ctx);
    inventory::expire_drops(ctx);
    let bounds = collision_bounds(ctx);
    for loot in ctx.db.loot().iter() {
        if now >= loot.expires_at_us {
            ctx.db.loot().id().delete(loot.id);
        }
    }
    for mut player in ctx.db.player().iter() {
        if player.health == 0 && now >= player.respawn_at_us {
            player.health = player.max_health;
            player.life_sequence = player.life_sequence.wrapping_add(1);
            player.respawn_at_us = 0;
            player.activity = 0;
            player.action_started_at_us = 0;
            player.action_ends_at_us = 0;
            (player.x, player.z) = content::SPAWN;
            player.y = content::height(player.x, player.z);
            ctx.db.player().identity().update(player);
        }
    }
    for mut monster in ctx.db.monster().iter() {
        if monster.health == 0 {
            if now >= monster.respawn_at_us {
                let life_sequence = monster.life_sequence.wrapping_add(1);
                ctx.db
                    .monster()
                    .id()
                    .update(fresh_monster(life_sequence, monster.attack_sequence));
                ctx.db.monster_clock().id().update(fresh_monster_clock());
            }
            continue;
        }
        let mut clock = ctx
            .db
            .monster_clock()
            .id()
            .find(monster.id)
            .unwrap_or_else(fresh_monster_clock);
        let target = nearest_target(ctx, &monster, &bounds);
        let (tx, tz) = target
            .as_ref()
            .map(|player| (player.x, player.z))
            .unwrap_or(content::MONSTER_HOME);
        let distance = (tx - monster.x).hypot(tz - monster.z);
        monster.activity = 0;
        if now < clock.attack_until_us {
            monster.activity = 2;
        } else if let Some(player) = target.filter(|player| {
            within_reach(
                (monster.x, monster.y, monster.z),
                (player.x, player.y, player.z),
                definitions::MOB_ATTACK.range_m,
            )
        }) {
            monster.heading = (monster.x - player.x).atan2(monster.z - player.z);
            monster.action_started_at_us = 0;
            monster.action_ends_at_us = 0;
            if now >= clock.next_attack_us {
                schedule_monster_hit(
                    ctx,
                    &mut monster,
                    &mut clock,
                    player.identity,
                    player.life_sequence,
                    now,
                );
            }
        } else if distance > 0.1 {
            monster.action_started_at_us = 0;
            monster.action_ends_at_us = 0;
            let travel = (definitions::MOB_MOVE_SPEED_MPS * elapsed.clamp(0.0, 0.1)).min(distance);
            let (x, z) = content::slide(
                monster.x,
                monster.z,
                (tx - monster.x) / distance * travel,
                (tz - monster.z) / distance * travel,
                &bounds,
            );
            if (x - monster.x).hypot(z - monster.z) > 0.001 {
                monster.activity = 1;
                monster.heading = (monster.x - x).atan2(monster.z - z);
            }
            monster.x = x;
            monster.z = z;
            monster.y = content::height(x, z);
        } else {
            monster.action_started_at_us = 0;
            monster.action_ends_at_us = 0;
        }
        ctx.db.monster().id().update(monster);
        ctx.db.monster_clock().id().update(clock);
    }
}

fn nearest_target(
    ctx: &ReducerContext,
    monster: &Monster,
    bounds: &[crate::movement::Bounds],
) -> Option<crate::Player> {
    ctx.db
        .player()
        .iter()
        .filter(|player| player.online && player.health > 0)
        .filter(|player| {
            (player.x - content::MONSTER_HOME.0).hypot(player.z - content::MONSTER_HOME.1)
                < definitions::MOB_CHASE_HOME_RANGE_M
        })
        .filter(|player| {
            (player.x - monster.x).hypot(player.z - monster.z)
                < definitions::MOB_ACQUISITION_RANGE_M
        })
        .filter(|player| content::clear_path(monster.x, monster.z, player.x, player.z, bounds))
        .min_by(|a, b| {
            (a.x - monster.x)
                .hypot(a.z - monster.z)
                .total_cmp(&(b.x - monster.x).hypot(b.z - monster.z))
        })
}

fn schedule_monster_hit(
    ctx: &ReducerContext,
    monster: &mut Monster,
    clock: &mut MonsterClock,
    target: Identity,
    target_generation: u32,
    now: i64,
) {
    clock.next_attack_us = now.saturating_add(definitions::MOB_ATTACK.cooldown_us);
    clock.attack_until_us = now.saturating_add(definitions::MOB_ATTACK.duration_us);
    clock.pending_target = target;
    clock.pending_target_generation = target_generation;
    clock.pending_hit_at_us = now.saturating_add(definitions::MOB_ATTACK.hit_start_us);
    clock.pending_hit_until_us = now.saturating_add(definitions::MOB_ATTACK.hit_end_us);
    clock.pending_damage = roll_u16(
        ctx,
        definitions::MOB_DAMAGE_MIN,
        definitions::MOB_DAMAGE_MAX,
    );
    monster.attack_sequence = monster.attack_sequence.wrapping_add(1);
    monster.activity = 2;
    monster.action_started_at_us = now;
    monster.action_ends_at_us = clock.attack_until_us;
}

fn resolve_monster_hit(ctx: &ReducerContext, monster_id: u32, hit: PendingMonsterHit, now: i64) {
    let Some(monster) = ctx.db.monster().id().find(monster_id) else {
        return;
    };
    let Some(mut player) = ctx.db.player().identity().find(hit.target) else {
        return;
    };
    if monster.health == 0
        || !player.online
        || player.health == 0
        || player.life_sequence != hit.target_generation
        || !within_reach(
            (monster.x, monster.y, monster.z),
            (player.x, player.y, player.z),
            definitions::MOB_ATTACK.range_m,
        )
        || !content::clear_path(
            monster.x,
            monster.z,
            player.x,
            player.z,
            &collision_bounds(ctx),
        )
    {
        return;
    }
    if apply_damage(&mut player.health, hit.damage) {
        player.activity = 3;
        player.action_started_at_us = now;
        player.respawn_at_us = now.saturating_add(PLAYER_RESPAWN_US);
        player.action_ends_at_us = player.respawn_at_us;
        if let Some(mut controller) = ctx.db.controller().identity().find(player.identity) {
            controller.mode = 0;
            controller.direction_x = 0.0;
            controller.direction_z = 0.0;
            controller.attack_until_us = 0;
            cancel_player_attack(&mut controller);
            ctx.db.controller().identity().update(controller);
        }
    }
    ctx.db.player().identity().update(player);
}

fn take_due_monster_hit(clock: &mut MonsterClock, now: i64) -> Option<PendingMonsterHit> {
    if clock.pending_hit_at_us == 0 || now < clock.pending_hit_at_us {
        return None;
    }
    let valid_window = now <= clock.pending_hit_until_us && now <= clock.attack_until_us;
    let hit = valid_window.then_some(PendingMonsterHit {
        target: clock.pending_target,
        target_generation: clock.pending_target_generation,
        damage: clock.pending_damage,
    });
    cancel_monster_hit(clock);
    hit
}

fn cancel_monster_hit(clock: &mut MonsterClock) {
    clock.pending_target = Identity::ZERO;
    clock.pending_target_generation = 0;
    clock.pending_hit_at_us = 0;
    clock.pending_hit_until_us = 0;
    clock.pending_damage = 0;
}

#[cfg(test)]
mod tests {
    use super::*;
    use spacetimedb::ConnectionId;

    fn controller_with_hit(hit_at_us: i64, hit_until_us: i64) -> Controller {
        Controller {
            identity: Identity::ZERO,
            connection_id: ConnectionId::ZERO,
            direction_x: 0.0,
            direction_z: 0.0,
            target_x: 0.0,
            target_z: 0.0,
            mode: 0,
            last_input_us: 0,
            attack_until_us: 2_000_000,
            next_attack_us: 0,
            pending_attack_target_id: 7,
            pending_attack_target_generation: 11,
            pending_attack_hit_at_us: hit_at_us,
            pending_attack_hit_until_us: hit_until_us,
            pending_attack_damage: 35,
            pending_attack_range: 2.7,
            next_chat_us: 0,
        }
    }

    fn monster_clock_with_hit(hit_at_us: i64, hit_until_us: i64) -> MonsterClock {
        MonsterClock {
            id: 1,
            next_attack_us: 0,
            attack_until_us: 2_000_000,
            pending_target: Identity::from_claims("test", "target"),
            pending_target_generation: 4,
            pending_hit_at_us: hit_at_us,
            pending_hit_until_us: hit_until_us,
            pending_damage: 20,
        }
    }

    fn cross_side_lethal_outcome(player_hit_at_us: i64, monster_hit_at_us: i64) -> (bool, bool) {
        let player = Identity::from_claims("test", "player");
        let mut events = [
            DueHitEvent {
                hit_at_us: player_hit_at_us,
                source: DueHitSource::Player(player),
            },
            DueHitEvent {
                hit_at_us: monster_hit_at_us,
                source: DueHitSource::Monster(1),
            },
        ];
        let mut player_alive = true;
        let mut monster_alive = true;
        let mut player_pending = true;
        let mut monster_pending = true;
        visit_due_hits(&mut events, |event| match event.source {
            DueHitSource::Player(_) if player_pending && player_alive && monster_alive => {
                monster_alive = false;
                monster_pending = false;
            }
            DueHitSource::Monster(_) if monster_pending && monster_alive && player_alive => {
                player_alive = false;
                player_pending = false;
            }
            _ => {}
        });
        (player_alive, monster_alive)
    }

    #[test]
    fn melee_requires_horizontal_and_vertical_reach() {
        let origin = (660.0, 198.0, 575.0);
        assert!(within_reach(origin, (661.5, 199.9, 575.0), 1.9));
        assert!(!within_reach(origin, (662.0, 198.0, 575.0), 1.9));
        assert!(!within_reach(origin, (660.0, 200.0, 575.0), 1.9));
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            assert!(!within_reach(origin, (bad, 198.0, 575.0), 2.7));
            assert!(!within_reach(origin, (660.0, bad, 575.0), 2.7));
            assert!(!within_reach(origin, (660.0, 198.0, bad), 2.7));
        }
    }

    #[test]
    fn generated_timings_are_exact_selected_source_values() {
        assert_eq!(definitions::PLAYER_GENERAL_ATTACK.duration_us, 1_000_000);
        assert_eq!(definitions::PLAYER_GENERAL_ATTACK.cooldown_us, 850_000);
        assert_eq!(definitions::PLAYER_GENERAL_ATTACK.hit_start_us, 456_410);
        assert_eq!(definitions::PLAYER_GENERAL_ATTACK.hit_end_us, 597_436);
        assert_eq!(definitions::PLAYER_ONEHAND_ATTACK.hit_start_us, 192_308);
        assert_eq!(definitions::PLAYER_ONEHAND_ATTACK.hit_end_us, 315_385);
        assert_eq!(definitions::PLAYER_ONEHAND_ATTACK.cooldown_us, 850_000);
        assert_eq!(definitions::MOB_ATTACK.duration_us, 933_333);
        assert_eq!(definitions::MOB_ATTACK.cooldown_us, 1_300_000);
        assert_eq!(definitions::MOB_ATTACK.hit_start_us, 320_195);
        assert_eq!(definitions::MOB_ATTACK.hit_end_us, 492_782);
    }

    #[test]
    fn delayed_hit_is_taken_once_inside_the_window() {
        let mut controller = controller_with_hit(1_192_308, 1_315_385);
        assert_eq!(take_due_player_hit(&mut controller, 1_192_307), None);
        let hit = take_due_player_hit(&mut controller, 1_250_000).unwrap();
        assert_eq!(hit.target_id, 7);
        assert_eq!(hit.target_generation, 11);
        assert_eq!(hit.damage, 35);
        assert_eq!(take_due_player_hit(&mut controller, 1_300_000), None);
    }

    #[test]
    fn stale_or_cancelled_action_cannot_hit() {
        let mut stale = controller_with_hit(1_192_308, 1_315_385);
        assert_eq!(take_due_player_hit(&mut stale, 1_400_000), None);
        assert_eq!(take_due_player_hit(&mut stale, 1_500_000), None);
        let mut cancelled = controller_with_hit(1_192_308, 1_315_385);
        cancel_player_attack(&mut cancelled);
        assert_eq!(take_due_player_hit(&mut cancelled, 1_250_000), None);
    }

    #[test]
    fn monster_hit_is_consumed_once_and_expires_after_its_window() {
        let mut due = monster_clock_with_hit(1_320_195, 1_492_782);
        assert_eq!(take_due_monster_hit(&mut due, 1_320_194), None);
        let hit = take_due_monster_hit(&mut due, 1_400_000).unwrap();
        assert_eq!(hit.target_generation, 4);
        assert_eq!(hit.damage, 20);
        assert_eq!(take_due_monster_hit(&mut due, 1_450_000), None);

        let mut stale = monster_clock_with_hit(1_320_195, 1_492_782);
        assert_eq!(take_due_monster_hit(&mut stale, 2_100_000), None);
        assert_eq!(take_due_monster_hit(&mut stale, 2_200_000), None);
    }

    #[test]
    fn same_tick_cross_side_hits_resolve_by_source_time_and_cancel_later_hits() {
        // Both pairs are due on one 50 ms simulation boundary. The earlier
        // lethal event wins and cancels the other source's copied event.
        assert_eq!(
            cross_side_lethal_outcome(1_049_000, 1_020_000),
            (false, true)
        );
        assert_eq!(
            cross_side_lethal_outcome(1_020_000, 1_049_000),
            (true, false)
        );
    }

    #[test]
    fn exactly_equal_cross_side_hits_use_the_documented_player_first_tie_break() {
        assert_eq!(
            cross_side_lethal_outcome(1_025_000, 1_025_000),
            (true, false)
        );
    }

    #[test]
    fn lethal_damage_transitions_once_and_preserves_zero_health() {
        let mut health = 30;
        assert!(apply_damage(&mut health, 35));
        assert_eq!(health, 0);
        assert!(!apply_damage(&mut health, 35));
    }
}
