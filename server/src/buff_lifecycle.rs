//! Shared captured skill-affect values, independent of database and presentation.
//! The adapter supplies trusted evaluated values and elapsed online affect ticks.
//! Remaining ticks are persisted; disconnect is not an expiry or a fresh cast.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Point {
    AttackSpeed,
    MovementSpeed,
    AttackGrade,
    NormalDamageTakenPercent,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Modifier {
    pub point: Point,
    pub value: i32,
    pub remaining_ticks: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SkillAffect {
    pub skill_vnum: u16,
    pub modifiers: Vec<Modifier>,
}

impl SkillAffect {
    fn validate(&self) -> Result<(), &'static str> {
        if !(1..=255).contains(&self.skill_vnum)
            || self.modifiers.is_empty()
            || self.modifiers.len() > 4
        {
            return Err("Invalid skill affect identity or modifier count");
        }
        for (index, modifier) in self.modifiers.iter().enumerate() {
            if !(1..=86_400).contains(&modifier.remaining_ticks)
                || !(-100_000..=100_000).contains(&modifier.value)
                || self.modifiers[..index]
                    .iter()
                    .any(|previous| previous.point == modifier.point)
            {
                return Err("Invalid skill affect value, duration or duplicate point");
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Effects {
    entries: Vec<SkillAffect>,
}

impl Effects {
    /// Validate the entire replacement before touching either of its old points.
    pub fn replace(&mut self, effect: SkillAffect) -> Result<(), &'static str> {
        effect.validate()?;
        if let Some(previous) = self
            .entries
            .iter_mut()
            .find(|entry| entry.skill_vnum == effect.skill_vnum)
        {
            *previous = effect;
        } else {
            self.entries.push(effect);
        }
        Ok(())
    }

    pub fn entries(&self) -> &[SkillAffect] {
        &self.entries
    }

    pub fn remove(&mut self, skill_vnum: u16) {
        self.entries.retain(|entry| entry.skill_vnum != skill_vnum);
    }

    /// Recompute contributions from active sources, never from already-buffed stats.
    pub fn bonus(&self, point: Point) -> i32 {
        self.entries
            .iter()
            .flat_map(|entry| &entry.modifiers)
            .filter(|modifier| modifier.point == point)
            .map(|modifier| modifier.value)
            .sum()
    }

    /// One source affect tick is one online second. Zero leaves saved state intact.
    pub fn advance(&mut self, online_ticks: u32) {
        for effect in &mut self.entries {
            for modifier in &mut effect.modifiers {
                modifier.remaining_ticks = modifier.remaining_ticks.saturating_sub(online_ticks);
            }
            effect
                .modifiers
                .retain(|modifier| modifier.remaining_ticks > 0);
        }
        self.entries.retain(|effect| !effect.modifiers.is_empty());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn effect(id: u16, value: i32, ticks: u32) -> SkillAffect {
        SkillAffect {
            skill_vnum: id,
            modifiers: vec![Modifier {
                point: Point::AttackSpeed,
                value,
                remaining_ticks: ticks,
            }],
        }
    }

    #[test]
    fn recast_replaces_skill_without_stacking_or_removing_other_sources() {
        let mut effects = Effects::default();
        effects.replace(effect(3, 10, 60)).unwrap();
        effects.replace(effect(4, 5, 30)).unwrap();
        effects.replace(effect(3, 20, 90)).unwrap();
        assert_eq!(effects.bonus(Point::AttackSpeed), 25);
        assert_eq!(effects.entries().len(), 2);
        effects.remove(3);
        assert_eq!(effects.bonus(Point::AttackSpeed), 5);
    }

    #[test]
    fn independent_secondary_expiry_and_offline_pause_preserve_remaining_duration() {
        let mut effects = Effects::default();
        let mut captured = effect(3, 10, 60);
        captured.modifiers.push(Modifier {
            point: Point::MovementSpeed,
            value: 4,
            remaining_ticks: 30,
        });
        effects.replace(captured).unwrap();
        effects.advance(29);
        let saved = effects.clone();
        effects.advance(0);
        assert_eq!(effects, saved);
        effects.advance(1);
        assert_eq!(effects.bonus(Point::MovementSpeed), 0);
        assert_eq!(effects.bonus(Point::AttackSpeed), 10);
        effects.advance(u32::MAX);
        assert!(effects.entries().is_empty());
    }

    #[test]
    fn invalid_replacement_does_not_partially_remove_previous_affect() {
        let mut effects = Effects::default();
        effects.replace(effect(3, 10, 60)).unwrap();
        let before = effects.clone();
        for invalid in [effect(0, 10, 60), effect(3, i32::MAX, 60), effect(3, 10, 0)] {
            assert!(effects.replace(invalid).is_err());
            assert_eq!(effects, before);
        }
        let mut duplicate = effect(3, 20, 90);
        duplicate.modifiers.push(duplicate.modifiers[0].clone());
        assert!(effects.replace(duplicate).is_err());
        assert_eq!(effects, before);
    }

    #[test]
    fn bounded_distinct_sources_cannot_overflow_derived_bonus() {
        let mut effects = Effects::default();
        for id in 1..=255 {
            effects.replace(effect(id, 100_000, 1)).unwrap();
        }
        assert_eq!(effects.bonus(Point::AttackSpeed), 25_500_000);
        effects.advance(1);
        assert_eq!(effects.bonus(Point::AttackSpeed), 0);
    }
}
