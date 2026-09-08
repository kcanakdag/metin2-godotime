//! Checked allocation of a complete group's public IDs before any rows are inserted.
//! Persist the returned high-water mark in the same transaction as group members.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Reservation {
    pub first: u32,
    pub last: u32,
}

impl Reservation {
    /// The first successfully placed member is the leader and owns regeneration
    /// capacity. Followers have distinct IDs but do not own another unit slot.
    pub fn owner(self) -> u64 {
        u64::from(self.first)
    }
}

/// `last_issued` includes authored/reserved IDs and every previously allocated
/// member, including destroyed leaders and surviving or destroyed followers.
/// Call after placement; failed member placements require no public identity.
/// Failure changes no cursor, so callers can reject the entire transaction.
pub fn reserve(last_issued: u32, placed_members: usize) -> Result<Reservation, String> {
    if !(1..=256).contains(&placed_members) {
        return Err("A group allocation requires 1..=256 placed members".into());
    }
    let count = u32::try_from(placed_members).map_err(|_| "Member count exceeds ID range")?;
    let last = last_issued
        .checked_add(count)
        .ok_or("Monster ID space exhausted")?;
    Ok(Reservation {
        first: last_issued + 1,
        last,
    })
}
