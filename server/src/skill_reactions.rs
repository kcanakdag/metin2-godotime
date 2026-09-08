//! Authored skill hit policy; GREAT hits share authoritative force and recovery.
use crate::combat::{Monster, monster_clock};
use crate::definitions::SkillHitReaction;
use spacetimedb::ReducerContext;

/// Source unit-mass/friction endpoint in metres; interpolation remains the shared
/// server ease-out policy, not a claim of exact original physical collision parity.
fn force_distance(force: f64) -> Result<f64, String> {
    if !force.is_finite() || !(0.0..=20.0).contains(&force) {
        return Err("Invalid authored skill force".into());
    }
    let steps = (force / 0.3).floor();
    Ok((steps * force - 0.3 * steps * (steps + 1.0) / 2.0).max(0.0) / 100.0)
}

pub fn apply(
    ctx: &ReducerContext,
    monster: &mut Monster,
    owner: &crate::Player,
    cast: &crate::skills::PendingSkill,
    reaction: &SkillHitReaction,
    now: i64,
) -> Result<(), String> {
    if reaction.hit_type == 2 {
        return crate::knockback::start_good(
            ctx,
            monster,
            crate::knockback::is_front_hit(owner.heading, monster.heading),
            now,
        );
    }
    if reaction.hit_type != 1 {
        return Err("Unsupported skill reaction".into());
    }
    let mut clock = ctx
        .db
        .monster_clock()
        .id()
        .find(monster.id)
        .ok_or("Skill victim clock is missing")?;
    crate::combat::cancel_monster_hit(&mut clock);
    clock.attack_until_us = 0;
    ctx.db.monster_clock().id().update(clock);
    crate::knockback::start(
        ctx,
        monster,
        crate::knockback::ForceStart {
            source_character: cast.character_id,
            source_action_revision: cast.action_revision,
            now,
            front: crate::knockback::is_front_hit(owner.heading, monster.heading),
            direction: crate::knockback::force_direction((owner.x, owner.z), monster),
            distance_m: force_distance(reaction.external_force)?,
            duration_us: 1_000_000,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_force_endpoints_and_invalid_values() {
        for (force, expected) in [
            (0.0, 0.0),
            (0.1, 0.0),
            (5.0, 0.392),
            (15.0, 3.675),
            (17.0, 4.732),
        ] {
            assert!((force_distance(force).unwrap() - expected).abs() < 1e-12);
        }
        for force in [-1.0, 20.1, f64::NAN, f64::INFINITY] {
            assert!(force_distance(force).is_err());
        }
    }
}
