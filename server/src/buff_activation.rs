//! Atomic self-buff activation proposal; the database adapter persists all fields
//! together after authenticating the living, selected character and its lease.
use crate::buff_capture::Captured;
use crate::buff_lifecycle::Effects;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SkillState {
    pub vnum: u16,
    pub rank: u8,
    pub revision: u32,
    pub ready_at_us: i64,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Activation {
    pub skill: SkillState,
    pub remaining_sp: u32,
    pub effects: Effects,
}

impl SkillState {
    pub fn activate(
        self,
        expected_revision: u32,
        captured: Captured,
        current_sp: u32,
        existing: &Effects,
        now_us: i64,
    ) -> Result<Activation, &'static str> {
        if self.vnum != captured.affect.skill_vnum
            || !(1..=20).contains(&self.rank)
            || self.ready_at_us < 0
            || now_us < 0
            || captured.sp_cost > 10_000
            || !(0..=600_000_000).contains(&captured.cooldown_us)
        {
            return Err("Invalid self-buff activation state");
        }
        if self.revision != expected_revision {
            return Err("Skill changed; refresh before casting");
        }
        if now_us < self.ready_at_us {
            return Err("Skill is cooling down");
        }
        let revision = self
            .revision
            .checked_add(1)
            .ok_or("Skill revision limit reached")?;
        let ready_at_us = now_us
            .checked_add(captured.cooldown_us)
            .ok_or("Skill clock overflow")?;
        let remaining_sp = current_sp
            .checked_sub(captured.sp_cost)
            .ok_or("Not enough SP")?;
        let mut effects = existing.clone();
        effects.replace(captured.affect)?;
        Ok(Activation {
            skill: Self {
                revision,
                ready_at_us,
                ..self
            },
            remaining_sp,
            effects,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::buff_lifecycle::{Modifier, Point, SkillAffect};

    fn captured() -> Captured {
        Captured {
            sp_cost: 57,
            cooldown_us: 67_000_000,
            affect: SkillAffect {
                skill_vnum: 3,
                modifiers: vec![Modifier {
                    point: Point::AttackSpeed,
                    value: 2,
                    remaining_ticks: 64,
                }],
            },
        }
    }

    fn skill() -> SkillState {
        SkillState {
            vnum: 3,
            rank: 1,
            revision: 0,
            ready_at_us: 0,
        }
    }

    #[test]
    fn accepted_cast_pays_once_and_replay_cannot_extend_or_replace_effects() {
        let existing = Effects::default();
        let cast = skill()
            .activate(0, captured(), 100, &existing, 1_000_000)
            .unwrap();
        assert_eq!(cast.remaining_sp, 43);
        assert_eq!(cast.skill.ready_at_us, 68_000_000);
        assert_eq!(cast.skill.revision, 1);
        assert_eq!(cast.effects.bonus(Point::AttackSpeed), 2);
        assert!(existing.entries().is_empty());
        let before = cast.effects.clone();
        assert!(
            cast.skill
                .activate(0, captured(), 100, &cast.effects, 68_000_000)
                .is_err()
        );
        assert!(
            cast.skill
                .activate(1, captured(), 100, &cast.effects, 67_999_999)
                .is_err()
        );
        assert_eq!(cast.effects, before);
        let recast = cast
            .skill
            .activate(1, captured(), 100, &cast.effects, 68_000_000)
            .unwrap();
        assert_eq!(recast.effects.bonus(Point::AttackSpeed), 2);
        assert_eq!(recast.effects.entries().len(), 1);
        assert_eq!(recast.remaining_sp, 43);
    }

    #[test]
    fn insufficient_sp_bad_capture_and_clock_overflow_leave_existing_state_intact() {
        let mut existing = Effects::default();
        existing.replace(captured().affect).unwrap();
        let before = existing.clone();
        assert!(skill().activate(0, captured(), 56, &existing, 0).is_err());
        assert!(
            skill()
                .activate(0, captured(), 100, &existing, i64::MAX)
                .is_err()
        );
        assert!(
            SkillState {
                revision: u32::MAX,
                ..skill()
            }
            .activate(u32::MAX, captured(), 100, &existing, 0)
            .is_err()
        );
        assert!(
            SkillState { rank: 0, ..skill() }
                .activate(0, captured(), 100, &existing, 0)
                .is_err()
        );
        let mut bad = captured();
        bad.affect.modifiers[0].remaining_ticks = 0;
        assert!(skill().activate(0, bad, 100, &existing, 0).is_err());
        let mut wrong_skill = captured();
        wrong_skill.affect.skill_vnum = 4;
        assert!(skill().activate(0, wrong_skill, 100, &existing, 0).is_err());
        assert_eq!(existing, before);
    }
}
