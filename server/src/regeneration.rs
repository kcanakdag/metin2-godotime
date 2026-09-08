//! Overworld regeneration state machine. Storage and spawning are supplied by callers.
use std::collections::BTreeSet;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EntryState {
    interval_us: i64,
    capacity: usize,
    next_tick_us: Option<i64>,
    initial: bool,
    jitter_us: i64,
    owners: BTreeSet<u64>,
    last_owner: u64,
}

impl EntryState {
    pub fn new(interval_us: i64, capacity: usize, jitter_seconds: u8) -> Result<Self, String> {
        if !(0..=86_400_000_000).contains(&interval_us) || capacity > 1000 || jitter_seconds > 16 {
            return Err("Invalid overworld regeneration configuration".into());
        }
        Ok(Self {
            interval_us,
            capacity,
            next_tick_us: None,
            initial: true,
            jitter_us: i64::from(jitter_seconds) * 1_000_000,
            owners: BTreeSet::new(),
            last_owner: 0,
        })
    }

    /// Spawn callbacks return the persistent identity of a successfully created
    /// unit owner (a group leader or direct mob). These allocation tokens must
    /// increase monotonically and never reuse a previous life's token. A public
    /// monster ID that is reused on respawn is not a suitable token.
    /// Failed attempts return None.
    /// The caller must transact spawned rows together with the returned state.
    /// Previewing a tick never changes this state, including on callback failure.
    pub fn plan_tick(
        &self,
        now_us: i64,
        mut spawn: impl FnMut() -> Result<Option<u64>, String>,
    ) -> Result<Self, String> {
        if now_us < 0 {
            return Err("Regeneration clock must be nonnegative".into());
        }
        if self.interval_us == 0 || self.next_tick_us.is_some_and(|due| now_us < due) {
            return Ok(self.clone());
        }
        let delay = self.interval_us + if self.initial { self.jitter_us } else { 0 };
        let due = now_us
            .checked_add(delay)
            .ok_or("Regeneration clock overflow")?;
        let mut next = self.clone();
        // Fix the attempt count before spawning: failures retry on the next
        // entry tick, not in an unbounded loop until capacity is reached.
        for _ in 0..self.capacity.saturating_sub(self.owners.len()) {
            if let Some(owner) = spawn()? {
                if owner <= next.last_owner || !next.owners.insert(owner) {
                    return Err("Regeneration owner token is zero, reused or out of order".into());
                }
                next.last_owner = owner;
            }
        }
        next.initial = false;
        next.next_tick_us = Some(due);
        Ok(next)
    }

    /// Call on destruction of this exact owner, not lethal damage or follower death.
    /// Repeated/stale destruction cannot decrement capacity a second time.
    pub fn owner_destroyed(&mut self, owner: u64) -> bool {
        self.owners.remove(&owner)
    }

    pub fn owners(&self) -> &BTreeSet<u64> {
        &self.owners
    }

    pub fn next_tick_us(&self) -> Option<i64> {
        self.next_tick_us
    }
}
