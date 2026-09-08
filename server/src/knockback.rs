//! Server-owned monster force and GREAT-hit reaction state.

use crate::combat::monster;
use crate::definitions::MonsterReactionDefinition;
use crate::{collision_bounds, content};
use spacetimedb::{Identity, ReducerContext, Table};

const FORCE_SUBSTEP_US: i64 = 50_000;
const MAX_FORCE_DURATION_US: i64 = 1_600_000;
const MAX_FORCE_DISTANCE_M: f64 = 8.0;
const REACTION_FRONT_KNOCKDOWN: u8 = 1;
const REACTION_FRONT_STANDUP: u8 = 2;
const REACTION_BACK_KNOCKDOWN: u8 = 3;
const REACTION_COMPLETE: u8 = 4;

#[spacetimedb::table(accessor = monster_force)]
pub struct MonsterForce {
    #[primary_key]
    pub monster_id: u32,
    pub monster_life_sequence: u32,
    pub source_character: Identity,
    pub source_action_revision: u64,
    pub started_at_us: i64,
    pub consumed_elapsed_us: i64,
    pub direction_x: f32,
    pub direction_z: f32,
    pub distance_m: f64,
    pub duration_us: i64,
}

#[spacetimedb::table(accessor = monster_reaction)]
pub struct MonsterReaction {
    #[primary_key]
    pub monster_id: u32,
    pub monster_life_sequence: u32,
    pub phase: u8,
    pub phase_started_at_us: i64,
    pub phase_ends_at_us: i64,
    pub completed_at_tick_us: i64,
}

fn valid_force(distance_m: f64, duration_us: i64, direction_x: f32, direction_z: f32) -> bool {
    distance_m.is_finite()
        && (0.0..=MAX_FORCE_DISTANCE_M).contains(&distance_m)
        && (1..=MAX_FORCE_DURATION_US).contains(&duration_us)
        && direction_x.is_finite()
        && direction_z.is_finite()
        && (direction_x.hypot(direction_z) - 1.0).abs() <= 0.000_1
}

fn ease_out_fraction(elapsed_us: i64, duration_us: i64) -> Option<f64> {
    if !(1..=MAX_FORCE_DURATION_US).contains(&duration_us) {
        return None;
    }
    let t = elapsed_us.clamp(0, duration_us) as f64 / duration_us as f64;
    Some(t * (2.0 - t))
}

fn simulation_elapsed(raw_elapsed_us: i64, duration_us: i64) -> i64 {
    let clamped = raw_elapsed_us.clamp(0, duration_us);
    if clamped == duration_us {
        duration_us
    } else {
        clamped / FORCE_SUBSTEP_US * FORCE_SUBSTEP_US
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct ForceAdvance {
    x: f32,
    z: f32,
    consumed_elapsed_us: i64,
}

#[derive(Clone, Copy, Debug)]
pub struct ForceStart {
    pub source_character: Identity,
    pub source_action_revision: u64,
    pub now: i64,
    pub front: bool,
    pub direction: (f32, f32),
    pub distance_m: f64,
    pub duration_us: i64,
}

fn advance_position(
    position: (f32, f32),
    direction: (f32, f32),
    motion: (f64, i64),
    elapsed: (i64, i64),
    bounds: &[crate::movement::Bounds],
) -> Result<ForceAdvance, String> {
    let (x, z) = position;
    let (direction_x, direction_z) = direction;
    let (distance_m, duration_us) = motion;
    let (consumed_elapsed_us, target_elapsed_us) = elapsed;
    if !x.is_finite()
        || !z.is_finite()
        || !valid_force(distance_m, duration_us, direction_x, direction_z)
        || consumed_elapsed_us < 0
        || consumed_elapsed_us > duration_us
        || target_elapsed_us < consumed_elapsed_us
        || target_elapsed_us > duration_us
    {
        return Err("Monster force advancement state is invalid.".into());
    }
    let mut position = (x, z);
    let mut cursor = consumed_elapsed_us;
    while cursor < target_elapsed_us {
        let next_boundary = cursor
            .checked_div(FORCE_SUBSTEP_US)
            .and_then(|bucket| bucket.checked_add(1))
            .and_then(|bucket| bucket.checked_mul(FORCE_SUBSTEP_US))
            .ok_or("Monster force timestamp is outside the supported range.")?;
        let next = next_boundary.min(target_elapsed_us);
        let before = ease_out_fraction(cursor, duration_us)
            .ok_or("The trusted monster force is invalid.")?;
        let after =
            ease_out_fraction(next, duration_us).ok_or("The trusted monster force is invalid.")?;
        let delta = (after - before) * distance_m;
        let dx = (f64::from(direction_x) * delta) as f32;
        let dz = (f64::from(direction_z) * delta) as f32;
        position = content::slide(position.0, position.1, dx, dz, bounds);
        cursor = next;
    }
    Ok(ForceAdvance {
        x: position.0,
        z: position.1,
        consumed_elapsed_us: cursor,
    })
}

pub(crate) fn force_direction(
    attacker: (f32, f32),
    monster: &crate::combat::Monster,
) -> (f32, f32) {
    let dx = monster.x - attacker.0;
    let dz = monster.z - attacker.1;
    let length = dx.hypot(dz);
    if length > 0.000_1 && length.is_finite() {
        (dx / length, dz / length)
    } else {
        // A zero-radius vector has no authoritative radial direction. Retain
        // damage/reaction and omit force rather than invent client geometry.
        (0.0, 0.0)
    }
}

pub(crate) fn is_front_hit(attacker_heading: f32, victim_heading: f32) -> bool {
    f64::from(attacker_heading - victim_heading).cos() < 0.0
}

fn reaction_definition(
    monster: &crate::combat::Monster,
    phase: u8,
) -> Option<MonsterReactionDefinition> {
    let definition = crate::combat::ordinary_definition(monster).ok()?;
    match phase {
        REACTION_FRONT_KNOCKDOWN => Some(definition.front_knockdown),
        REACTION_FRONT_STANDUP => Some(definition.front_standup),
        REACTION_BACK_KNOCKDOWN => Some(definition.back_knockdown),
        _ => None,
    }
}

fn publish_reaction(
    monster: &mut crate::combat::Monster,
    definition: MonsterReactionDefinition,
    started_at_us: i64,
) -> Result<i64, String> {
    let ends_at_us = started_at_us
        .checked_add(definition.duration_us)
        .ok_or("Monster reaction timestamp is outside the supported range.")?;
    monster.attack_sequence = monster.attack_sequence.wrapping_add(1);
    monster.activity = 2;
    monster.attack_action_id = definition.id.into();
    monster.action_started_at_us = started_at_us;
    monster.action_ends_at_us = ends_at_us;
    Ok(ends_at_us)
}

pub fn clear(ctx: &ReducerContext, monster_id: u32) {
    ctx.db.monster_force().monster_id().delete(monster_id);
    ctx.db.monster_reaction().monster_id().delete(monster_id);
}

fn reaction_is_active(reaction: &MonsterReaction, life_sequence: u32) -> bool {
    reaction.monster_life_sequence == life_sequence && reaction.phase != REACTION_COMPLETE
}

fn reaction_phase_to_start(
    existing: Option<&MonsterReaction>,
    life_sequence: u32,
    front: bool,
) -> Option<u8> {
    if existing.is_some_and(|row| reaction_is_active(row, life_sequence)) {
        None
    } else if front {
        Some(REACTION_FRONT_KNOCKDOWN)
    } else {
        Some(REACTION_BACK_KNOCKDOWN)
    }
}

/// Start a source GREAT reaction and its independent authoritative force.
/// `front` is derived from the accepted attacker/victim headings; no client
/// orientation or destination participates.
pub fn start(
    ctx: &ReducerContext,
    monster: &mut crate::combat::Monster,
    start: ForceStart,
) -> Result<(), String> {
    if crate::training_targets::validate(monster)?.is_some() {
        return Ok(());
    }
    let (direction_x, direction_z) = start.direction;
    let distance_m = start.distance_m;
    let duration_us = start.duration_us;
    let has_direction = direction_x != 0.0 || direction_z != 0.0;
    if start.source_action_revision == 0
        || (has_direction && !valid_force(distance_m, duration_us, direction_x, direction_z))
        || (!has_direction
            && (!distance_m.is_finite()
                || !(0.0..=MAX_FORCE_DISTANCE_M).contains(&distance_m)
                || !(1..=MAX_FORCE_DURATION_US).contains(&duration_us)))
    {
        return Err("The trusted monster force is invalid.".into());
    }
    ctx.db.monster_force().monster_id().delete(monster.id);
    if has_direction {
        ctx.db.monster_force().insert(MonsterForce {
            monster_id: monster.id,
            monster_life_sequence: monster.life_sequence,
            source_character: start.source_character,
            source_action_revision: start.source_action_revision,
            started_at_us: start.now,
            consumed_elapsed_us: 0,
            direction_x,
            direction_z,
            distance_m,
            duration_us,
        });
    }
    let existing_reaction = ctx.db.monster_reaction().monster_id().find(monster.id);
    if let Some(phase) = reaction_phase_to_start(
        existing_reaction.as_ref(),
        monster.life_sequence,
        start.front,
    ) {
        ctx.db.monster_reaction().monster_id().delete(monster.id);
        let ends_at_us = publish_reaction(
            monster,
            reaction_definition(monster, phase)
                .ok_or("The trusted monster reaction is missing.")?,
            start.now,
        )?;
        ctx.db.monster_reaction().insert(MonsterReaction {
            monster_id: monster.id,
            monster_life_sequence: monster.life_sequence,
            phase,
            phase_started_at_us: start.now,
            phase_ends_at_us: ends_at_us,
            completed_at_tick_us: 0,
        });
    }
    Ok(())
}

fn advance_force(ctx: &ReducerContext, force: &mut MonsterForce, now: i64) -> Result<bool, String> {
    let Some(mut victim) = ctx.db.monster().id().find(force.monster_id) else {
        return Ok(false);
    };
    if victim.health == 0
        || victim.life_sequence != force.monster_life_sequence
        || !valid_force(
            force.distance_m,
            force.duration_us,
            force.direction_x,
            force.direction_z,
        )
        || force.started_at_us <= 0
        || force.consumed_elapsed_us < 0
        || force.consumed_elapsed_us > force.duration_us
    {
        return Ok(false);
    }
    let Some(raw_elapsed_us) = now.checked_sub(force.started_at_us) else {
        return Ok(false);
    };
    if raw_elapsed_us < 0 {
        return Ok(false);
    }
    let target_elapsed_us = simulation_elapsed(raw_elapsed_us, force.duration_us);
    let advance = advance_position(
        (victim.x, victim.z),
        (force.direction_x, force.direction_z),
        (force.distance_m, force.duration_us),
        (force.consumed_elapsed_us, target_elapsed_us),
        &collision_bounds(ctx),
    )?;
    victim.x = advance.x;
    victim.z = advance.z;
    victim.y = content::height(victim.x, victim.z);
    force.consumed_elapsed_us = advance.consumed_elapsed_us;
    ctx.db.monster().id().update(victim);
    Ok(force.consumed_elapsed_us < force.duration_us)
}

fn advance_reaction(
    ctx: &ReducerContext,
    reaction: &mut MonsterReaction,
    now: i64,
) -> Result<bool, String> {
    let Some(mut victim) = ctx.db.monster().id().find(reaction.monster_id) else {
        return Ok(false);
    };
    if victim.health == 0 || victim.life_sequence != reaction.monster_life_sequence {
        return Ok(false);
    }
    if reaction.phase == REACTION_COMPLETE {
        if now > reaction.completed_at_tick_us {
            return Ok(false);
        }
        return Ok(true);
    }
    if reaction_definition(&victim, reaction.phase).is_none()
        || reaction.phase_started_at_us <= 0
        || reaction.phase_ends_at_us <= reaction.phase_started_at_us
    {
        return Ok(false);
    }
    if now < reaction.phase_ends_at_us {
        return Ok(true);
    }
    if reaction.phase == REACTION_FRONT_KNOCKDOWN {
        let started_at_us = reaction.phase_ends_at_us;
        let standup = crate::combat::ordinary_definition(&victim)?.front_standup;
        let ends_at_us = publish_reaction(&mut victim, standup, started_at_us)?;
        reaction.phase = REACTION_FRONT_STANDUP;
        reaction.phase_started_at_us = started_at_us;
        reaction.phase_ends_at_us = ends_at_us;
        if now < ends_at_us {
            ctx.db.monster().id().update(victim);
            return Ok(true);
        }
    }
    victim.activity = 0;
    victim.action_started_at_us = 0;
    victim.action_ends_at_us = 0;
    ctx.db.monster().id().update(victim);
    reaction.phase = REACTION_COMPLETE;
    reaction.completed_at_tick_us = now;
    Ok(true)
}

/// Advance every force before area scans and update reaction actions. Returns
/// no public auxiliary state: subscribed monster positions/actions are the
/// complete client contract.
pub fn advance_all(ctx: &ReducerContext, now: i64) -> Result<(), String> {
    let mut ids: Vec<u32> = ctx
        .db
        .monster_force()
        .iter()
        .map(|row| row.monster_id)
        .collect();
    ids.sort_unstable();
    for id in ids {
        let Some(mut force) = ctx.db.monster_force().monster_id().find(id) else {
            continue;
        };
        if advance_force(ctx, &mut force, now)? {
            ctx.db.monster_force().monster_id().update(force);
        } else {
            ctx.db.monster_force().monster_id().delete(id);
        }
    }

    let mut ids: Vec<u32> = ctx
        .db
        .monster_reaction()
        .iter()
        .map(|row| row.monster_id)
        .collect();
    ids.sort_unstable();
    for id in ids {
        let Some(mut reaction) = ctx.db.monster_reaction().monster_id().find(id) else {
            continue;
        };
        if advance_reaction(ctx, &mut reaction, now)? {
            ctx.db.monster_reaction().monster_id().update(reaction);
        } else {
            ctx.db.monster_reaction().monster_id().delete(id);
        }
    }
    Ok(())
}

pub fn locks_ai(ctx: &ReducerContext, monster_id: u32, life_sequence: u32) -> bool {
    ctx.db
        .monster_force()
        .monster_id()
        .find(monster_id)
        .is_some_and(|row| row.monster_life_sequence == life_sequence)
        || ctx
            .db
            .monster_reaction()
            .monster_id()
            .find(monster_id)
            .is_some_and(|row| row.monster_life_sequence == life_sequence)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn open_test_origin() -> (f32, f32) {
        if cfg!(feature = "yongan") {
            (660.0, 575.0)
        } else {
            (0.0, 0.0)
        }
    }

    #[test]
    fn ordinary_force_uses_its_own_endpoint_and_shared_sampling() {
        let origin = open_test_origin();
        let first =
            advance_position(origin, (1.0, 0.0), (3.675, 1_000_000), (0, 500_000), &[]).unwrap();
        assert!((first.x - origin.0 - 3.675 * 0.75).abs() < 0.001);
        let end = advance_position(
            (first.x, first.z),
            (1.0, 0.0),
            (3.675, 1_000_000),
            (500_000, 1_000_000),
            &[],
        )
        .unwrap();
        assert!((end.x - origin.0 - 3.675).abs() < 0.001);
        assert_eq!(end.consumed_elapsed_us, 1_000_000);
    }

    #[test]
    fn analytic_quadratic_ease_out_has_exact_endpoints() {
        assert_eq!(ease_out_fraction(0, 1_000_000), Some(0.0));
        assert_eq!(ease_out_fraction(500_000, 1_000_000), Some(0.75));
        assert_eq!(ease_out_fraction(1_000_000, 1_000_000), Some(1.0));
        assert_eq!(ease_out_fraction(2_000_000, 1_000_000), Some(1.0));
    }

    #[test]
    fn force_sampling_is_canonical_and_bounded() {
        assert_eq!(simulation_elapsed(49_999, 1_000_000), 0);
        assert_eq!(simulation_elapsed(50_000, 1_000_000), 50_000);
        assert_eq!(simulation_elapsed(999_999, 1_000_000), 950_000);
        assert_eq!(simulation_elapsed(1_000_000, 1_000_000), 1_000_000);
        assert!(valid_force(4.732, 1_000_000, 1.0, 0.0));
        assert!(!valid_force(f64::NAN, 1_000_000, 1.0, 0.0));
        assert!(!valid_force(4.732, 0, 1.0, 0.0));
        assert!(!valid_force(4.732, 1_000_000, 0.0, 0.0));
    }

    #[test]
    fn open_force_reaches_derived_endpoint_independent_of_call_partition() {
        let origin = open_test_origin();
        let once =
            advance_position(origin, (1.0, 0.0), (4.732, 1_000_000), (0, 1_000_000), &[]).unwrap();
        let first =
            advance_position(origin, (1.0, 0.0), (4.732, 1_000_000), (0, 350_000), &[]).unwrap();
        let split = advance_position(
            (first.x, first.z),
            (1.0, 0.0),
            (4.732, 1_000_000),
            (first.consumed_elapsed_us, 1_000_000),
            &[],
        )
        .unwrap();
        assert!((once.x - (origin.0 + 4.732)).abs() < 0.001);
        assert!((once.z - origin.1).abs() < 0.000_01);
        assert!((once.x - split.x).abs() < 0.000_01);
        assert_eq!(once.consumed_elapsed_us, 1_000_000);
    }

    #[test]
    #[cfg(not(feature = "yongan"))]
    fn force_collision_consumes_the_blocked_remainder() {
        let origin = open_test_origin();
        let wall = [crate::movement::Bounds {
            min_x: origin.0 + 1.0,
            max_x: origin.0 + 2.0,
            min_z: origin.1 - 1.0,
            max_z: origin.1 + 1.0,
        }];
        let advance = advance_position(
            origin,
            (1.0, 0.0),
            (4.732, 1_000_000),
            (0, 1_000_000),
            &wall,
        )
        .unwrap();
        assert_eq!(advance.x, origin.0 + 1.0);
        assert_eq!(advance.z, origin.1);
        assert_eq!(advance.consumed_elapsed_us, 1_000_000);
        let repeated = advance_position(
            (advance.x, advance.z),
            (1.0, 0.0),
            (4.732, 1_000_000),
            (advance.consumed_elapsed_us, 1_000_000),
            &wall,
        )
        .unwrap();
        assert_eq!(advance, repeated);
    }

    #[test]
    #[cfg(feature = "yongan")]
    fn authored_town_wall_clips_force_and_consumes_the_remainder() {
        let advance = advance_position(
            (640.75, 549.5),
            (1.0, 0.0),
            (4.732, 1_000_000),
            (0, 1_000_000),
            &[],
        )
        .unwrap();
        assert!(advance.x > 641.6 && advance.x < 641.75);
        assert_eq!(advance.z, 549.5);
        assert_eq!(advance.consumed_elapsed_us, 1_000_000);
        let repeated = advance_position(
            (advance.x, advance.z),
            (1.0, 0.0),
            (4.732, 1_000_000),
            (advance.consumed_elapsed_us, 1_000_000),
            &[],
        )
        .unwrap();
        assert_eq!(advance, repeated);
    }

    #[test]
    fn overlapping_great_hit_preserves_an_active_reaction() {
        let active = MonsterReaction {
            monster_id: 2,
            monster_life_sequence: 7,
            phase: REACTION_FRONT_KNOCKDOWN,
            phase_started_at_us: 1_000,
            phase_ends_at_us: 1_001_000,
            completed_at_tick_us: 0,
        };
        assert!(reaction_is_active(&active, 7));
        assert_eq!(reaction_phase_to_start(Some(&active), 7, false), None);
        let published_before = (
            active.phase_started_at_us,
            active.phase_ends_at_us,
            active.phase,
        );
        let replacement_force = MonsterForce {
            monster_id: 2,
            monster_life_sequence: 7,
            source_character: Identity::from_claims("test", "second-attacker"),
            source_action_revision: 9,
            started_at_us: 301_000,
            consumed_elapsed_us: 0,
            direction_x: 1.0,
            direction_z: 0.0,
            distance_m: 4.732,
            duration_us: 1_000_000,
        };
        assert_eq!(replacement_force.source_action_revision, 9);
        assert_eq!(
            (
                active.phase_started_at_us,
                active.phase_ends_at_us,
                active.phase
            ),
            published_before
        );
        assert!(!reaction_is_active(&active, 8));
        assert_eq!(
            reaction_phase_to_start(Some(&active), 8, false),
            Some(REACTION_BACK_KNOCKDOWN)
        );
        let complete = MonsterReaction {
            phase: REACTION_COMPLETE,
            ..active
        };
        assert!(!reaction_is_active(&complete, 7));
    }
}
