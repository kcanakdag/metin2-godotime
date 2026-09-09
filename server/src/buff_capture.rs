//! Evaluate trusted deterministic self-buff programs once at cast acceptance.
//! Database adapters must validate ownership/rank and atomically persist payment,
//! cooldown and this captured affect. Client expressions are never accepted.

use crate::buff_lifecycle::{Modifier, Point, SkillAffect};
use crate::skill_formula::{self, Op, VARIABLE_COUNT};

pub enum ModifierValue<'a> {
    Formula(&'a [Op]),
    /// Original integer GetSkillPower * factor / 100 path (not float k).
    PowerPercent(u16),
}

pub struct ModifierProgram<'a> {
    pub point: Point,
    pub value: ModifierValue<'a>,
    pub duration: &'a [Op],
}

pub struct Definition<'a> {
    pub skill_vnum: u16,
    pub sp_cost: &'a [Op],
    pub cooldown: &'a [Op],
    pub modifiers: &'a [ModifierProgram<'a>],
}

#[derive(Debug, PartialEq, Eq)]
pub struct Captured {
    pub sp_cost: u32,
    pub cooldown_us: i64,
    pub affect: SkillAffect,
}

fn integer(
    program: &[Op],
    variables: &[f64; VARIABLE_COUNT],
    minimum: i64,
    maximum: i64,
) -> Result<i64, String> {
    // Random buffs need explicit source evaluation ordering before support.
    if program.iter().any(|op| matches!(op, Op::Number)) {
        return Err("Random self-buff programs are not supported".into());
    }
    let value = skill_formula::evaluate(program, variables, |_, _| unreachable!())?;
    if value < minimum as f64 || value > maximum as f64 {
        return Err("Self-buff formula result exceeds runtime bounds".into());
    }
    Ok(value as i64)
}

pub fn capture(
    definition: &Definition<'_>,
    variables: &[f64; VARIABLE_COUNT],
    power_percent: u8,
) -> Result<Captured, String> {
    if !(1..=100).contains(&power_percent) {
        return Err("Self-buff requires a learned bounded skill power".into());
    }
    let mut source_variables = *variables;
    source_variables[4] = f64::from((f64::from(power_percent) / 100.0) as f32);
    let variables = &source_variables;
    if definition.modifiers.is_empty() || definition.modifiers.len() > 4 {
        return Err("Invalid self-buff modifier count".into());
    }
    let sp_cost = integer(definition.sp_cost, variables, 0, 10_000)? as u32;
    // Player UseSkill truncates seconds BEFORE conversion to milliseconds.
    let cooldown_us = integer(definition.cooldown, variables, 0, 600)? * 1_000_000;
    let mut modifiers = Vec::with_capacity(definition.modifiers.len());
    for program in definition.modifiers {
        modifiers.push(Modifier {
            point: program.point,
            value: match program.value {
                ModifierValue::Formula(formula) => {
                    integer(formula, variables, -100_000, 100_000)? as i32
                }
                ModifierValue::PowerPercent(factor) => {
                    i32::from(power_percent) * i32::from(factor) / 100
                }
            },
            remaining_ticks: integer(program.duration, variables, 1, 86_400)? as u32,
        });
    }
    let affect = SkillAffect {
        skill_vnum: definition.skill_vnum,
        modifiers,
    };
    affect.validate()?;
    Ok(Captured {
        sp_cost,
        cooldown_us,
        affect,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::buff_lifecycle::Effects;

    const COST: &[Op] = &[
        Op::Constant(50.0),
        Op::Constant(140.0),
        Op::Variable(4),
        Op::Mul,
        Op::Add,
    ];
    const COOLDOWN: &[Op] = &[
        Op::Constant(63.0),
        Op::Constant(90.0),
        Op::Variable(4),
        Op::Mul,
        Op::Add,
    ];
    const DURATION: &[Op] = &[
        Op::Constant(60.0),
        Op::Constant(90.0),
        Op::Variable(4),
        Op::Mul,
        Op::Add,
    ];
    const ATTACK: &[Op] = &[Op::Constant(50.0), Op::Variable(4), Op::Mul];
    const MOVEMENT: &[Op] = &[Op::Constant(20.0), Op::Variable(4), Op::Mul];

    #[test]
    fn berserk_captures_both_speeds_and_normal_damage_penalty_at_source_integer_boundaries() {
        let modifiers = [
            ModifierProgram {
                point: Point::AttackSpeed,
                value: ModifierValue::Formula(ATTACK),
                duration: DURATION,
            },
            ModifierProgram {
                point: Point::MovementSpeed,
                value: ModifierValue::Formula(MOVEMENT),
                duration: DURATION,
            },
            ModifierProgram {
                point: Point::NormalDamageTakenPercent,
                value: ModifierValue::PowerPercent(25),
                duration: DURATION,
            },
        ];
        let definition = Definition {
            skill_vnum: 3,
            sp_cost: COST,
            cooldown: COOLDOWN,
            modifiers: &modifiers,
        };
        for (power, cost, cooldown, duration, attack, movement, penalty) in [
            (5, 57, 67, 64, 2, 1, 1),
            (6, 58, 68, 65, 2, 1, 1),
            (12, 66, 73, 70, 5, 2, 3),
            (50, 120, 108, 105, 25, 10, 12),
        ] {
            let mut variables = [0.0; VARIABLE_COUNT];
            variables[4] = 999.0; // Rank power comes from the trusted integer argument.
            let captured = capture(&definition, &variables, power).unwrap();
            variables[4] = 0.0; // Later input mutation leaves captured values unchanged.
            assert_eq!(variables[4], 0.0);
            assert_eq!(
                (captured.sp_cost, captured.cooldown_us),
                (cost, cooldown * 1_000_000)
            );
            assert!(
                captured
                    .affect
                    .modifiers
                    .iter()
                    .all(|value| value.remaining_ticks == duration)
            );
            let mut active = Effects::default();
            active.replace(captured.affect).unwrap();
            assert_eq!(active.bonus(Point::AttackSpeed), attack);
            assert_eq!(active.bonus(Point::MovementSpeed), movement);
            assert_eq!(active.bonus(Point::NormalDamageTakenPercent), penalty);
            active.advance(duration);
            assert!(active.entries().is_empty());
        }
    }

    #[test]
    fn invalid_formulas_and_duplicate_points_reject_without_returning_partial_capture() {
        let variables = [0.0; VARIABLE_COUNT];
        for value in [
            vec![Op::Constant(f64::NAN)],
            vec![Op::Constant(100_001.0)],
            vec![Op::Constant(1.0), Op::Constant(2.0), Op::Number],
        ] {
            let modifiers = [ModifierProgram {
                point: Point::AttackSpeed,
                value: ModifierValue::Formula(&value),
                duration: DURATION,
            }];
            let definition = Definition {
                skill_vnum: 3,
                sp_cost: COST,
                cooldown: COOLDOWN,
                modifiers: &modifiers,
            };
            assert!(capture(&definition, &variables, 5).is_err());
        }
        let duplicate = [
            ModifierProgram {
                point: Point::AttackSpeed,
                value: ModifierValue::Formula(ATTACK),
                duration: DURATION,
            },
            ModifierProgram {
                point: Point::AttackSpeed,
                value: ModifierValue::Formula(MOVEMENT),
                duration: DURATION,
            },
        ];
        assert!(
            capture(
                &Definition {
                    skill_vnum: 3,
                    sp_cost: COST,
                    cooldown: COOLDOWN,
                    modifiers: &duplicate
                },
                &variables,
                5
            )
            .is_err()
        );
    }
}
