//! Bounded arithmetic programs compiled from trusted skill data, never client expressions.

#[derive(Clone, Copy, Debug)]
pub enum Op {
    Constant(f64),
    Variable(u8),
    Add,
    Sub,
    Mul,
    Div,
    Neg,
    Floor,
    Number,
}

pub const VARIABLE_COUNT: usize = 10;
const LIMIT: f64 = 1_000_000_000_000.0;

fn bounded(value: f64) -> Result<f64, String> {
    if value.is_finite() && value.abs() <= LIMIT {
        Ok(value)
    } else {
        Err("Skill arithmetic exceeds supported bounds.".into())
    }
}

pub fn evaluate(
    program: &[Op],
    variables: &[f64; VARIABLE_COUNT],
    mut random: impl FnMut(i64, i64) -> i64,
) -> Result<f64, String> {
    if program.is_empty() || program.len() > 128 {
        return Err("Invalid skill arithmetic program size.".into());
    }
    for value in variables {
        bounded(*value)?;
    }
    let mut stack = Vec::with_capacity(32);
    for op in program {
        let value = match *op {
            Op::Constant(value) => {
                if value.abs() > 1_000_000.0 {
                    return Err("Invalid skill arithmetic constant.".into());
                }
                value
            }
            Op::Variable(index) => *variables
                .get(usize::from(index))
                .ok_or("Unknown skill arithmetic variable.")?,
            Op::Neg | Op::Floor => {
                let a: f64 = stack.pop().ok_or("Skill arithmetic stack underflow.")?;
                if matches!(op, Op::Neg) { -a } else { a.floor() }
            }
            _ => {
                let b = stack.pop().ok_or("Skill arithmetic stack underflow.")?;
                let a = stack.pop().ok_or("Skill arithmetic stack underflow.")?;
                match op {
                    Op::Add => a + b,
                    Op::Sub => a - b,
                    Op::Mul => a * b,
                    Op::Div if b != 0.0 => a / b,
                    Op::Number => {
                        // The legacy number() function uses inclusive integer endpoints.
                        if a.abs() > 1_000_000.0 || b.abs() > 1_000_000.0 || a > b {
                            return Err("Invalid skill random range.".into());
                        }
                        let (lo, hi) = (a as i64, b as i64);
                        let roll = random(lo, hi);
                        if !(lo..=hi).contains(&roll) {
                            return Err("Skill random result is outside its range.".into());
                        }
                        roll as f64
                    }
                    _ => return Err("Invalid skill arithmetic operation.".into()),
                }
            }
        };
        stack.push(bounded(value)?);
        if stack.len() > 32 {
            return Err("Skill arithmetic stack limit reached.".into());
        }
    }
    if stack.len() != 1 {
        return Err("Incomplete skill arithmetic program.".into());
    }
    Ok(stack[0])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn original_cost_floor_and_integer_random_order() {
        let mut vars = [0.0; VARIABLE_COUNT];
        vars[4] = 0.05;
        let cost = [
            Op::Constant(50.0),
            Op::Constant(130.0),
            Op::Variable(4),
            Op::Mul,
            Op::Add,
        ];
        assert_eq!(evaluate(&cost, &vars, |lo, _| lo).unwrap(), 56.5);
        let random = [
            Op::Constant(1.9),
            Op::Constant(5.9),
            Op::Number,
            Op::Neg,
            Op::Constant(0.5),
            Op::Add,
            Op::Floor,
        ];
        assert_eq!(evaluate(&random, &vars, |lo, _| lo).unwrap(), -1.0);
        assert_eq!(evaluate(&random, &vars, |_, hi| hi).unwrap(), -5.0);
        assert_eq!(
            evaluate(
                &[
                    Op::Constant(3.0),
                    Op::Constant(2.0),
                    Op::Div,
                    Op::Constant(1.0),
                    Op::Sub
                ],
                &vars,
                |lo, _| lo
            )
            .unwrap(),
            0.5
        );
    }

    #[test]
    fn malformed_nonfinite_and_excessive_programs_reject() {
        for program in [
            vec![],
            vec![Op::Add],
            vec![Op::Variable(10)],
            vec![Op::Constant(f64::NAN)],
            vec![Op::Constant(f64::INFINITY)],
            vec![Op::Constant(1.0); 33],
            vec![Op::Constant(1.0); 129],
            vec![Op::Constant(1.0), Op::Constant(0.0), Op::Div],
            vec![Op::Constant(2.0), Op::Constant(1.0), Op::Number],
            vec![Op::Constant(1.0), Op::Constant(1.0), Op::Number],
        ] {
            assert!(evaluate(&program, &[0.0; VARIABLE_COUNT], |_, hi| hi + 1).is_err());
        }
        assert!(
            evaluate(
                &[Op::Constant(1.0)],
                &[f64::NAN; VARIABLE_COUNT],
                |lo, _| lo
            )
            .is_err()
        );
    }
}
