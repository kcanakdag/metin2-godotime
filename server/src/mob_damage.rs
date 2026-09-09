//! Original ordinary-NPC damage dispatch after CalcMeleeDamage.
//! No player bow/skill formula: callers supply trusted NPC damage and defenses.
//! Party, magic-attack, affect, penetration resistance and hit/skill bonus stages remain zero
//! in the installed policy. Extend that policy before enabling those modifiers.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Kind {
    Normal,
    NormalRange,
    Magic,
}

/// Resistances apply before critical doubling. Magic alone repeats the low floor
/// from CalcMagicDamageWithValue, even if CalcMeleeDamage already drew a floor.
/// Draws are requested only when the original branch consumes randomness.
pub fn finish(
    kind: Kind,
    melee_damage: u16,
    resistance: u8,
    critical_percent: u8,
    draw: impl FnMut(u8, u8) -> u8,
) -> Result<u16, String> {
    finish_with_penetration(
        kind,
        melee_damage,
        resistance,
        critical_percent,
        Penetration::default(),
        draw,
    )
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Penetration {
    pub percent: u8,
    // Authoritative defense grade after defense-percent adjustment, excluding
    // NPC-attacker marriage defense. Added after critical, never doubled by it.
    pub defense: u16,
}

pub fn finish_with_penetration(
    kind: Kind,
    melee_damage: u16,
    resistance: u8,
    critical_percent: u8,
    penetration: Penetration,
    draw: impl FnMut(u8, u8) -> u8,
) -> Result<u16, String> {
    finish_with_affects(
        kind,
        melee_damage,
        resistance,
        critical_percent,
        penetration,
        0,
        draw,
    )
}

pub fn finish_with_affects(
    kind: Kind,
    melee_damage: u16,
    resistance: u8,
    critical_percent: u8,
    penetration: Penetration,
    normal_damage_taken_percent: i32,
    mut draw: impl FnMut(u8, u8) -> u8,
) -> Result<u16, String> {
    if resistance > 100
        || critical_percent > 100
        || penetration.percent > 100
        || (kind == Kind::Normal && resistance != 0)
        || !(0..=100_000).contains(&normal_damage_taken_percent)
    {
        return Err("Invalid ordinary mob damage modifiers.".into());
    }
    let mut damage = u32::from(melee_damage);
    if kind == Kind::Magic && damage < 3 {
        damage = u32::from(checked_draw(&mut draw, 1, 5)?);
    }
    damage = damage * u32::from(100 - resistance) / 100;
    if kind != Kind::Magic {
        // JEONGWIHON precedes normal-hit critical and penetration. Magic skips it.
        damage =
            u32::try_from(u64::from(damage) * (100 + normal_damage_taken_percent as u64) / 100)
                .map_err(|_| "Ordinary damage affect overflow")?;
    }
    if critical_percent != 0 {
        let chance = proc_chance(kind, critical_percent);
        // A nonzero source percentage still draws when its reduced chance is 0.
        if checked_draw(&mut draw, 1, 100)? <= chance {
            damage *= 2;
        }
    }
    if penetration.percent != 0
        && checked_draw(&mut draw, 1, 100)? <= proc_chance(kind, penetration.percent)
    {
        damage += u32::from(penetration.defense);
    }
    u16::try_from(damage).map_err(|_| "Ordinary mob damage exceeds the supported range.".into())
}

fn proc_chance(kind: Kind, percent: u8) -> u8 {
    match kind {
        Kind::Magic if percent >= 10 => 5 + (percent - 10) / 4,
        Kind::Magic => percent / 2,
        _ => percent,
    }
}

fn checked_draw(draw: &mut impl FnMut(u8, u8) -> u8, low: u8, high: u8) -> Result<u8, String> {
    let value = draw(low, high);
    if !(low..=high).contains(&value) {
        return Err("Ordinary mob damage RNG returned an out-of-range value.".into());
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn berserk_penalty_truncates_before_critical_and_never_boosts_penetration_or_magic() {
        for kind in [Kind::Normal, Kind::NormalRange, Kind::Magic] {
            let result = finish_with_affects(
                kind,
                37,
                0,
                100,
                Penetration {
                    percent: 100,
                    defense: 11,
                },
                12,
                |_, _| 1,
            )
            .unwrap();
            assert_eq!(result, if kind == Kind::Magic { 85 } else { 93 });
        }
        assert!(
            finish_with_affects(
                Kind::Normal,
                u16::MAX,
                0,
                0,
                Penetration::default(),
                100_000,
                |_, _| panic!("no RNG needed")
            )
            .is_err()
        );
        assert!(
            finish_with_affects(
                Kind::Normal,
                1,
                0,
                0,
                Penetration::default(),
                -1,
                |_, _| panic!("invalid inputs must not draw")
            )
            .is_err()
        );
    }

    #[test]
    fn penetration_adds_defense_after_resistance_and_critical() {
        for kind in [Kind::NormalRange, Kind::Magic] {
            let mut draws = 0;
            let result = finish_with_penetration(
                kind,
                37,
                50,
                100,
                Penetration {
                    percent: 100,
                    defense: 11,
                },
                |lo, hi| {
                    assert_eq!((lo, hi), (1, 100));
                    draws += 1;
                    1
                },
            )
            .unwrap();
            assert_eq!(result, 47); // 37 -> 18 -> 36 -> 47; defense is not doubled.
            assert_eq!(draws, 2);
        }
    }

    #[test]
    fn original_one_percent_magic_penetration_draws_but_cannot_proc() {
        for kind in [Kind::Normal, Kind::NormalRange, Kind::Magic] {
            let mut hits = 0;
            let mut draws = 0;
            for roll in 1..=100 {
                let result = finish_with_penetration(
                    kind,
                    30,
                    0,
                    0,
                    Penetration {
                        percent: 1,
                        defense: 10,
                    },
                    |_, _| {
                        draws += 1;
                        roll
                    },
                )
                .unwrap();
                hits += usize::from(result == 40);
            }
            assert_eq!(draws, 100);
            assert_eq!(hits, if kind == Kind::Magic { 0 } else { 1 });
        }
    }

    #[test]
    fn penetration_rejects_invalid_inputs_and_overflow() {
        assert!(
            finish_with_penetration(
                Kind::Normal,
                30,
                0,
                0,
                Penetration {
                    percent: 101,
                    defense: 10
                },
                |_, _| panic!("invalid input drew RNG")
            )
            .is_err()
        );
        assert!(
            finish_with_penetration(
                Kind::Normal,
                u16::MAX,
                0,
                0,
                Penetration {
                    percent: 100,
                    defense: 1
                },
                |_, _| 1
            )
            .is_err()
        );
        assert!(
            finish_with_penetration(
                Kind::Magic,
                30,
                0,
                0,
                Penetration {
                    percent: 1,
                    defense: 10
                },
                |_, _| 0
            )
            .is_err()
        );
    }

    #[test]
    fn magic_critical_uses_reduced_probability_but_range_uses_full_probability() {
        for (percent, magic_chance) in [
            (1, 0),
            (9, 4),
            (10, 5),
            (13, 5),
            (14, 6),
            (50, 15),
            (100, 27),
        ] {
            for kind in [Kind::Normal, Kind::NormalRange, Kind::Magic] {
                let doubled = (1..=100)
                    .filter(|&roll| {
                        finish(kind, 37, 0, percent, |lo, hi| {
                            assert_eq!((lo, hi), (1, 100));
                            roll
                        })
                        .unwrap()
                            == 74
                    })
                    .count();
                assert_eq!(
                    doubled,
                    usize::from(if kind == Kind::Magic {
                        magic_chance
                    } else {
                        percent
                    })
                );
            }
        }
    }

    #[test]
    fn magic_second_floor_precedes_resistance_and_critical() {
        let mut requests = Vec::new();
        let result = finish(Kind::Magic, 1, 25, 10, |lo, hi| {
            requests.push((lo, hi));
            if hi == 5 { 5 } else { 1 }
        })
        .unwrap();
        assert_eq!(requests, [(1, 5), (1, 100)]);
        assert_eq!(result, 6); // floor 5 -> resisted 3 -> critical 6
        assert_eq!(
            finish(Kind::NormalRange, 1, 25, 0, |_, _| panic!(
                "unexpected draw"
            ))
            .unwrap(),
            0
        );
        for damage in [0, 1, 2] {
            for roll in 1..=5 {
                assert_eq!(
                    finish(Kind::Magic, damage, 0, 0, |_, hi| {
                        assert_eq!(hi, 5);
                        roll
                    })
                    .unwrap(),
                    u16::from(roll)
                );
            }
        }
        assert_eq!(
            finish(Kind::Magic, 3, 0, 0, |_, _| panic!("unexpected floor")).unwrap(),
            3
        );
    }

    #[test]
    fn resistance_rounds_before_doubling_and_does_not_add_a_floor() {
        assert_eq!(
            finish(Kind::NormalRange, 37, 50, 100, |_, _| 1).unwrap(),
            36
        );
        for kind in [Kind::NormalRange, Kind::Magic] {
            assert_eq!(
                finish(kind, 37, 100, 0, |_, _| panic!("unexpected draw")).unwrap(),
                0
            );
        }
    }

    #[test]
    fn invalid_inputs_reject_without_rng_and_overflow_never_wraps() {
        for (kind, resistance, critical) in [
            (Kind::Normal, 1, 0),
            (Kind::Magic, 101, 0),
            (Kind::NormalRange, 0, 101),
        ] {
            assert!(
                finish(kind, 37, resistance, critical, |_, _| panic!(
                    "invalid request drew RNG"
                ))
                .is_err()
            );
        }
        assert!(finish(Kind::Magic, 1, 0, 0, |_, _| 6).is_err());
        assert!(finish(Kind::NormalRange, 37, 0, 1, |_, _| 0).is_err());
        assert!(finish(Kind::Normal, u16::MAX, 0, 100, |_, _| 1).is_err());
    }
}
