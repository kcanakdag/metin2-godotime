//! Fixed skill areas retain exact-life swept samples separately for each event.
use crate::combat::{Monster, monster};
use crate::definitions::SkillHitGeometry;
use crate::skills::{SkillAreaPlacement, SkillAreaVictim, SkillEventTiming};
use spacetimedb::{ReducerContext, Table};

fn sample(ctx: &ReducerContext, monster: &Monster) -> Option<SkillAreaVictim> {
    if monster.health == 0 || crate::combat::validate_monster(ctx, monster).is_err() {
        return None;
    }
    let [center_x, center_y, center_z] = crate::special_area::victim_center(ctx, monster)?;
    Some(SkillAreaVictim {
        monster_id: monster.id,
        life_sequence: monster.life_sequence,
        center_x,
        center_y,
        center_z,
    })
}

pub fn seed(ctx: &ReducerContext) -> Vec<SkillAreaVictim> {
    let mut samples: Vec<_> = ctx
        .db
        .monster()
        .iter()
        .filter_map(|m| sample(ctx, &m))
        .collect();
    samples.sort_by_key(|s| (s.monster_id, s.life_sequence));
    samples
}

fn intersects(
    placement: &SkillAreaPlacement,
    shape: &SkillHitGeometry,
    current: &SkillAreaVictim,
    radius: f64,
) -> Result<bool, String> {
    let center = [current.center_x, current.center_y, current.center_z];
    let previous = placement
        .victims
        .binary_search_by_key(&(current.monster_id, current.life_sequence), |s| {
            (s.monster_id, s.life_sequence)
        })
        .ok()
        .map_or(center, |index| {
            let s = &placement.victims[index];
            [s.center_x, s.center_y, s.center_z]
        });
    Ok(shape.intersects_fixed_area(
        [placement.origin_x, placement.origin_y, placement.origin_z],
        placement.heading,
        previous,
        center,
        radius,
    )?)
}

pub fn candidates(
    ctx: &ReducerContext,
    event: &mut SkillEventTiming,
    shape: &SkillHitGeometry,
    now: i64,
) -> Result<Vec<Monster>, String> {
    let Some(placement) = event.placement.as_mut() else {
        return Ok(Vec::new());
    };
    if crate::area_lifecycle::area_phase(
        now,
        event.starts_at_us,
        event.ends_at_us,
        placement.activated_at_us,
    ) != crate::area_lifecycle::AreaPhase::Scan
    {
        return Ok(Vec::new());
    }
    let mut victims = Vec::new();
    let mut samples = Vec::new();
    for monster in ctx.db.monster().iter() {
        let Some(current) = sample(ctx, &monster) else {
            continue;
        };
        if intersects(
            placement,
            shape,
            &current,
            crate::combat::defending_sphere(ctx, &monster).radius_m,
        )? {
            victims.push(monster);
        }
        samples.push(current);
    }
    samples.sort_by_key(|s| (s.monster_id, s.life_sequence));
    // Drop dead/despawned lives each scan; a new life starts with its current center.
    placement.victims = samples;
    Ok(victims)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::definitions::SkillHitSphere;
    #[test]
    fn crossing_uses_exact_life_and_frozen_origin() {
        let shape = SkillHitGeometry::Area {
            spheres: &[SkillHitSphere {
                position_m: [0.0, 1.0, -2.0],
                radius_m: 1.2,
            }],
        };
        let mut current = SkillAreaVictim {
            monster_id: 1,
            life_sequence: 7,
            center_x: 13.0,
            center_y: 1.0,
            center_z: 18.0,
        };
        let mut previous = current.clone();
        previous.center_x = 7.0;
        let placement = SkillAreaPlacement {
            origin_x: 10.0,
            origin_y: 0.0,
            origin_z: 20.0,
            heading: 0.0,
            activated_at_us: 100,
            victims: vec![previous],
        };
        assert!(intersects(&placement, &shape, &current, 0.4).unwrap());
        current.life_sequence += 1;
        assert!(!intersects(&placement, &shape, &current, 0.4).unwrap());
        current.monster_id = 2;
        current.life_sequence = 7;
        assert!(!intersects(&placement, &shape, &current, 0.4).unwrap());
        current.center_x = 10.0;
        current.center_y = 5.0;
        assert!(!intersects(&placement, &shape, &current, 0.4).unwrap());
        current.center_y = f64::NAN;
        assert!(intersects(&placement, &shape, &current, 0.4).is_err());
    }
}
