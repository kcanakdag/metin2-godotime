//! Original CRUSH eligibility; database ownership and collision remain adapter work.

#[derive(Clone, Copy, Debug)]
pub struct Victim {
    pub no_move: bool,
    pub main_target: bool,
    pub already_stunned: bool,
    pub stun_immune: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Outcome {
    pub push_distance_m: f32,
    pub stun_duration_us: i64,
}

/// Compute the source-style integer-centimetre destination, then sweep through
/// the authoritative map collision. Coincident actors have no radial direction.
pub fn displace(
    attacker: [f32; 2],
    victim: [f32; 2],
    distance_m: f32,
    bounds: &[crate::movement::Bounds],
) -> Result<[f32; 2], String> {
    if !attacker
        .into_iter()
        .chain(victim)
        .all(|v| v.is_finite() && v.abs() <= 20_000_000.0)
        || !distance_m.is_finite()
        || !(0.0..=8.0).contains(&distance_m)
    {
        return Err("Invalid CRUSH displacement geometry".into());
    }
    let dx = f64::from(victim[0]) - f64::from(attacker[0]);
    let dz = f64::from(victim[1]) - f64::from(attacker[1]);
    let length = dx.hypot(dz);
    if length == 0.0 || distance_m == 0.0 {
        return Ok(victim);
    }
    let destination = [
        ((f64::from(victim[0]) + dx / length * f64::from(distance_m)) * 100.0).trunc() / 100.0,
        ((f64::from(victim[1]) + dz / length * f64::from(distance_m)) * 100.0).trunc() / 100.0,
    ];
    let (x, z) = crate::content::slide(
        victim[0],
        victim[1],
        destination[0] as f32 - victim[0],
        destination[1] as f32 - victim[1],
        bounds,
    );
    Ok([x, z])
}

/// The immunity roll is server-generated, inclusive 1..=100, never a client intent.
/// Horse Wild Attack's special direction is outside this distance/affect policy.
pub fn resolve(
    attacker_is_player: bool,
    long: bool,
    victim: Victim,
    immunity_roll: u8,
) -> Result<Outcome, String> {
    if !(1..=100).contains(&immunity_roll) {
        return Err("Invalid CRUSH immunity roll".into());
    }
    if victim.no_move {
        return Ok(Outcome {
            push_distance_m: 0.0,
            stun_duration_us: 0,
        });
    }
    let immune = victim.stun_immune && immunity_roll <= 90;
    Ok(Outcome {
        push_distance_m: (if attacker_is_player { 2.0 } else { 4.0 })
            * (if long { 2.0 } else { 1.0 }),
        stun_duration_us: if attacker_is_player
            && victim.main_target
            && !victim.already_stunned
            && !immune
        {
            4_000_000
        } else {
            0
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn main_target() -> Victim {
        Victim {
            no_move: false,
            main_target: true,
            already_stunned: false,
            stun_immune: false,
        }
    }

    #[test]
    #[cfg(not(feature = "yongan"))]
    fn radial_push_sweeps_walls_and_truncates_centimetres() {
        assert_eq!(
            displace([-1.0, 0.0], [0.0, 0.0], 2.0, &[]).unwrap(),
            [2.0, 0.0]
        );
        let diagonal = displace([-1.0, -1.0], [0.0; 2], 2.0, &[]).unwrap();
        assert!((diagonal[0] - 1.41).abs() < 0.00001);
        assert!((diagonal[1] - 1.41).abs() < 0.00001);
        let wall = [crate::movement::Bounds {
            min_x: 1.0,
            max_x: 1.1,
            min_z: -1.0,
            max_z: 1.0,
        }];
        let stopped = displace([-1.0, 0.0], [0.0; 2], 8.0, &wall).unwrap();
        assert_eq!(stopped, [1.0, 0.0]);
    }

    #[test]
    fn displacement_rejects_nonfinite_and_excessive_inputs() {
        for bad in [f32::NAN, f32::INFINITY, f32::MAX] {
            assert!(displace([bad, 0.0], [0.0; 2], 2.0, &[]).is_err());
            assert!(displace([0.0; 2], [0.0, bad], 2.0, &[]).is_err());
        }
        for bad in [-1.0, 8.01, f32::NAN, f32::INFINITY] {
            assert!(displace([0.0; 2], [1.0; 2], bad, &[]).is_err());
        }
        assert_eq!(displace([0.0; 2], [0.0; 2], 2.0, &[]).unwrap(), [0.0; 2]);
        assert_eq!(displace([0.0; 2], [1.0; 2], 0.0, &[]).unwrap(), [1.0; 2]);
    }

    #[test]
    fn source_distance_depends_on_attacker_and_long_flag() {
        for (player, long, distance) in [
            (true, false, 2.0),
            (true, true, 4.0),
            (false, false, 4.0),
            (false, true, 8.0),
        ] {
            let outcome = resolve(player, long, main_target(), 1).unwrap();
            assert_eq!(outcome.push_distance_m, distance);
            assert_eq!(outcome.stun_duration_us, if player { 4_000_000 } else { 0 });
        }
    }

    #[test]
    fn no_move_skips_both_push_and_stun() {
        let victim = Victim {
            no_move: true,
            ..main_target()
        };
        assert_eq!(
            resolve(true, true, victim, 100).unwrap(),
            Outcome {
                push_distance_m: 0.0,
                stun_duration_us: 0,
            }
        );
    }

    #[test]
    fn secondary_targets_and_existing_stuns_are_not_stunned_or_refreshed() {
        for victim in [
            Victim {
                main_target: false,
                ..main_target()
            },
            Victim {
                already_stunned: true,
                ..main_target()
            },
        ] {
            let outcome = resolve(true, false, victim, 100).unwrap();
            assert_eq!(outcome.stun_duration_us, 0);
            assert_eq!(outcome.push_distance_m, 2.0);
        }
    }

    #[test]
    fn immunity_blocks_ninety_percent_without_blocking_push() {
        let victim = Victim {
            stun_immune: true,
            ..main_target()
        };
        for roll in 1..=100 {
            let outcome = resolve(true, false, victim, roll).unwrap();
            assert_eq!(
                outcome.stun_duration_us,
                if roll <= 90 { 0 } else { 4_000_000 }
            );
            assert_eq!(outcome.push_distance_m, 2.0);
            assert_eq!(
                resolve(true, false, main_target(), roll)
                    .unwrap()
                    .stun_duration_us,
                4_000_000
            );
        }
        assert!(resolve(true, false, victim, 0).is_err());
        assert!(resolve(true, false, victim, 101).is_err());
    }
}
