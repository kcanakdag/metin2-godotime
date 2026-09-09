//! Pure charge transitions. The reducer adapter must persist the returned state
//! and resource changes together, after validating the current lease and target.
//! No client intent can supply the owner snapshot, policy, cost or clock.

use spacetimedb::{ConnectionId, Identity};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Owner {
    pub character: Identity,
    pub connection: ConnectionId,
    pub life: u32,
}

/// Evaluated from trusted skill content at activation, including duration bonuses.
#[derive(Clone, Copy, Debug)]
pub struct Policy {
    pub duration_us: i64,
    pub cooldown_us: i64,
    pub speed_bonus: i32,
    pub sp_cost: u32,
}

impl Policy {
    fn validate(self) -> Result<(), String> {
        if !(1..=600_000_000).contains(&self.duration_us)
            || !(0..=600_000_000).contains(&self.cooldown_us)
            || !(0..=1000).contains(&self.speed_bonus)
            || self.sp_cost > 10_000
        {
            return Err("Invalid charge policy".into());
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Charge {
    pub owner: Owner,
    pub rank: u8,
    pub starts_at_us: i64,
    pub expires_at_us: i64,
    pub speed_bonus: i32,
}

impl Charge {
    /// None means no living, online character with a current controller lease.
    pub fn active(self, owner: Option<Owner>, now: i64) -> bool {
        owner == Some(self.owner) && now >= self.starts_at_us && now < self.expires_at_us
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct State {
    pub skill_vnum: u16,
    pub revision: u32,
    pub ready_at_us: i64,
    pub charge: Option<Charge>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Activation {
    pub state: State,
    pub remaining_sp: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Consumption {
    pub state: State,
    pub captured_rank: u8,
}

impl State {
    fn next_revision(self, expected: u32) -> Result<u32, String> {
        if self.skill_vnum == 0 || self.ready_at_us < 0 {
            return Err("Invalid charge skill state".into());
        }
        if self.revision != expected {
            return Err("Skill changed; refresh before casting".into());
        }
        self.revision
            .checked_add(1)
            .ok_or("Skill revision limit reached".into())
    }

    pub fn begin(
        self,
        owner: Owner,
        rank: u8,
        policy: Policy,
        current_sp: u32,
        expected_revision: u32,
        now: i64,
    ) -> Result<Activation, String> {
        policy.validate()?;
        let revision = self.next_revision(expected_revision)?;
        if now < 0 || !(1..=20).contains(&rank) {
            return Err("Invalid charge clock or rank".into());
        }
        // Stale charge records must be explicitly invalidated by maintenance.
        // Never silently refresh a charge or let it pay for another activation.
        if self.charge.is_some() {
            return Err("Charge already exists".into());
        }
        if now < self.ready_at_us {
            return Err("Skill is cooling down".into());
        }
        let remaining_sp = current_sp
            .checked_sub(policy.sp_cost)
            .ok_or("Not enough SP")?;
        let expires_at_us = now
            .checked_add(policy.duration_us)
            .ok_or("Charge clock overflow")?;
        let ready_at_us = now
            .checked_add(policy.cooldown_us)
            .ok_or("Skill clock overflow")?;
        Ok(Activation {
            state: Self {
                revision,
                ready_at_us,
                charge: Some(Charge {
                    owner,
                    rank,
                    starts_at_us: now,
                    expires_at_us,
                    speed_bonus: policy.speed_bonus,
                }),
                ..self
            },
            remaining_sp,
        })
    }

    /// Call only after target life, distance, map and attack eligibility validate.
    /// Consumption neither pays SP nor restarts cooldown. Persist with damage in
    /// the same transaction; do not persist a proposal from a rejected strike.
    pub fn consume(
        self,
        owner: Option<Owner>,
        expected_revision: u32,
        now: i64,
    ) -> Result<Consumption, String> {
        let revision = self.next_revision(expected_revision)?;
        let charge = self
            .charge
            .filter(|charge| charge.active(owner, now))
            .ok_or("No active charge for this controller life")?;
        Ok(Consumption {
            state: Self {
                revision,
                charge: None,
                ..self
            },
            captured_rank: charge.rank,
        })
    }

    /// Clear expired or invalidated ownership without refunding SP or cooldown.
    /// The adapter derives owner from live lease/health/character state. Clearing
    /// also changes revision so queued intents cannot reuse the old charge.
    pub fn invalidate(self, owner: Option<Owner>, now: i64) -> Result<Self, String> {
        if now < 0 {
            return Err("Invalid charge clock".into());
        }
        if self.charge.is_none_or(|charge| charge.active(owner, now)) {
            return Ok(self);
        }
        Ok(Self {
            revision: self.next_revision(self.revision)?,
            charge: None,
            ..self
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const NOW: i64 = 1_000_000;

    fn owner() -> Owner {
        Owner {
            character: Identity::from_claims("charge-test", "warrior"),
            connection: ConnectionId::from_u128(1),
            life: 0,
        }
    }
    fn state() -> State {
        State {
            skill_vnum: 5,
            revision: 7,
            ready_at_us: 0,
            charge: None,
        }
    }
    fn policy() -> Policy {
        Policy {
            duration_us: 3_000_000,
            cooldown_us: 12_000_000,
            speed_bonus: 150,
            sp_cost: 66,
        }
    }
    fn begin() -> Activation {
        state().begin(owner(), 1, policy(), 100, 7, NOW).unwrap()
    }

    #[test]
    fn approaching_charge_pays_once_and_strikes_once_during_cooldown() {
        let activated = begin();
        assert_eq!(activated.remaining_sp, 34);
        assert_eq!(activated.state.ready_at_us, NOW + 12_000_000);
        assert!(
            activated
                .state
                .begin(owner(), 1, policy(), 100, 8, NOW)
                .is_err()
        );
        let consumed = activated
            .state
            .consume(Some(owner()), 8, NOW + 2_000_000)
            .unwrap();
        assert_eq!(consumed.captured_rank, 1);
        assert_eq!(consumed.state.ready_at_us, activated.state.ready_at_us);
        assert_eq!(consumed.state.revision, 9);
        assert!(consumed.state.charge.is_none());
        for replay_revision in [7, 8, 9] {
            assert!(
                consumed
                    .state
                    .consume(Some(owner()), replay_revision, NOW + 2_000_001)
                    .is_err()
            );
        }
        assert!(
            consumed
                .state
                .begin(owner(), 1, policy(), 100, 9, NOW + 3_000_000)
                .is_err()
        );
        assert!(
            consumed
                .state
                .begin(owner(), 1, policy(), 100, 9, NOW + 12_000_000)
                .is_ok()
        );
    }

    #[test]
    fn immediate_targeted_use_can_compose_one_activation_and_consumption() {
        let activated = begin();
        let consumed = activated.state.consume(Some(owner()), 8, NOW).unwrap();
        assert_eq!(activated.remaining_sp, 34);
        assert_eq!(consumed.state.ready_at_us, NOW + 12_000_000);
        assert!(consumed.state.charge.is_none());
    }

    #[test]
    fn expiry_is_exclusive_and_does_not_refund_or_restart_cooldown() {
        let active = begin().state;
        let expires = NOW + 3_000_000;
        assert!(active.consume(Some(owner()), 8, NOW - 1).is_err());
        assert!(active.consume(Some(owner()), 8, expires - 1).is_ok());
        assert!(active.consume(Some(owner()), 8, expires).is_err());
        assert_eq!(
            active.invalidate(Some(owner()), expires - 1).unwrap(),
            active
        );
        let expired = active.invalidate(Some(owner()), expires).unwrap();
        assert!(expired.charge.is_none());
        assert_eq!(expired.ready_at_us, active.ready_at_us);
        assert_eq!(expired.revision, 9);
        assert_eq!(
            expired.invalidate(Some(owner()), expires + 1).unwrap(),
            expired
        );
        assert!(
            expired
                .begin(owner(), 1, policy(), 100, 9, expires)
                .is_err()
        );
    }

    #[test]
    fn disconnect_switch_death_and_replacement_cannot_transfer_or_restore_charge() {
        let active = begin().state;
        for current in [
            None,
            Some(Owner {
                character: Identity::from_claims("charge-test", "other"),
                ..owner()
            }),
            Some(Owner {
                connection: ConnectionId::from_u128(2),
                ..owner()
            }),
            Some(Owner { life: 1, ..owner() }),
        ] {
            assert!(active.consume(current, 8, NOW + 1).is_err());
            let cleared = active.invalidate(current, NOW + 1).unwrap();
            assert!(cleared.charge.is_none());
            assert_eq!(cleared.ready_at_us, active.ready_at_us);
            assert!(cleared.consume(Some(owner()), 9, NOW + 2).is_err());
        }
    }

    #[test]
    fn rejected_proposals_leave_the_original_state_unchanged() {
        let before = state();
        assert!(before.begin(owner(), 1, policy(), 65, 7, NOW).is_err());
        assert!(before.begin(owner(), 1, policy(), 100, 6, NOW).is_err());
        for rank in [0, 21, u8::MAX] {
            assert!(before.begin(owner(), rank, policy(), 100, 7, NOW).is_err());
        }
        assert_eq!(before, state());
        let active = begin().state;
        assert!(active.consume(Some(owner()), 7, NOW).is_err());
        assert!(active.consume(None, 8, NOW).is_err());
        assert!(active.consume(Some(owner()), 8, NOW).is_ok());
    }

    #[test]
    fn policy_clock_and_revision_limits_fail_closed() {
        for invalid in [
            Policy {
                duration_us: 0,
                ..policy()
            },
            Policy {
                duration_us: 600_000_001,
                ..policy()
            },
            Policy {
                cooldown_us: -1,
                ..policy()
            },
            Policy {
                cooldown_us: 600_000_001,
                ..policy()
            },
            Policy {
                speed_bonus: -1,
                ..policy()
            },
            Policy {
                speed_bonus: 1001,
                ..policy()
            },
            Policy {
                sp_cost: 10_001,
                ..policy()
            },
        ] {
            assert!(state().begin(owner(), 1, invalid, 100, 7, NOW).is_err());
        }
        for now in [-1, i64::MAX, i64::MAX - 4_000_000] {
            assert!(state().begin(owner(), 1, policy(), 100, 7, now).is_err());
        }
        let exhausted = State {
            revision: u32::MAX,
            ..state()
        };
        assert!(
            exhausted
                .begin(owner(), 1, policy(), 100, u32::MAX, NOW)
                .is_err()
        );
        let exhausted = State {
            revision: u32::MAX,
            ..begin().state
        };
        assert!(exhausted.consume(Some(owner()), u32::MAX, NOW).is_err());
        assert!(exhausted.invalidate(None, NOW).is_err());
    }
}
