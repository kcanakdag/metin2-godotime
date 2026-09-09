//! Pure movement and collision rules; positions use meters on the X/Z plane.

pub const SPEED: f32 = 5.0;
pub const BASE_SPEED_POINTS: i32 = 100;
pub const HALF_SIZE: f32 = 32.0;
pub const PLAYER_RADIUS: f32 = 0.45;
pub const TRAINING_OBSTACLES: &[(f32, f32, f32, f32, f32, &str)] = &[
    (-8.0, -5.0, 1.6, 1.3, 2.2, "stone"),
    (8.0, -5.0, 1.3, 1.7, 2.7, "stone"),
    (-11.0, 7.0, 3.0, 0.5, 1.2, "wall"),
    (11.0, 7.0, 3.0, 0.5, 1.2, "wall"),
    (0.0, -13.0, 2.0, 1.0, 3.8, "metin"),
];

pub struct Bounds {
    pub min_x: f32,
    pub max_x: f32,
    pub min_z: f32,
    pub max_z: f32,
}

impl Bounds {
    pub fn contains(&self, x: f32, z: f32) -> bool {
        x > self.min_x && x < self.max_x && z > self.min_z && z < self.max_z
    }
}

pub fn valid_direction(x: f32, z: f32) -> Result<(), String> {
    if !x.is_finite() || !z.is_finite() || x.abs() > 1.0 || z.abs() > 1.0 {
        return Err("Direction components must be finite and between -1 and 1.".into());
    }
    Ok(())
}

pub fn valid_target(x: f32, z: f32) -> Result<(), String> {
    let limit = HALF_SIZE - PLAYER_RADIUS;
    if !x.is_finite() || !z.is_finite() || x.abs() > limit || z.abs() > limit {
        return Err("Destination must be finite and inside the map boundary.".into());
    }
    Ok(())
}

/// Original PC MOV_SPEED limit and CalculateDuration integer quantization.
/// Points are server-owned stats, never a value supplied by a movement intent.
fn speed_multiplier(points: i32) -> f32 {
    let points = points.clamp(0, 200);
    let duration_percent = if points < BASE_SPEED_POINTS {
        200 - points
    } else {
        10_000 / points
    };
    100.0 / duration_percent as f32
}

/// A trusted timed speed bonus, projected only after validating its owner lease.
#[derive(Clone, Copy, Debug)]
pub struct SpeedEffect {
    pub starts_at_us: i64,
    pub expires_at_us: i64,
    pub bonus_points: i32,
}

/// Bounded movement allowance shared by held movement and click-to-move.
#[derive(Clone, Copy, Debug)]
pub struct Travel(f32);

impl Travel {
    /// Legacy single-charge test adapter; production combines all trusted intervals.
    #[cfg(test)]
    pub fn tick(
        previous_us: i64,
        now_us: i64,
        blocked_until_us: i64,
        base_points: i32,
        effect: Option<SpeedEffect>,
    ) -> Result<Self, String> {
        if effect.is_some_and(|effect| {
            effect.expires_at_us.saturating_sub(effect.starts_at_us) > 600_000_000
                || !(0..=1000).contains(&effect.bonus_points)
        }) {
            return Err("Invalid timed movement speed effect".into());
        }
        Self::with_effects(
            previous_us,
            now_us,
            blocked_until_us,
            base_points,
            effect.as_slice(),
        )
    }

    /// Sum trusted points per interval before applying the original speed cap.
    pub fn with_effects(
        previous_us: i64,
        now_us: i64,
        blocked_until_us: i64,
        base_points: i32,
        effects: &[SpeedEffect],
    ) -> Result<Self, String> {
        if effects.len() > 256
            || effects.iter().any(|effect| {
                effect.starts_at_us < 0
                    || effect.expires_at_us <= effect.starts_at_us
                    || effect.expires_at_us.saturating_sub(effect.starts_at_us) > 86_400_000_000
                    || !(-100_000..=100_000).contains(&effect.bonus_points)
            })
        {
            return Err("Invalid timed movement speed effects".into());
        }
        // Only the latest 100 ms can grant travel after a stalled simulation.
        // In particular, an old expired charge cannot be banked until this tick.
        let start = previous_us
            .max(blocked_until_us)
            .max(now_us.saturating_sub(100_000));
        if previous_us < 0 || now_us <= start || now_us < 0 {
            return Ok(Self(0.0));
        }
        let mut boundaries = vec![start, now_us];
        for effect in effects {
            for boundary in [effect.starts_at_us, effect.expires_at_us] {
                if boundary > start && boundary < now_us {
                    boundaries.push(boundary);
                }
            }
        }
        boundaries.sort_unstable();
        boundaries.dedup();
        let mut distance = 0.0_f64;
        for interval in boundaries.windows(2) {
            let bonus: i32 = effects
                .iter()
                .filter(|effect| {
                    effect.starts_at_us <= interval[0] && effect.expires_at_us > interval[0]
                })
                .map(|effect| effect.bonus_points)
                .sum();
            distance += f64::from(SPEED)
                * (interval[1] - interval[0]) as f64
                * f64::from(speed_multiplier(base_points.saturating_add(bonus)))
                / 1_000_000.0;
        }
        Ok(Self(distance as f32))
    }
}

pub fn step(x: f32, z: f32, travel: Travel) -> Result<(f32, f32), String> {
    valid_direction(x, z)?;
    let magnitude = x.hypot(z).max(1.0);
    Ok((x / magnitude * travel.0, z / magnitude * travel.0))
}

pub fn target_step(x: f32, z: f32, target_x: f32, target_z: f32, travel: Travel) -> (f32, f32) {
    let dx = target_x - x;
    let dz = target_z - z;
    let length = dx.hypot(dz);
    if length < 0.02 {
        return (0.0, 0.0);
    }
    let travel = travel.0.min(length);
    (dx / length * travel, dz / length * travel)
}

/// Resolve each axis against the entire swept segment, then slide on the other axis.
pub fn slide(x: f32, z: f32, dx: f32, dz: f32, obstacles: &[Bounds]) -> (f32, f32) {
    let limit = HALF_SIZE - PLAYER_RADIUS;
    let mut new_x = (x + dx).clamp(-limit, limit);
    for bounds in obstacles {
        if z <= bounds.min_z || z >= bounds.max_z {
            continue;
        }
        if dx > 0.0 && x <= bounds.min_x && new_x > bounds.min_x {
            new_x = bounds.min_x;
        } else if dx < 0.0 && x >= bounds.max_x && new_x < bounds.max_x {
            new_x = bounds.max_x;
        }
    }
    let mut new_z = (z + dz).clamp(-limit, limit);
    for bounds in obstacles {
        if new_x <= bounds.min_x || new_x >= bounds.max_x {
            continue;
        }
        if dz > 0.0 && z <= bounds.min_z && new_z > bounds.min_z {
            new_z = bounds.min_z;
        } else if dz < 0.0 && z >= bounds.max_z && new_z < bounds.max_z {
            new_z = bounds.max_z;
        }
    }
    (new_x, new_z)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overlapping_buff_and_charge_sum_points_before_cap_at_each_boundary() {
        let effects = [
            SpeedEffect {
                starts_at_us: 1_000_000,
                expires_at_us: 1_060_000,
                bonus_points: 20,
            },
            SpeedEffect {
                starts_at_us: 1_040_000,
                expires_at_us: 2_000_000,
                bonus_points: 150,
            },
        ];
        let travel = Travel::with_effects(1_000_000, 1_100_000, 0, 100, &effects).unwrap();
        let expected = SPEED * (0.04 * speed_multiplier(120) + 0.06 * speed_multiplier(200));
        assert!((travel.0 - expected).abs() < 0.000001);
        let reversed = [effects[1], effects[0]];
        assert_eq!(
            travel.0,
            Travel::with_effects(1_000_000, 1_100_000, 0, 100, &reversed)
                .unwrap()
                .0
        );
        let blocked = Travel::with_effects(1_000_000, 1_100_000, 1_050_000, 100, &effects).unwrap();
        assert!((blocked.0 - 0.5).abs() < 0.000001);
    }

    #[test]
    fn buff_movement_never_banks_expired_or_future_intervals() {
        let effects = [SpeedEffect {
            starts_at_us: 2_000_000,
            expires_at_us: 3_000_000,
            bonus_points: 20,
        }];
        for (previous, now) in [(0, 1_000_000), (1_000_000, 4_000_000)] {
            assert_eq!(
                Travel::with_effects(previous, now, 0, 100, &effects)
                    .unwrap()
                    .0,
                0.5
            );
        }
        let too_many = vec![effects[0]; 257];
        assert!(Travel::with_effects(0, 1, 0, 100, &too_many).is_err());
    }

    #[test]
    fn timed_speed_counts_only_overlap_after_attack_recovery() {
        let start = 1_000_000;
        let now = start + 50_000;
        for (a, b, blocked, expected) in [
            (0, 25_000, 0, 0.375),
            (25_000, 50_000, 0, 0.375),
            (10_000, 30_000, 0, 0.35),
            (0, 50_000, 0, 0.5),
            (50_000, 60_000, 0, 0.25),
            (-10_000, 0, 0, 0.25),
            (0, 25_000, 25_000, 0.125),
            (0, 50_000, 25_000, 0.25),
            (0, 50_000, 50_000, 0.0),
        ] {
            let effect = SpeedEffect {
                starts_at_us: start + a,
                expires_at_us: start + b,
                bonus_points: 150,
            };
            let travel = Travel::tick(start, now, start + blocked, 100, Some(effect)).unwrap();
            let (distance, _) = step(1.0, 0.0, travel).unwrap();
            assert!(
                (distance - expected).abs() < 0.000001,
                "{a}..{b}, blocked={blocked}: {distance}"
            );
            let (dx, dz) = step(1.0, 1.0, travel).unwrap();
            assert!((dx.hypot(dz) - expected).abs() < 0.000001);
            assert_eq!(target_step(0.0, 0.0, 10.0, 0.0, travel), (distance, 0.0));
        }
    }

    #[test]
    fn stalled_ticks_do_not_bank_expired_speed_bonuses() {
        let now = 5_000_000;
        for (expiry, expected) in [(4_900_000, 0.5), (4_950_000, 0.75), (5_000_000, 1.0)] {
            let effect = SpeedEffect {
                starts_at_us: 4_000_000,
                expires_at_us: expiry,
                bonus_points: 150,
            };
            let travel = Travel::tick(0, now, 0, 100, Some(effect)).unwrap();
            assert_eq!(step(1.0, 0.0, travel).unwrap(), (expected, 0.0));
            assert_eq!(slide(0.9, 0.0, travel.0, 0.0, &wall()), (1.0, 0.0));
            assert_eq!(target_step(0.0, 0.0, 0.1, 0.0, travel), (0.1, 0.0));
        }
    }

    #[test]
    fn splitting_a_normal_tick_at_expiry_preserves_total_travel() {
        let effect = SpeedEffect {
            starts_at_us: 1_000_000,
            expires_at_us: 1_025_000,
            bonus_points: 150,
        };
        let distance = |start, end| Travel::tick(start, end, 0, 100, Some(effect)).unwrap().0;
        assert_eq!(
            distance(1_000_000, 1_050_000),
            distance(1_000_000, 1_025_000) + distance(1_025_000, 1_050_000)
        );
    }

    #[test]
    fn clock_extremes_and_invalid_effects_never_grant_unbounded_travel() {
        assert_eq!(Travel::tick(0, i64::MAX, 0, i32::MAX, None).unwrap().0, 1.0);
        assert_eq!(Travel::tick(i64::MAX, 0, 0, 100, None).unwrap().0, 0.0);
        assert_eq!(Travel::tick(-1, 50_000, 0, 100, None).unwrap().0, 0.0);
        assert_eq!(Travel::tick(0, -1, 0, 100, None).unwrap().0, 0.0);
        let base = SpeedEffect {
            starts_at_us: 0,
            expires_at_us: 100_000,
            bonus_points: 150,
        };
        for bad in [
            SpeedEffect {
                starts_at_us: -1,
                ..base
            },
            SpeedEffect {
                expires_at_us: 0,
                ..base
            },
            SpeedEffect {
                expires_at_us: 600_000_001,
                ..base
            },
            SpeedEffect {
                bonus_points: -1,
                ..base
            },
            SpeedEffect {
                bonus_points: 1001,
                ..base
            },
        ] {
            assert!(Travel::tick(0, 50_000, 0, 100, Some(bad)).is_err());
        }
        assert_eq!(
            Travel::tick(0, 100_000, 0, i32::MAX, Some(base)).unwrap().0,
            1.0
        );
    }
    fn travel(elapsed: f32, points: i32) -> Travel {
        assert!(elapsed.is_finite());
        Travel::tick(
            0,
            (f64::from(elapsed) * 1_000_000.0).round() as i64,
            0,
            points,
            None,
        )
        .unwrap()
    }
    #[test]
    fn original_player_speed_uses_capped_quantized_duration() {
        // Source CalculateDuration uses integer division, including above 100.
        for (points, duration) in [(0, 200), (50, 150), (100, 100), (150, 66), (200, 50)] {
            assert!((speed_multiplier(points) - 100.0 / duration as f32).abs() < 0.00001);
        }
        assert_eq!(speed_multiplier(i32::MIN), 0.5);
        assert_eq!(speed_multiplier(i32::MAX), 2.0);
        assert_eq!(
            step(1.0, 0.0, travel(0.1, BASE_SPEED_POINTS + 150)).unwrap(),
            (1.0, 0.0)
        );
    }

    #[test]
    fn boosted_movement_preserves_input_time_and_collision_limits() {
        let boosted = BASE_SPEED_POINTS + 150;
        let (dx, dz) = step(1.0, 1.0, travel(3600.0, boosted)).unwrap();
        assert!((dx.hypot(dz) - 1.0).abs() < 0.00001);
        assert_eq!(step(0.5, 0.0, travel(0.1, boosted)).unwrap(), (0.5, 0.0));
        assert!(step(f32::NAN, 0.0, travel(0.1, boosted)).is_err());
        assert!(step(2.0, 0.0, travel(0.1, boosted)).is_err());
        let (dx, dz) = step(1.0, 0.0, travel(0.1, boosted)).unwrap();
        assert_eq!(slide(0.75, 0.0, dx, dz, &wall()), (1.0, 0.0));
        assert_eq!(
            target_step(0.0, 0.0, 0.25, 0.0, travel(0.1, boosted)),
            (0.25, 0.0)
        );
        let (dx, dz) = target_step(0.0, 0.0, 10.0, 10.0, travel(3600.0, boosted));
        assert!((dx.hypot(dz) - 1.0).abs() < 0.00001);
    }

    fn wall() -> [Bounds; 1] {
        [Bounds {
            min_x: 1.0,
            max_x: 2.0,
            min_z: -3.0,
            max_z: 3.0,
        }]
    }
    #[test]
    fn diagonal_movement_has_no_speed_bonus() {
        let (x, z) = step(1.0, 1.0, travel(0.1, BASE_SPEED_POINTS)).unwrap();
        assert!((x.hypot(z) - 0.5).abs() < 0.00001);
        assert_eq!(
            step(0.5, 0.0, travel(0.1, BASE_SPEED_POINTS)).unwrap(),
            (0.25, 0.0)
        );
    }
    #[test]
    fn stalled_tick_cannot_bank_elapsed_time() {
        assert_eq!(
            step(1.0, 0.0, travel(3600.0, BASE_SPEED_POINTS)).unwrap(),
            (0.5, 0.0)
        );
        assert_eq!(
            step(1.0, 0.0, travel(-1.0, BASE_SPEED_POINTS)).unwrap(),
            (0.0, 0.0)
        );
    }
    #[test]
    fn rejects_nonfinite_and_out_of_range_input() {
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, 2.0, -2.0] {
            assert!(step(value, 0.0, travel(0.1, BASE_SPEED_POINTS)).is_err());
            assert!(step(0.0, value, travel(0.1, BASE_SPEED_POINTS)).is_err());
        }
        for value in [f32::NAN, f32::INFINITY, 32.0, -32.0] {
            assert!(valid_target(value, 0.0).is_err());
            assert!(valid_target(0.0, value).is_err());
        }
    }
    #[test]
    fn map_boundary_accounts_for_player_radius() {
        let limit = HALF_SIZE - PLAYER_RADIUS;
        assert_eq!(slide(31.5, -31.5, 0.5, -0.5, &[]), (limit, -limit));
    }
    #[test]
    fn swept_collision_prevents_tunneling_and_preserves_slide() {
        assert_eq!(slide(0.0, 0.0, 5.0, 0.0, &wall()), (1.0, 0.0));
        assert_eq!(slide(3.0, 0.0, -5.0, 0.0, &wall()), (2.0, 0.0));
        assert_eq!(slide(0.9, 0.0, 0.3, 0.3, &wall()), (1.0, 0.3));
        assert_eq!(slide(1.5, -4.0, 0.0, 5.0, &wall()), (1.5, -3.0));
        assert_eq!(slide(1.5, 4.0, 0.0, -5.0, &wall()), (1.5, 3.0));
    }
    #[test]
    fn click_target_stops_without_overshooting() {
        let (dx, dz) = target_step(0.0, 0.0, 0.1, 0.1, travel(0.1, BASE_SPEED_POINTS));
        assert!((dx - 0.1).abs() < 0.00001);
        assert!((dz - 0.1).abs() < 0.00001);
        assert_eq!(
            target_step(0.0, 0.0, 0.0, 0.0, travel(0.1, BASE_SPEED_POINTS)),
            (0.0, 0.0)
        );
    }
}
