//! PvE actions, delayed hit windows, damage, death, respawn and rewards.
use crate::definitions::{self, AttackDefinition, MonsterSpawnDefinition};
use crate::progression::{self, character_progression};
use crate::{
    Controller, active_controller, collision_bounds, content, controller, inventory, now_us,
    player, session,
};
use spacetimedb::rand::Rng;
use spacetimedb::{ConnectionId, Identity, ReducerContext, Table};
use std::cmp::Ordering;

const PLAYER_RESPAWN_US: i64 = 8_000_000;
const LOOT_RESERVED_US: i64 = 10_000_000;
const LOOT_EXPIRES_US: i64 = 60_000_000;

fn within_reach(a: (f32, f32, f32), b: (f32, f32, f32), range: f32) -> bool {
    (a.0 - b.0).hypot(a.2 - b.2) <= range && (a.1 - b.1).abs() < 2.0
}

#[spacetimedb::table(accessor = monster, public)]
#[derive(Clone, PartialEq)]
pub struct Monster {
    #[primary_key]
    pub id: u32,
    pub definition_vnum: u32,
    pub actor_id: String,
    pub name: String,
    pub level: u8,
    pub model_key: String,
    pub motion_set: String,
    pub attack_action_id: String,
    pub attack_target: Identity,
    pub attack_target_life_sequence: u32,
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
#[derive(Clone, PartialEq)]
pub struct MonsterClock {
    #[primary_key]
    pub id: u32,
    pub home_x: f32,
    pub home_z: f32,
    pub next_attack_us: i64,
    pub attack_until_us: i64,
    pub pending_target: Identity,
    pub pending_target_generation: u32,
    pub pending_source_generation: u32,
    pub pending_hit_at_us: i64,
    pub pending_hit_until_us: i64,
    pub area_invulnerable_until_us: i64,
}

#[spacetimedb::table(accessor = monster_damage)]
#[derive(Clone)]
pub struct MonsterDamage {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub monster_id: u32,
    pub monster_life_sequence: u32,
    pub character_id: Identity,
    pub controller_connection_id: ConnectionId,
    pub registered_damage: u32,
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
    pub heading: Option<f32>,
    pub can_select_target: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PendingPlayerHit {
    action_revision: u64,
    target_id: u32,
    target_generation: u32,
    source_generation: u32,
    damage: u16,
    range_m: f32,
    invulnerability_us: i64,
    target_revision: u64,
    can_select_target: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct PendingMonsterHit {
    target: Identity,
    target_generation: u32,
    source_generation: u32,
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
    action_revision: u64,
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

fn exact_hit_generations_match(
    captured_source: u32,
    current_source: u32,
    captured_target: u32,
    current_target: u32,
) -> bool {
    captured_source == current_source && captured_target == current_target
}

fn visit_due_hits(events: &mut [DueHitEvent], mut visit: impl FnMut(DueHitEvent)) {
    events.sort_by(compare_due_hits);
    for event in events.iter().copied() {
        visit(event);
    }
}

pub fn initialize(ctx: &ReducerContext) {
    crate::monster_spawns::initialize(ctx);
    let bounds = collision_bounds(ctx);
    let ordinary = if definitions::REGENERATING_MOB_FIXTURE {
        Vec::new()
    } else if definitions::ALLOCATED_MOB_FIXTURE {
        crate::monster_spawns::allocate_group(ctx, definitions::MONSTER_SPAWNS, 0)
            .expect("trusted training group allocation must succeed")
    } else {
        definitions::MONSTER_SPAWNS.to_vec()
    };
    for spawn in ordinary.iter().chain(definitions::TRAINING_TARGET_SPAWNS) {
        content::valid_spawn(spawn.home_x, spawn.home_z)
            .expect("Authored monster home must be traversable on the compiled map");
        assert!(
            !bounds
                .iter()
                .any(|bound| bound.contains(spawn.home_x, spawn.home_z)),
            "Authored monster home intersects a training obstacle"
        );
        ctx.db.monster().insert(fresh_monster(*spawn, 0, 0));
        ctx.db.monster_clock().insert(fresh_monster_clock(*spawn));
    }
    crate::mob_regeneration::initialize(ctx).expect("regeneration initialization must succeed");
}

pub(crate) fn insert_allocated_monster(
    ctx: &ReducerContext,
    spawn: MonsterSpawnDefinition,
    heading: f32,
) {
    let mut monster = fresh_monster(spawn, 0, 0);
    monster.heading = heading;
    ctx.db.monster().insert(monster);
    ctx.db.monster_clock().insert(fresh_monster_clock(spawn));
}

/// Resolve private origin before validating public combat state.
pub(crate) fn validate_monster(
    ctx: &ReducerContext,
    monster: &Monster,
) -> Result<MonsterSpawnDefinition, String> {
    let spawn = crate::monster_spawns::resolve(ctx, monster.id)?;
    validate_monster_at(monster, spawn)?;
    Ok(spawn)
}

fn validate_monster_at(monster: &Monster, spawn: MonsterSpawnDefinition) -> Result<(), String> {
    let authored = crate::training_targets::validate(monster)?;
    let supported = authored.is_some()
        || mob_definition(monster.definition_vnum).is_some_and(|d| {
            monster.actor_id == d.actor_id
                && d.immunity_flags & !0x7f == 0
                && monster.level == d.level
                && monster.max_health == d.health
                && monster.model_key == d.model_key
                && monster.motion_set == d.motion_set
        });
    if !supported
        || spawn.id != monster.id
        || spawn.definition_vnum != monster.definition_vnum
        || monster.health > monster.max_health
        || !monster.x.is_finite()
        || !monster.y.is_finite()
        || !monster.z.is_finite()
        || !monster.heading.is_finite()
    {
        return Err("Combat actor differs from its trusted world definition".into());
    }
    Ok(())
}

fn mob_definition(vnum: u32) -> Option<&'static definitions::MobDefinition> {
    definitions::MOB_DEFINITIONS.iter().find(|d| d.vnum == vnum)
}

pub(crate) fn ordinary_definition(
    ctx: &ReducerContext,
    monster: &Monster,
) -> Result<&'static definitions::MobDefinition, String> {
    validate_monster(ctx, monster)?;
    mob_definition(monster.definition_vnum).ok_or("No ordinary mob definition for actor".into())
}

pub(crate) fn defending_sphere(
    ctx: &ReducerContext,
    monster: &Monster,
) -> definitions::DefendingSphereDefinition {
    if let Some(d) = crate::training_targets::definition(monster.id) {
        definitions::DefendingSphereDefinition {
            local_center_x_m: 0.0,
            local_center_y_m: d.hit_center_y_m,
            local_center_z_m: 0.0,
            radius_m: d.hit_radius_m,
        }
    } else {
        ordinary_definition(ctx, monster)
            .expect("defending monster must have a trusted definition")
            .defending_sphere
    }
}

fn fresh_monster(
    spawn: MonsterSpawnDefinition,
    life_sequence: u32,
    attack_sequence: u32,
) -> Monster {
    let x = spawn.home_x;
    let z = spawn.home_z;
    let training = crate::training_targets::definition(spawn.id);
    let (actor_id, name, level, model_key, motion_set, attack_action_id, health) =
        if let Some(d) = training {
            assert_eq!(spawn.definition_vnum, d.vnum);
            (
                d.actor_id, d.name, d.level, d.actor_id, "general", "", d.health,
            )
        } else {
            let d = mob_definition(spawn.definition_vnum)
                .expect("compiled spawn must reference a registered mob");
            (
                d.actor_id,
                d.name,
                d.level,
                d.model_key,
                d.motion_set,
                d.attacks[0].attack.id,
                d.health,
            )
        };
    Monster {
        id: spawn.id,
        definition_vnum: spawn.definition_vnum,
        actor_id: actor_id.into(),
        name: name.into(),
        level,
        model_key: model_key.into(),
        motion_set: motion_set.into(),
        attack_action_id: attack_action_id.into(),
        attack_target: Identity::ZERO,
        attack_target_life_sequence: 0,
        x,
        y: content::height(x, z),
        z,
        heading: 0.0,
        health,
        max_health: health,
        activity: 0,
        attack_sequence,
        life_sequence,
        respawn_at_us: 0,
        action_started_at_us: 0,
        action_ends_at_us: 0,
    }
}

fn fresh_monster_clock(spawn: MonsterSpawnDefinition) -> MonsterClock {
    MonsterClock {
        id: spawn.id,
        home_x: spawn.home_x,
        home_z: spawn.home_z,
        next_attack_us: 0,
        attack_until_us: 0,
        pending_target: Identity::ZERO,
        pending_target_generation: 0,
        pending_source_generation: 0,
        pending_hit_at_us: 0,
        pending_hit_until_us: 0,
        area_invulnerable_until_us: 0,
    }
}

pub fn plan_player_attack(
    ctx: &ReducerContext,
    character: Identity,
    control: &Controller,
) -> Result<PlayerAttackPlan, String> {
    let definition =
        crate::characters::attack(ctx, character, inventory::equipped_weapon(ctx, character))?;
    let bounds = collision_bounds(ctx);
    let Some(player) = ctx.db.player().identity().find(character) else {
        return Ok(PlayerAttackPlan {
            definition,
            target_id: 0,
            target_generation: 0,
            heading: None,
            can_select_target: false,
        });
    };
    if control.combat_target_id != 0 {
        let selected = ctx
            .db
            .monster()
            .id()
            .find(control.combat_target_id)
            .filter(|monster| monster.life_sequence == control.combat_target_life_sequence);
        return Ok(PlayerAttackPlan {
            definition,
            target_id: control.combat_target_id,
            target_generation: control.combat_target_life_sequence,
            heading: selected.map(|monster| (player.x - monster.x).atan2(player.z - monster.z)),
            can_select_target: false,
        });
    }
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
    Ok(PlayerAttackPlan {
        definition,
        target_id: target.as_ref().map_or(0, |monster| monster.id),
        target_generation: target.as_ref().map_or(0, |monster| monster.life_sequence),
        heading: target
            .as_ref()
            .map(|monster| (player.x - monster.x).atan2(player.z - monster.z)),
        can_select_target: target.is_some(),
    })
}

pub fn start_player_action(
    ctx: &ReducerContext,
    controller: &mut Controller,
    plan: PlayerAttackPlan,
    now: i64,
) -> Result<(), String> {
    validate_player_action_start(ctx, controller, plan.definition, plan.target_id != 0, now)?;
    let speed = if crate::skills::is_skill_action(plan.definition.id) {
        100
    } else {
        crate::attack_timing::equipped_speed(ctx, controller.identity)?
    };
    let attack_until_us = now
        .checked_add(crate::attack_timing::scaled_us(
            plan.definition.duration_us,
            speed,
        )?)
        .ok_or("Attack timestamp is outside the supported range.")?;
    let source_cooldown = fresh_action_not_before(0, plan.definition)?;
    let next_attack_us = now
        .checked_add(crate::attack_timing::scaled_us(source_cooldown, speed)?)
        .ok_or("Attack timestamp is outside the supported range.")?;
    let action_revision = controller
        .action_revision
        .checked_add(1)
        .ok_or("Attack action revision limit reached.")?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(controller.identity)
        .ok_or("Enter the world first.")?;
    let attack_sequence = player
        .attack_sequence
        .checked_add(1)
        .ok_or("Attack sequence limit reached.")?;
    let has_ordinary_hit = plan.target_id != 0 && plan.definition.special_area.is_none();
    let requires_weapon = crate::characters::requires_weapon(plan.definition.id);
    let captured_attacker = (has_ordinary_hit || plan.definition.special_area.is_some())
        .then(|| crate::physical_damage::capture_player(ctx, controller.identity, requires_weapon))
        .transpose()?;
    let validated_target = has_ordinary_hit
        .then(|| {
            ctx.db
                .monster()
                .id()
                .find(plan.target_id)
                .filter(|monster| {
                    monster.health > 0 && monster.life_sequence == plan.target_generation
                })
        })
        .flatten();
    let pending_damage = crate::physical_damage::capture_ordinary_damage(
        has_ordinary_hit,
        validated_target,
        |monster| {
            crate::physical_damage::roll_player_hit(
                ctx,
                captured_attacker.expect("ordinary physical hits capture an attacker"),
                &monster,
            )
        },
    )?;
    let (hit_at_us, hit_until_us) = if !has_ordinary_hit {
        (0, 0)
    } else {
        (
            now.checked_add(crate::attack_timing::scaled_us(
                plan.definition.hit_start_us,
                speed,
            )?)
            .ok_or("Attack hit timestamp is outside the supported range.")?,
            now.checked_add(crate::attack_timing::scaled_us(
                plan.definition.hit_end_us,
                speed,
            )?)
            .ok_or("Attack hit timestamp is outside the supported range.")?,
        )
    };

    controller.mode = 0;
    controller.direction_x = 0.0;
    controller.direction_z = 0.0;
    controller.attack_until_us = attack_until_us;
    controller.attack_speed_percent = speed;
    controller.next_attack_us = next_attack_us;
    controller.action_revision = action_revision;
    controller.pending_attack_target_id = plan.target_id;
    controller.pending_attack_target_generation = plan.target_generation;
    controller.pending_attack_source_generation = if has_ordinary_hit {
        player.life_sequence
    } else {
        0
    };
    controller.pending_attack_hit_at_us = hit_at_us;
    controller.pending_attack_hit_until_us = hit_until_us;
    controller.pending_attack_damage = pending_damage;
    controller.pending_attack_range = if !has_ordinary_hit {
        0.0
    } else {
        plan.definition.range_m
    };
    controller.pending_attack_invulnerability_us = if has_ordinary_hit {
        plan.definition.ordinary_hit_invulnerability_us
    } else {
        0
    };
    controller.pending_attack_target_revision = controller.combat_target_revision;
    controller.pending_attack_can_select_target = plan.can_select_target;
    controller.pending_attack_action_revision = if !has_ordinary_hit {
        0
    } else {
        action_revision
    };

    player.activity = 2;
    if let Some(heading) = plan.heading {
        player.heading = heading;
    }
    crate::root_motion::start(
        controller,
        plan.definition,
        now,
        player.heading,
        action_revision,
    )?;
    crate::special_area::start(
        ctx,
        controller,
        plan.definition,
        player.life_sequence,
        now,
        player.heading,
        captured_attacker,
    )?;
    player.attack_sequence = attack_sequence;
    player.attack_speed_percent = speed;
    player.attack_action_id = plan.definition.id.into();
    player.action_started_at_us = now;
    player.action_ends_at_us = attack_until_us;
    ctx.db.player().identity().update(player);
    Ok(())
}

pub fn validate_player_action_start(
    ctx: &ReducerContext,
    controller: &Controller,
    definition: &AttackDefinition,
    has_target: bool,
    now: i64,
) -> Result<(), String> {
    let ordinary_cooldown_is_valid = if definition.special_area.is_some() {
        definition.ordinary_hit_invulnerability_us == 0
    } else {
        (1..=1_000_000).contains(&definition.ordinary_hit_invulnerability_us)
    };
    if !ordinary_cooldown_is_valid {
        return Err("The trusted ordinary-hit cooldown is invalid.".into());
    }
    now.checked_add(definition.duration_us)
        .ok_or("Attack timestamp is outside the supported range.")?;
    fresh_action_not_before(now, definition)?;
    controller
        .action_revision
        .checked_add(1)
        .ok_or("Attack action revision limit reached.")?;
    let player = ctx
        .db
        .player()
        .identity()
        .find(controller.identity)
        .ok_or("Enter the world first.")?;
    player
        .attack_sequence
        .checked_add(1)
        .ok_or("Attack sequence limit reached.")?;
    if has_target {
        now.checked_add(definition.hit_start_us)
            .and_then(|_| now.checked_add(definition.hit_end_us))
            .ok_or("Attack hit timestamp is outside the supported range.")?;
    }
    crate::root_motion::validate_action_definition(definition)?;
    crate::special_area::validate_action_definition(definition)
}

fn fresh_action_not_before(now: i64, definition: &AttackDefinition) -> Result<i64, String> {
    let cooldown = now
        .checked_add(definition.cooldown_us)
        .ok_or("Attack timestamp is outside the supported range.")?;
    if !definitions::PLAYER_ONEHAND_COMBO
        .iter()
        .any(|candidate| candidate.id == definition.id)
    {
        return Ok(cooldown);
    }
    let action_end = now
        .checked_add(definition.duration_us)
        .ok_or("Attack timestamp is outside the supported range.")?;
    Ok(cooldown.max(action_end))
}

pub fn take_due_player_hit(controller: &mut Controller, now: i64) -> Option<PendingPlayerHit> {
    if controller.pending_attack_hit_at_us == 0 || now < controller.pending_attack_hit_at_us {
        return None;
    }
    let still_valid = now <= controller.pending_attack_hit_until_us
        && now <= controller.attack_until_us
        && controller.pending_attack_target_id != 0
        && controller.pending_attack_action_revision != 0
        && controller.pending_attack_action_revision == controller.action_revision;
    let hit = still_valid.then_some(PendingPlayerHit {
        action_revision: controller.pending_attack_action_revision,
        target_id: controller.pending_attack_target_id,
        target_generation: controller.pending_attack_target_generation,
        source_generation: controller.pending_attack_source_generation,
        damage: controller.pending_attack_damage,
        range_m: controller.pending_attack_range,
        invulnerability_us: controller.pending_attack_invulnerability_us,
        target_revision: controller.pending_attack_target_revision,
        can_select_target: controller.pending_attack_can_select_target,
    });
    cancel_player_attack(controller);
    hit
}

pub fn discard_expired_player_hit(controller: &mut Controller, now: i64) {
    if controller.pending_attack_hit_at_us != 0
        && (now > controller.pending_attack_hit_until_us
            || now > controller.attack_until_us
            || controller.pending_attack_action_revision != controller.action_revision)
    {
        cancel_player_attack(controller);
    }
}

pub fn cancel_player_attack(controller: &mut Controller) {
    controller.pending_attack_target_id = 0;
    controller.pending_attack_target_generation = 0;
    controller.pending_attack_source_generation = 0;
    controller.pending_attack_hit_at_us = 0;
    controller.pending_attack_hit_until_us = 0;
    controller.pending_attack_damage = 0;
    controller.pending_attack_range = 0.0;
    controller.pending_attack_invulnerability_us = 0;
    controller.pending_attack_target_revision = 0;
    controller.pending_attack_can_select_target = false;
    controller.pending_attack_action_revision = 0;
}

pub fn cancel_attacks_targeting(ctx: &ReducerContext, character: Identity) {
    crate::mob_aggro::forget_character(ctx, character);
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
            action_revision: controller.pending_attack_action_revision,
        })
        .chain(
            ctx.db
                .monster_clock()
                .iter()
                .filter(|clock| clock.pending_hit_at_us != 0 && now >= clock.pending_hit_at_us)
                .map(|clock| DueHitEvent {
                    hit_at_us: clock.pending_hit_at_us,
                    source: DueHitSource::Monster(clock.id),
                    action_revision: 0,
                }),
        )
        .collect();
    visit_due_hits(&mut events, |event| match event.source {
        DueHitSource::Player(character) => {
            resolve_due_player_event(ctx, character, event.hit_at_us, event.action_revision, now)
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
    expected_action_revision: u64,
    now: i64,
) {
    let Some(mut controller) = ctx.db.controller().identity().find(character) else {
        return;
    };
    if controller.pending_attack_hit_at_us != expected_hit_at_us
        || controller.pending_attack_action_revision != expected_action_revision
        || controller.action_revision != expected_action_revision
        || now < expected_hit_at_us
    {
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
    let now = now_us(ctx);
    if !player.online
        || player.health == 0
        || !exact_hit_generations_match(
            hit.source_generation,
            player.life_sequence,
            hit.target_generation,
            monster.life_sequence,
        )
        || monster.health == 0
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
    if !monster_hit_cooldown_allows(ctx, monster.id, now) {
        return;
    }
    let controller = ctx
        .db
        .controller()
        .identity()
        .find(character)
        .expect("a resolved player hit has an active controller");
    if controller.action_revision != hit.action_revision {
        return;
    }
    player.heading = crate::root_motion::active_action_heading(&controller)
        .unwrap_or_else(|| (player.x - monster.x).atan2(player.z - monster.z));
    let force = crate::characters::root_actions()
        .find(|definition| definition.id == player.attack_action_id)
        .and_then(|definition| definition.ordinary_knockback)
        .map(|definition| crate::knockback::ForceStart {
            source_character: character,
            source_action_revision: hit.action_revision,
            now,
            front: crate::knockback::is_front_hit(player.heading, monster.heading),
            direction: crate::knockback::force_direction((player.x, player.z), &monster),
            distance_m: definition.unobstructed_distance_m,
            duration_us: definition.duration_us,
        });
    ctx.db.player().identity().update(player);
    record_damage(
        ctx,
        monster.id,
        monster.life_sequence,
        character,
        controller.connection_id,
        u32::from(hit.damage),
        crate::mob_threat::DamageKind::Normal,
    )
    .unwrap_or_else(|error| panic!("cannot record resolved monster damage: {error}"));
    mark_monster_hit_cooldown(ctx, monster.id, now, hit.invulnerability_us)
        .unwrap_or_else(|error| panic!("cannot set resolved monster hit cooldown: {error}"));
    if apply_damage(&mut monster.health, hit.damage) {
        kill_monster(ctx, &mut monster, character);
    } else if let Some(force) = force {
        let mut clock = ctx
            .db
            .monster_clock()
            .id()
            .find(monster.id)
            .expect("a surviving monster has an action clock");
        cancel_monster_hit(&mut clock);
        clock.attack_until_us = 0;
        ctx.db.monster_clock().id().update(clock);
        crate::knockback::start(ctx, &mut monster, force)
            .unwrap_or_else(|error| panic!("cannot apply ordinary GREAT hit: {error}"));
    }
    let target_id = monster.id;
    let target_life_sequence = monster.life_sequence;
    ctx.db.monster().id().update(monster);
    if hit.can_select_target {
        crate::targeting::select_fallback_after_hit(
            ctx,
            character,
            target_id,
            target_life_sequence,
            hit.target_revision,
        );
    }
}

pub(crate) fn kill_monster(ctx: &ReducerContext, monster: &mut Monster, character: Identity) {
    let now = now_us(ctx);
    crate::mob_affects::clear(ctx, monster.id);
    crate::combo::clear_chains_targeting(ctx, monster.id, monster.life_sequence);
    monster.activity = 3;
    clear_monster_attack_target(monster);
    monster.action_started_at_us = now;
    monster.respawn_at_us =
        now.saturating_add(crate::training_targets::definition(monster.id).map_or_else(
            || {
                ordinary_definition(ctx, monster)
                    .expect("defeated mob must be trusted")
                    .respawn_us
            },
            |d| d.respawn_us,
        ));
    monster.action_ends_at_us = monster.respawn_at_us;
    crate::targeting::clear_monster_targets(ctx, monster.id, monster.life_sequence)
        .unwrap_or_else(|error| panic!("cannot clear defeated monster targets: {error}"));
    if let Some(mut clock) = ctx.db.monster_clock().id().find(monster.id) {
        clock.attack_until_us = 0;
        cancel_monster_hit(&mut clock);
        ctx.db.monster_clock().id().update(clock);
    }
    crate::knockback::clear(ctx, monster.id);
    if crate::training_targets::definition(monster.id).is_some() {
        clear_monster_damage(ctx, monster.id, monster.life_sequence);
        return;
    }
    let definition = ordinary_definition(ctx, monster).expect("rewarded mob must be trusted");
    award_monster_experience(ctx, monster);
    inventory::drop_potion(ctx, character, monster.x, monster.y, monster.z);
    ctx.db.loot().insert(Loot {
        id: 0,
        x: monster.x,
        y: monster.y,
        z: monster.z,
        gold: roll_u32(ctx, definition.gold_min, definition.gold_max),
        owner: character,
        reserved_until_us: now.saturating_add(LOOT_RESERVED_US),
        expires_at_us: now.saturating_add(LOOT_EXPIRES_US),
    });
}

pub(crate) fn record_damage(
    ctx: &ReducerContext,
    monster_id: u32,
    monster_life_sequence: u32,
    character_id: Identity,
    controller_connection_id: ConnectionId,
    damage: u32,
    kind: crate::mob_threat::DamageKind,
) -> Result<(), String> {
    if damage == 0 || crate::training_targets::definition(monster_id).is_some() {
        return Ok(());
    }
    let monster = ctx
        .db
        .monster()
        .id()
        .find(monster_id)
        .ok_or("Threat monster is missing")?;
    if monster.life_sequence != monster_life_sequence {
        return Err("Threat monster life is stale".into());
    }
    crate::mob_aggro::record_hit(ctx, &monster, character_id, damage, kind)?;
    let mut matching: Vec<_> = ctx
        .db
        .monster_damage()
        .monster_id()
        .filter(monster_id)
        .filter(|row| {
            row.monster_life_sequence == monster_life_sequence
                && row.character_id == character_id
                && row.controller_connection_id == controller_connection_id
        })
        .collect();
    if matching.len() > 1 {
        return Err("The monster damage ledger contains duplicate attribution rows.".into());
    }
    if let Some(mut row) = matching.pop() {
        row.registered_damage = row
            .registered_damage
            .checked_add(damage)
            .ok_or("Registered monster damage overflowed.")?;
        ctx.db.monster_damage().id().update(row);
    } else {
        ctx.db.monster_damage().insert(MonsterDamage {
            id: 0,
            monster_id,
            monster_life_sequence,
            character_id,
            controller_connection_id,
            registered_damage: damage,
        });
    }
    Ok(())
}

fn source_distance_approx_cm(dx_cm: i64, dz_cm: i64) -> Option<i64> {
    let x = dx_cm.checked_abs()?;
    let z = dz_cm.checked_abs()?;
    let minimum = x.min(z);
    let maximum = x.max(z);
    maximum
        .checked_mul(246)?
        .checked_add(minimum.checked_mul(102)?)
        .map(|value| value >> 8)
}

pub(crate) fn source_distance_between_meters(a: (f32, f32), b: (f32, f32)) -> Option<i64> {
    let to_cm = |delta: f64| {
        let value = (delta * 100.0).trunc();
        if value.is_finite() && value >= i64::MIN as f64 && value <= i64::MAX as f64 {
            Some(value as i64)
        } else {
            None
        }
    };
    let dx = to_cm(f64::from(a.0) - f64::from(b.0))?;
    let dz = to_cm(f64::from(a.1) - f64::from(b.1))?;
    source_distance_approx_cm(dx, dz)
}

fn distribute_raw_experience(
    base: u32,
    contributions: &[(Identity, u32)],
) -> Result<Vec<(Identity, u32)>, String> {
    if base == 0 || contributions.is_empty() {
        return Ok(Vec::new());
    }
    let mut contributions = contributions.to_vec();
    contributions.sort_by_key(|left| left.0.to_string());
    let total = contributions.iter().try_fold(0_u32, |sum, (_, damage)| {
        sum.checked_add(*damage)
            .ok_or("Eligible monster damage overflowed.")
    })?;
    if total == 0 {
        return Ok(Vec::new());
    }
    let highest = contributions
        .iter()
        .enumerate()
        .fold(0, |highest, (index, (_, damage))| {
            if *damage > contributions[highest].1 {
                index
            } else {
                highest
            }
        });
    let reserve = base / 5;
    let remainder = base - reserve;
    let mut result = Vec::with_capacity(contributions.len());
    let (highest_identity, highest_damage) = contributions[highest];
    let highest_proportion = ((highest_damage as f32) / (total as f32)).min(1.0);
    result.push((
        highest_identity,
        reserve + ((remainder as f32) * highest_proportion) as u32,
    ));
    if highest_proportion == 1.0 {
        return Ok(result);
    }
    for (index, (identity, damage)) in contributions.into_iter().enumerate() {
        if index == highest {
            continue;
        }
        let proportion = ((damage as f32) / (total as f32)).min(1.0);
        let raw = ((remainder as f32) * proportion) as u32;
        if raw > 0 {
            result.push((identity, raw));
        }
    }
    Ok(result)
}

fn clear_monster_damage(ctx: &ReducerContext, monster_id: u32, life_sequence: u32) {
    crate::mob_aggro::clear_monster(ctx, monster_id);
    let ids: Vec<_> = ctx
        .db
        .monster_damage()
        .monster_id()
        .filter(monster_id)
        .filter(|row| row.monster_life_sequence == life_sequence)
        .map(|row| row.id)
        .collect();
    for id in ids {
        ctx.db.monster_damage().id().delete(id);
    }
}

fn award_monster_experience(ctx: &ReducerContext, monster: &Monster) {
    let mut eligible: Vec<(Identity, u32)> = Vec::new();
    for row in ctx
        .db
        .monster_damage()
        .monster_id()
        .filter(monster.id)
        .filter(|row| row.monster_life_sequence == monster.life_sequence)
    {
        let Some(player) = ctx.db.player().identity().find(row.character_id) else {
            continue;
        };
        let same_live_connection = player.online
            && ctx
                .db
                .controller()
                .identity()
                .find(row.character_id)
                .is_some_and(|control| {
                    control.connection_id == row.controller_connection_id
                        && ctx
                            .db
                            .session()
                            .connection_id()
                            .find(control.connection_id)
                            .is_some()
                });
        let in_range = source_distance_between_meters((player.x, player.z), (monster.x, monster.z))
            .is_some_and(|distance| distance <= definitions::EXP_ELIGIBILITY_DISTANCE_CM);
        if same_live_connection
            && in_range
            && ctx
                .db
                .character_progression()
                .character_id()
                .find(row.character_id)
                .is_some()
        {
            if let Some((_, damage)) = eligible
                .iter_mut()
                .find(|(identity, _)| *identity == row.character_id)
            {
                *damage = damage
                    .checked_add(row.registered_damage)
                    .unwrap_or_else(|| {
                        panic!("eligible monster damage overflowed for one character")
                    });
            } else {
                eligible.push((row.character_id, row.registered_damage));
            }
        }
    }
    let definition = ordinary_definition(ctx, monster).expect("experience source must be trusted");
    let shares = distribute_raw_experience(definition.experience, &eligible)
        .unwrap_or_else(|error| panic!("cannot distribute monster experience: {error}"));
    for (recipient, share) in shares {
        progression::apply_combat_experience(ctx, recipient, definition.level, share)
            .unwrap_or_else(|error| panic!("cannot apply monster experience: {error}"));
    }
    clear_monster_damage(ctx, monster.id, monster.life_sequence);
}

pub(crate) fn apply_damage(health: &mut u16, damage: u16) -> bool {
    if *health == 0 {
        return false;
    }
    *health = health.saturating_sub(damage);
    *health == 0
}

pub(crate) fn monster_hit_cooldown_allows(ctx: &ReducerContext, monster_id: u32, now: i64) -> bool {
    ctx.db
        .monster_clock()
        .id()
        .find(monster_id)
        .is_some_and(|clock| hit_cooldown_allows(now, clock.area_invulnerable_until_us))
}

fn hit_cooldown_allows(now: i64, invulnerable_until_us: i64) -> bool {
    now >= invulnerable_until_us
}

pub(crate) fn mark_monster_hit_cooldown(
    ctx: &ReducerContext,
    monster_id: u32,
    now: i64,
    duration_us: i64,
) -> Result<(), String> {
    if duration_us <= 0 {
        return Err("Monster hit cooldown is invalid.".into());
    }
    let mut clock = ctx
        .db
        .monster_clock()
        .id()
        .find(monster_id)
        .ok_or("The trusted monster clock is missing.")?;
    clock.area_invulnerable_until_us = now
        .checked_add(duration_us)
        .ok_or("Monster hit cooldown timestamp is outside the supported range.")?;
    ctx.db.monster_clock().id().update(clock);
    Ok(())
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

pub fn simulate(ctx: &ReducerContext, elapsed: f32) -> Result<(), String> {
    let now = now_us(ctx);
    crate::mob_affects::maintain(ctx, now);
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
        let spawn = validate_monster(ctx, &monster)?;
        if monster.health == 0 {
            if now >= monster.respawn_at_us {
                if crate::mob_regeneration::destroy(ctx, monster.id)? {
                    clear_monster_damage(ctx, monster.id, monster.life_sequence);
                    ctx.db.monster_clock().id().delete(monster.id);
                    ctx.db.monster().id().delete(monster.id);
                    continue;
                }
                let life_sequence = monster.life_sequence.wrapping_add(1);
                clear_monster_damage(ctx, monster.id, monster.life_sequence);
                ctx.db.monster().id().update(fresh_monster(
                    spawn,
                    life_sequence,
                    monster.attack_sequence,
                ));
                ctx.db
                    .monster_clock()
                    .id()
                    .update(fresh_monster_clock(spawn));
            }
            continue;
        }
        if crate::training_targets::validate(&monster)?.is_some() {
            continue;
        }
        let definition = ordinary_definition(ctx, &monster)?;
        if crate::knockback::locks_ai(ctx, monster.id, monster.life_sequence)
            || crate::mob_affects::stunned(ctx, &monster, now)
        {
            continue;
        }
        let previous_monster = monster.clone();
        let mut clock = ctx
            .db
            .monster_clock()
            .id()
            .find(monster.id)
            .unwrap_or_else(|| fresh_monster_clock(spawn));
        let previous_clock = clock.clone();
        if (clock.home_x, clock.home_z) != (spawn.home_x, spawn.home_z) {
            clock.home_x = spawn.home_x;
            clock.home_z = spawn.home_z;
        }
        let target = select_monster_victim(ctx, &monster, &clock, &bounds);
        let (tx, tz) = target
            .as_ref()
            .map(|player| (player.x, player.z))
            .unwrap_or((clock.home_x, clock.home_z));
        let distance = (tx - monster.x).hypot(tz - monster.z);
        monster.activity = 0;
        let mut immediate_hit = false;
        if now < clock.attack_until_us {
            monster.activity = 2;
        } else if let Some(player) = target.filter(|player| {
            within_reach(
                (monster.x, monster.y, monster.z),
                (player.x, player.y, player.z),
                definition.attack_range_m,
            )
        }) {
            monster.heading = (monster.x - player.x).atan2(monster.z - player.z);
            monster.action_started_at_us = 0;
            monster.action_ends_at_us = 0;
            if now >= clock.next_attack_us {
                immediate_hit = schedule_monster_hit(
                    ctx,
                    &mut monster,
                    &mut clock,
                    player.identity,
                    player.life_sequence,
                    now,
                )?;
            }
        } else if distance > 0.1 {
            monster.action_started_at_us = 0;
            monster.action_ends_at_us = 0;
            let travel = (definition.move_speed_mps * elapsed.clamp(0.0, 0.1)).min(distance);
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
        if monster.activity != 2 {
            clear_monster_attack_target(&mut monster);
        }
        let monster_id = monster.id;
        // Idle population must not rewrite thousands of identical rows each tick.
        // Compare all fields so action timing, life and target changes still publish.
        if monster != previous_monster {
            ctx.db.monster().id().update(monster);
        }
        if clock != previous_clock {
            ctx.db.monster_clock().id().update(clock);
        }
        if immediate_hit {
            // Publish the accepted source action before resolving its exact target.
            // Consume the pending record in this transaction, never on a client fly event.
            resolve_due_monster_event(ctx, monster_id, now, now);
        }
    }
    crate::mob_regeneration::tick(ctx)?;
    Ok(())
}

fn mob_distance_m(a: (f32, f32), b: (f32, f32), original: bool) -> f64 {
    if original {
        source_distance_between_meters(a, b).map_or(f64::INFINITY, |cm| cm as f64 / 100.0)
    } else {
        f64::from((a.0 - b.0).hypot(a.1 - b.1))
    }
}

fn within_chase_policy(
    d: &definitions::MobDefinition,
    monster: (f32, f32),
    home: (f32, f32),
    player: (f32, f32),
) -> bool {
    if let Some(limit) = d.target_chase_limit_cm {
        limit > 0
            && source_distance_between_meters(monster, player)
                .is_some_and(|distance| distance < limit)
    } else {
        (player.0 - home.0).hypot(player.1 - home.1) < d.chase_home_range_m
    }
}

fn select_monster_victim(
    ctx: &ReducerContext,
    monster: &Monster,
    clock: &MonsterClock,
    bounds: &[crate::movement::Bounds],
) -> Option<crate::Player> {
    let definition = ordinary_definition(ctx, monster).ok()?;
    if let Some(player) = crate::mob_aggro::victim(ctx, monster).filter(|p| {
        within_chase_policy(
            definition,
            (monster.x, monster.z),
            (clock.home_x, clock.home_z),
            (p.x, p.z),
        ) && content::clear_path(monster.x, monster.z, p.x, p.z, bounds)
    }) {
        return Some(player);
    }
    crate::mob_aggro::clear_monster(ctx, monster.id);
    if !definition.aggressive
        && !crate::mob_regeneration::forces_aggression(ctx, monster.id).ok()?
    {
        return None;
    }
    let selected =
        ctx.db
            .player()
            .iter()
            .filter(|player| player.online && player.health > 0)
            .filter(|player| {
                within_chase_policy(
                    definition,
                    (monster.x, monster.z),
                    (clock.home_x, clock.home_z),
                    (player.x, player.z),
                )
            })
            .filter(|player| {
                mob_distance_m(
                    (monster.x, monster.z),
                    (player.x, player.z),
                    definition.target_chase_limit_cm.is_some(),
                ) < f64::from(definition.acquisition_range_m)
            })
            .filter(|player| content::clear_path(monster.x, monster.z, player.x, player.z, bounds))
            .min_by(|a, b| {
                let original = definition.target_chase_limit_cm.is_some();
                mob_distance_m((monster.x, monster.z), (a.x, a.z), original).total_cmp(
                    &mob_distance_m((monster.x, monster.z), (b.x, b.z), original),
                )
            });
    if let Some(player) = &selected {
        crate::mob_aggro::acquire(ctx, monster, player);
    }
    selected
}

fn schedule_monster_hit(
    ctx: &ReducerContext,
    monster: &mut Monster,
    clock: &mut MonsterClock,
    target: Identity,
    target_generation: u32,
    now: i64,
) -> Result<bool, String> {
    let definition = ordinary_definition(ctx, monster)?;
    let roll = if definition.attacks.len() == 1 {
        1
    } else {
        ctx.rng().gen_range(1..=100)
    };
    let attack = crate::mob_actions::select(definition, roll)?;
    clock.next_attack_us = now.saturating_add(attack.cooldown_us);
    clock.attack_until_us = now.saturating_add(attack.duration_us);
    clock.pending_target = target;
    clock.pending_target_generation = target_generation;
    clock.pending_source_generation = monster.life_sequence;
    let immediate = definition.damage_kind != crate::mob_damage::Kind::Normal;
    clock.pending_hit_at_us = now.saturating_add(attack.hit_start_us);
    clock.pending_hit_until_us = now.saturating_add(attack.hit_end_us);
    monster.attack_action_id = attack.id.into();
    monster.attack_target = target;
    monster.attack_target_life_sequence = target_generation;
    monster.attack_sequence = monster.attack_sequence.wrapping_add(1);
    monster.activity = 2;
    monster.action_started_at_us = now;
    monster.action_ends_at_us = clock.attack_until_us;
    Ok(immediate)
}

fn resolve_monster_hit(ctx: &ReducerContext, monster_id: u32, hit: PendingMonsterHit, now: i64) {
    let Some(monster) = ctx.db.monster().id().find(monster_id) else {
        return;
    };
    let Ok(definition) = ordinary_definition(ctx, &monster) else {
        return;
    };
    let Ok(attack) = crate::mob_actions::by_id(definition, &monster.attack_action_id) else {
        return;
    };
    let Some(mut player) = ctx.db.player().identity().find(hit.target) else {
        return;
    };
    if monster.health == 0
        || !exact_hit_generations_match(
            hit.source_generation,
            monster.life_sequence,
            hit.target_generation,
            player.life_sequence,
        )
        || !player.online
        || player.health == 0
        || !within_reach(
            (monster.x, monster.y, monster.z),
            (player.x, player.y, player.z),
            attack.range_m,
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
    // Sample current defenses and affects only after this exact-life hit qualifies.
    let damage = crate::physical_damage::roll_monster_hit(ctx, &monster, player.identity)
        .unwrap_or_else(|error| panic!("cannot resolve trusted monster damage: {error}"));
    if apply_damage(&mut player.health, damage) {
        crate::player_buffs::clear(ctx, player.identity);
        crate::npcs::clear(ctx, player.identity);
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
            crate::combo::clear_chain(&mut controller);
            crate::root_motion::clear(&mut controller);
            crate::special_area::clear(ctx, player.identity);
            crate::targeting::clear_character_target(ctx, &mut controller)
                .unwrap_or_else(|error| panic!("cannot clear defeated character target: {error}"));
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
        source_generation: clock.pending_source_generation,
    });
    cancel_monster_hit(clock);
    hit
}

/// Presentation target survives hit consumption, but not the owning action/life.
pub(crate) fn clear_monster_attack_target(monster: &mut Monster) {
    monster.attack_target = Identity::ZERO;
    monster.attack_target_life_sequence = 0;
}

pub(crate) fn cancel_monster_hit(clock: &mut MonsterClock) {
    clock.pending_target = Identity::ZERO;
    clock.pending_target_generation = 0;
    clock.pending_source_generation = 0;
    clock.pending_hit_at_us = 0;
    clock.pending_hit_until_us = 0;
}

#[cfg(test)]
mod tests {
    #[test]
    fn original_chase_uses_current_target_distance_instead_of_authored_home() {
        let authored = super::definitions::MOB_DEFINITIONS[0];
        let original = super::definitions::MobDefinition {
            target_chase_limit_cm: Some(4000),
            ..authored
        };
        assert!(!super::within_chase_policy(
            &authored,
            (100.0, 0.0),
            (0.0, 0.0),
            (110.0, 0.0)
        ));
        assert!(super::within_chase_policy(
            &original,
            (100.0, 0.0),
            (0.0, 0.0),
            (110.0, 0.0)
        ));
        // The source approximation differs from Euclidean meters along one axis.
        assert!(super::within_chase_policy(
            &original,
            (0.0, 0.0),
            (0.0, 0.0),
            (41.0, 0.0)
        ));
        assert!(!super::within_chase_policy(
            &original,
            (0.0, 0.0),
            (0.0, 0.0),
            (42.0, 0.0)
        ));
        assert!(!super::within_chase_policy(
            &original,
            (0.0, 0.0),
            (0.0, 0.0),
            (f32::NAN, 0.0)
        ));
    }

    fn validate_fixture(monster: &super::Monster) -> Result<(), String> {
        let spawn = super::definitions::MONSTER_SPAWNS
            .iter()
            .chain(super::definitions::TRAINING_TARGET_SPAWNS)
            .find(|spawn| spawn.id == monster.id)
            .ok_or("Missing fixture spawn")?;
        super::validate_monster_at(monster, *spawn)
    }

    fn ordinary_fixture(monster: &super::Monster) -> Result<(), String> {
        validate_fixture(monster)?;
        super::mob_definition(monster.definition_vnum).ok_or("Not an ordinary definition")?;
        Ok(())
    }

    #[test]
    fn persisted_mob_identity_must_match_its_compiled_spawn() {
        let spawn = super::definitions::MONSTER_SPAWNS[0];
        let mut monster = super::fresh_monster(spawn, 0, 0);
        assert_eq!(monster.definition_vnum, spawn.definition_vnum);
        assert!(validate_fixture(&monster).is_ok());
        monster.definition_vnum = spawn.definition_vnum + 1;
        assert!(validate_fixture(&monster).is_err());
        monster = super::fresh_monster(spawn, 0, 0);
        monster.id = u32::MAX;
        assert!(validate_fixture(&monster).is_err());
        let training = super::definitions::TRAINING_TARGET_SPAWNS[0];
        monster = super::fresh_monster(training, 0, 0);
        assert_eq!(monster.definition_vnum, training.definition_vnum);
        assert!(validate_fixture(&monster).is_ok());
        monster.id = spawn.id;
        assert!(validate_fixture(&monster).is_err());
    }

    #[test]
    fn persisted_mob_stats_and_presentation_cannot_drift_from_registry() {
        let original = super::fresh_monster(super::definitions::MONSTER_SPAWNS[0], 0, 0);
        for field in ["level", "health", "model", "motions"] {
            let mut monster = super::fresh_monster(super::definitions::MONSTER_SPAWNS[0], 0, 0);
            match field {
                "level" => monster.level += 1,
                "health" => monster.max_health += 1,
                "model" => monster.model_key = "unregistered-model".into(),
                "motions" => monster.motion_set = "unregistered-motions".into(),
                _ => unreachable!(),
            }
            assert!(ordinary_fixture(&monster).is_err(), "{field}");
        }
        assert!(ordinary_fixture(&original).is_ok());
        let dummy = super::fresh_monster(super::definitions::TRAINING_TARGET_SPAWNS[0], 0, 0);
        assert!(validate_fixture(&dummy).is_ok());
        assert!(ordinary_fixture(&dummy).is_err());
    }

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
            attack_speed_percent: 100,
            next_attack_us: 0,
            action_revision: 5,
            pending_attack_target_id: 7,
            pending_attack_target_generation: 11,
            pending_attack_source_generation: 2,
            pending_attack_hit_at_us: hit_at_us,
            pending_attack_hit_until_us: hit_until_us,
            pending_attack_damage: 35,
            pending_attack_range: 2.7,
            pending_attack_invulnerability_us: 100_000,
            pending_attack_target_revision: 9,
            pending_attack_can_select_target: true,
            pending_attack_action_revision: 5,
            combat_target_id: 0,
            combat_target_life_sequence: 0,
            combat_target_change_not_before_us: 0,
            combat_target_revision: 9,
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
        }
    }

    fn monster_clock_with_hit(hit_at_us: i64, hit_until_us: i64) -> MonsterClock {
        MonsterClock {
            id: 1,
            home_x: 3.0,
            home_z: 3.0,
            next_attack_us: 0,
            attack_until_us: 2_000_000,
            pending_target: Identity::from_claims("test", "target"),
            pending_target_generation: 4,
            pending_source_generation: 3,
            pending_hit_at_us: hit_at_us,
            pending_hit_until_us: hit_until_us,
            area_invulnerable_until_us: 0,
        }
    }

    fn cross_side_lethal_outcome(player_hit_at_us: i64, monster_hit_at_us: i64) -> (bool, bool) {
        let player = Identity::from_claims("test", "player");
        let mut events = [
            DueHitEvent {
                hit_at_us: player_hit_at_us,
                source: DueHitSource::Player(player),
                action_revision: 5,
            },
            DueHitEvent {
                hit_at_us: monster_hit_at_us,
                source: DueHitSource::Monster(1),
                action_revision: 0,
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
    fn global_monster_hit_cooldown_ends_at_its_exact_boundary() {
        assert!(!hit_cooldown_allows(1_299_999, 1_300_000));
        assert!(hit_cooldown_allows(1_300_000, 1_300_000));
        assert!(hit_cooldown_allows(1_300_001, 1_300_000));
    }

    #[test]
    fn combo_fresh_action_deadline_includes_the_full_motion() {
        let combo_one = &definitions::PLAYER_ONEHAND_COMBO[0];
        let combo_two = &definitions::PLAYER_ONEHAND_COMBO[1];
        let combo_four = &definitions::PLAYER_ONEHAND_COMBO[3];
        assert_eq!(fresh_action_not_before(100, combo_one).unwrap(), 1_000_100);
        assert_eq!(fresh_action_not_before(100, combo_two).unwrap(), 933_433);
        assert_eq!(fresh_action_not_before(100, combo_four).unwrap(), 1_266_767);
        assert_eq!(
            fresh_action_not_before(100, &definitions::PLAYER_GENERAL_ATTACK).unwrap(),
            850_100
        );
        assert!(fresh_action_not_before(i64::MAX, combo_one).is_err());
    }

    #[test]
    fn delayed_hit_is_taken_once_inside_the_window() {
        let mut controller = controller_with_hit(1_192_308, 1_315_385);
        assert_eq!(take_due_player_hit(&mut controller, 1_192_307), None);
        let hit = take_due_player_hit(&mut controller, 1_250_000).unwrap();
        assert_eq!(hit.action_revision, 5);
        assert_eq!(hit.target_id, 7);
        assert_eq!(hit.target_generation, 11);
        assert_eq!(hit.source_generation, 2);
        assert_eq!(hit.damage, 35);
        assert_eq!(take_due_player_hit(&mut controller, 1_300_000), None);
    }

    #[test]
    fn target_change_cannot_rewrite_the_pending_hit_snapshot() {
        let mut controller = controller_with_hit(1_192_308, 1_315_385);
        controller.combat_target_id = 99;
        controller.combat_target_life_sequence = 42;
        controller.combat_target_revision = 10;
        let hit = take_due_player_hit(&mut controller, 1_250_000).unwrap();
        assert_eq!(hit.target_id, 7);
        assert_eq!(hit.target_generation, 11);
        assert_eq!(hit.source_generation, 2);
        assert_eq!(hit.damage, 35);
        assert_eq!(hit.target_revision, 9);
        assert!(hit.can_select_target);
    }

    #[test]
    fn generated_monsters_keep_distinct_trusted_homes() {
        assert!(!definitions::MONSTER_SPAWNS.is_empty());
        for (index, spawn) in definitions::MONSTER_SPAWNS.iter().enumerate() {
            assert!(spawn.home_x.is_finite() && spawn.home_z.is_finite());
            assert!(
                content::valid_target(spawn.home_x, spawn.home_z).is_ok(),
                "Blocked monster home {} at {}, {}",
                spawn.id,
                spawn.home_x,
                spawn.home_z
            );
            assert!(
                definitions::MONSTER_SPAWNS[..index]
                    .iter()
                    .all(|previous| previous.id != spawn.id)
            );
            let monster = fresh_monster(*spawn, 4, 8);
            let clock = fresh_monster_clock(*spawn);
            assert_eq!((monster.x, monster.z), (spawn.home_x, spawn.home_z));
            assert_eq!((clock.home_x, clock.home_z), (spawn.home_x, spawn.home_z));
        }
        if !definitions::COMBAT_FIXTURE_CONTENT_HASH.is_empty() {
            assert!(definitions::MONSTER_SPAWNS.len() >= 2);
            assert!(definitions::MONSTER_SPAWNS.windows(2).all(|pair| {
                pair[0].home_x != pair[1].home_x || pair[0].home_z != pair[1].home_z
            }));
        }
    }

    #[test]
    fn stale_or_cancelled_action_cannot_hit() {
        let mut stale = controller_with_hit(1_192_308, 1_315_385);
        assert_eq!(take_due_player_hit(&mut stale, 1_400_000), None);
        assert_eq!(take_due_player_hit(&mut stale, 1_500_000), None);
        let mut cancelled = controller_with_hit(1_192_308, 1_315_385);
        cancel_player_attack(&mut cancelled);
        assert_eq!(cancelled.pending_attack_source_generation, 0);
        assert_eq!(take_due_player_hit(&mut cancelled, 1_250_000), None);
    }

    #[test]
    fn both_hit_generations_must_match_and_zero_is_a_valid_fresh_life() {
        assert!(exact_hit_generations_match(0, 0, 0, 0));
        assert!(exact_hit_generations_match(3, 3, 7, 7));
        assert!(!exact_hit_generations_match(3, 4, 7, 7));
        assert!(!exact_hit_generations_match(3, 3, 7, 8));
    }

    #[test]
    fn immediate_monster_hit_is_consumed_on_acceptance_and_not_replayed() {
        let now = 1_000_000;
        let mut clock = monster_clock_with_hit(now, now);
        assert!(take_due_monster_hit(&mut clock, now - 1).is_none());
        let hit = take_due_monster_hit(&mut clock, now).unwrap();
        assert_eq!((hit.source_generation, hit.target_generation), (3, 4));
        assert!(take_due_monster_hit(&mut clock, now).is_none());
        assert!(take_due_monster_hit(&mut clock, now + 50_000).is_none());
        assert_eq!(clock.pending_target, Identity::ZERO);
    }

    #[test]
    fn monster_hit_is_consumed_once_and_expires_after_its_window() {
        let mut due = monster_clock_with_hit(1_320_195, 1_492_782);
        assert_eq!(take_due_monster_hit(&mut due, 1_320_194), None);
        let hit = take_due_monster_hit(&mut due, 1_400_000).unwrap();
        assert_eq!(hit.source_generation, 3);
        assert_eq!(hit.target_generation, 4);
        assert_eq!(take_due_monster_hit(&mut due, 1_450_000), None);
        assert_eq!(due.pending_source_generation, 0);

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

    #[test]
    fn no_party_split_preserves_overkill_and_unassigned_float_remainder() {
        let high = Identity::from_claims("test", "high");
        let low = Identity::from_claims("test", "low");
        let shares = distribute_raw_experience(15, &[(low, 35), (high, 75)]).unwrap();
        assert_eq!(shares.iter().find(|row| row.0 == high).unwrap().1, 11);
        assert_eq!(shares.iter().find(|row| row.0 == low).unwrap().1, 3);
        assert_eq!(shares.iter().map(|row| row.1).sum::<u32>(), 14);
    }

    #[test]
    fn no_party_tie_uses_stable_identity_order_and_single_contributor_gets_all() {
        let first = Identity::from_claims("test", "a");
        let second = Identity::from_claims("test", "b");
        let expected_high = [first, second]
            .into_iter()
            .min_by_key(|identity| identity.to_string())
            .unwrap();
        let tied = distribute_raw_experience(15, &[(second, 50), (first, 50)]).unwrap();
        assert_eq!(tied.iter().find(|row| row.0 == expected_high).unwrap().1, 9);
        assert_eq!(tied.iter().map(|row| row.1).sum::<u32>(), 15);
        assert_eq!(
            distribute_raw_experience(15, &[(first, 110)]).unwrap(),
            [(first, 15)]
        );
        assert_eq!(
            distribute_raw_experience(15, &[(first, u32::MAX - 1), (second, 1)]).unwrap(),
            [(first, 15)]
        );
    }

    #[test]
    fn source_approximate_distance_keeps_exact_boundary_and_rejects_invalid_positions() {
        assert_eq!(source_distance_approx_cm(5_204, 0), Some(5_000));
        assert_eq!(source_distance_approx_cm(5_205, 0), Some(5_001));
        assert!(
            source_distance_between_meters((0.0, 0.0), (52.03, 0.0)).unwrap()
                <= definitions::EXP_ELIGIBILITY_DISTANCE_CM
        );
        assert!(
            source_distance_between_meters((0.0, 0.0), (52.06, 0.0)).unwrap()
                > definitions::EXP_ELIGIBILITY_DISTANCE_CM
        );
        assert_eq!(
            source_distance_between_meters((f32::NAN, 0.0), (0.0, 0.0)),
            None
        );
    }
}
