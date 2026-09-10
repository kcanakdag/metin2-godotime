//! Private, transactional quantity history. IDs identify stacks, not item definitions.
use crate::inventory::{InventoryItem, ItemDrop};
use spacetimedb::{Identity, ReducerContext, Table, Timestamp};

#[spacetimedb::table(accessor = item_audit)]
pub struct ItemAudit {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub item_id: u64,
    #[index(btree)]
    pub drop_id: u64,
    pub owner: Identity,
    pub account: Identity,
    pub vnum: u32,
    pub previous_count: u16,
    pub count: u16,
    pub revision: u32,
    pub cause: String,
    pub created_at: Timestamp,
}

#[derive(Clone, Copy)]
pub enum Cause {
    Starter,
    Progression,
    Quest,
    Monster,
    Pickup(u64),
    Consume,
    Expiry,
}

impl Cause {
    fn name(self) -> &'static str {
        match self {
            Self::Starter => "starter",
            Self::Progression => "progression",
            Self::Quest => "quest",
            Self::Monster => "monster",
            Self::Pickup(_) => "pickup",
            Self::Consume => "consume",
            Self::Expiry => "expiry",
        }
    }
}

pub fn next_revision(current: u32, expected: u32) -> Result<u32, String> {
    if current == 0 || current != expected {
        return Err("That item changed. Wait for the inventory update and try again.".into());
    }
    current
        .checked_add(1)
        .ok_or("Item revision limit reached.".into())
}

pub fn inventory(ctx: &ReducerContext, item: &InventoryItem, previous_count: u16, cause: Cause) {
    ctx.db.item_audit().insert(ItemAudit {
        id: 0,
        item_id: item.id,
        drop_id: match cause {
            Cause::Pickup(id) => id,
            _ => 0,
        },
        owner: item.owner,
        account: item.account,
        vnum: item.vnum,
        previous_count,
        count: item.count,
        revision: item.revision,
        cause: cause.name().into(),
        created_at: ctx.timestamp,
    });
}

pub fn ground(ctx: &ReducerContext, drop: &ItemDrop, created: bool, cause: Cause) {
    ctx.db.item_audit().insert(ItemAudit {
        id: 0,
        item_id: 0,
        drop_id: drop.id,
        owner: drop.owner,
        // Ground reservation identifies a character; it does not grant account ownership.
        account: Identity::ZERO,
        vnum: drop.vnum,
        previous_count: if created { 0 } else { drop.count },
        count: if created { drop.count } else { 0 },
        revision: 0,
        cause: cause.name().into(),
        created_at: ctx.timestamp,
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn replay_future_zero_and_exhausted_revisions_fail_closed() {
        assert_eq!(next_revision(1, 1), Ok(2));
        for (current, expected) in [(2, 1), (1, 2), (0, 0), (1, 0), (u32::MAX, u32::MAX)] {
            assert!(next_revision(current, expected).is_err());
        }
        assert_eq!(next_revision(u32::MAX - 1, u32::MAX - 1), Ok(u32::MAX));
    }
}
