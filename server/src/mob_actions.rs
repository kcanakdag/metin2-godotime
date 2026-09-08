//! Authoritative weighted ordinary-mob actions, selected once per accepted attack.
use crate::definitions::{AttackDefinition, MobDefinition, WeightedMobAttack};

fn validate(definition: &MobDefinition) -> Result<(), String> {
    let rows = definition.attacks;
    if rows.is_empty()
        || rows.len() > 16
        || !definition.attack_range_m.is_finite()
        || definition.attack_range_m <= 0.0
        || definition.attack_range_m > 100.0
    {
        return Err("Invalid mob attack registry bounds".into());
    }
    let mut total = 0_u16;
    for (index, row) in rows.iter().enumerate() {
        let a = row.attack;
        if row.weight == 0
            || row.weight > 100
            || rows[..index].iter().any(|other| other.attack.id == a.id)
            || !a
                .id
                .strip_prefix(definition.actor_id)
                .is_some_and(|suffix| suffix.starts_with(".general.normal_attack"))
            || a.duration_us <= 0
            || a.duration_us > 60_000_000
            || a.cooldown_us <= 0
            || a.cooldown_us > 60_000_000
            || a.hit_start_us < 0
            || a.hit_end_us <= a.hit_start_us
            || a.hit_end_us > a.duration_us
            || a.range_m != definition.attack_range_m
            || a.combo_input.is_some()
            || a.root_motion.is_some()
            || a.special_area.is_some()
            || a.screen_wave.is_some()
            || a.ordinary_knockback.is_some()
        {
            return Err("Invalid or unsupported ordinary mob attack".into());
        }
        total += u16::from(row.weight);
    }
    if total != 100 {
        return Err("Mob attack weights must total 100".into());
    }
    Ok(())
}

pub fn select(definition: &MobDefinition, roll: u8) -> Result<AttackDefinition, String> {
    validate(definition)?;
    if !(1..=100).contains(&roll) {
        return Err("Mob action roll is outside 1..100".into());
    }
    let mut cumulative = 0_u16;
    for WeightedMobAttack { attack, weight } in definition.attacks {
        cumulative += u16::from(*weight);
        if u16::from(roll) <= cumulative {
            return Ok(*attack);
        }
    }
    Err("No mob action covers the accepted roll".into())
}

pub fn by_id(definition: &MobDefinition, id: &str) -> Result<AttackDefinition, String> {
    validate(definition)?;
    definition
        .attacks
        .iter()
        .find(|row| row.attack.id == id)
        .map(|row| row.attack)
        .ok_or("Accepted mob action is not registered for its species".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::definitions;

    const FIRST: AttackDefinition = definitions::MOB_ATTACK;
    const SECOND: AttackDefinition = AttackDefinition {
        id: "actor.mob.wild-dog-101.general.normal_attack.v2",
        duration_us: 1_333_333,
        hit_start_us: 483_374,
        hit_end_us: 577_453,
        ..FIRST
    };
    const VARIANTS: &[WeightedMobAttack] = &[
        WeightedMobAttack {
            attack: FIRST,
            weight: 50,
        },
        WeightedMobAttack {
            attack: SECOND,
            weight: 50,
        },
    ];

    #[test]
    fn every_weighted_roll_keeps_its_own_identity_and_hit_window() {
        let mob = MobDefinition {
            attacks: VARIANTS,
            ..definitions::MOB_DEFINITIONS[0]
        };
        for roll in 1..=100 {
            let selected = select(&mob, roll).unwrap();
            let expected = if roll <= 50 { FIRST } else { SECOND };
            assert_eq!(selected.id, expected.id);
            assert_eq!(selected.hit_start_us, expected.hit_start_us);
            assert_eq!(selected.hit_end_us, expected.hit_end_us);
            assert_eq!(
                by_id(&mob, selected.id).unwrap().duration_us,
                expected.duration_us
            );
        }
        assert!(select(&mob, 0).is_err());
        assert!(by_id(&mob, "actor.mob.wolf-102.general.normal_attack.v1").is_err());
    }

    #[test]
    fn incomplete_duplicate_and_out_of_clip_actions_reject() {
        const BAD: &[&[WeightedMobAttack]] = &[
            &[],
            &[WeightedMobAttack {
                attack: FIRST,
                weight: 50,
            }],
            &[
                WeightedMobAttack {
                    attack: FIRST,
                    weight: 100,
                },
                WeightedMobAttack {
                    attack: SECOND,
                    weight: 0,
                },
            ],
            &[
                WeightedMobAttack {
                    attack: FIRST,
                    weight: 50,
                },
                WeightedMobAttack {
                    attack: FIRST,
                    weight: 50,
                },
            ],
            &[WeightedMobAttack {
                attack: AttackDefinition {
                    hit_end_us: 2_000_000,
                    ..FIRST
                },
                weight: 100,
            }],
        ];
        for rows in BAD {
            let mob = MobDefinition {
                attacks: rows,
                ..definitions::MOB_DEFINITIONS[0]
            };
            assert!(select(&mob, 1).is_err());
            assert!(by_id(&mob, FIRST.id).is_err());
        }
    }
}
