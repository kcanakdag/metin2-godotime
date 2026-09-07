//! Validated item effects. Recovery is private, gradual, and scoped to an active life.
use crate::definitions::{ItemKind, RECOVERY_INTERVAL_US, RECOVERY_PERCENT};
use crate::progression::character_progression;
use crate::{now_us, player};
use spacetimedb::{Identity, ReducerContext, Table};

#[spacetimedb::table(accessor = item_recovery)]
pub struct ItemRecovery {
    #[primary_key]
    pub owner: Identity,
    pub life_sequence: u32,
    pub hp: u32,
    pub sp: u32,
    pub next_tick_us: i64,
}

fn add_recovery(current: u32, maximum: u32, pending: u32, amount: u32) -> Result<u32, String> {
    if amount == 0 {
        return Ok(pending);
    }
    if current.saturating_add(pending) >= maximum {
        return Err("That resource is already full or recovering.".into());
    }
    pending
        .checked_add(amount)
        .ok_or("Recovery amount exceeds its limit.".into())
}

fn recovery_step(current: u32, maximum: u32, pending: u32) -> (u32, u32) {
    if current >= maximum {
        return (current, 0);
    }
    // The source consumes the full tick allotment even when health caps partway through it.
    let amount = pending.min((u64::from(maximum) * u64::from(RECOVERY_PERCENT) / 100) as u32);
    (
        current.saturating_add(amount).min(maximum),
        pending - amount,
    )
}

pub fn apply(ctx: &ReducerContext, owner: Identity, kind: ItemKind) -> Result<(), String> {
    let ItemKind::Recovery { hp, sp } = kind else {
        return Err("That item cannot be consumed.".into());
    };
    let player = ctx
        .db
        .player()
        .identity()
        .find(owner)
        .ok_or("Enter the world first.")?;
    if !player.online || player.health == 0 {
        return Err("Recovery requires a living character in the world.".into());
    }
    let progression = ctx
        .db
        .character_progression()
        .character_id()
        .find(owner)
        .ok_or("Character progression is missing.")?;
    let now = now_us(ctx);
    let existing = ctx.db.item_recovery().owner().find(owner);
    let (pending_hp, pending_sp, next_tick_us) = existing
        .as_ref()
        .filter(|row| row.life_sequence == player.life_sequence)
        .map_or((0, 0, now.saturating_add(RECOVERY_INTERVAL_US)), |row| {
            (row.hp, row.sp, row.next_tick_us)
        });
    // Validate both resources before changing the pool or consuming the instance.
    let row = ItemRecovery {
        owner,
        life_sequence: player.life_sequence,
        hp: add_recovery(
            player.health.into(),
            player.max_health.into(),
            pending_hp,
            hp,
        )?,
        sp: add_recovery(progression.current_sp, progression.max_sp, pending_sp, sp)?,
        next_tick_us,
    };
    if existing.is_some() {
        ctx.db.item_recovery().owner().update(row);
    } else {
        ctx.db.item_recovery().insert(row);
    }
    Ok(())
}

pub fn clear(ctx: &ReducerContext, owner: Identity) {
    ctx.db.item_recovery().owner().delete(owner);
}

pub fn simulate(ctx: &ReducerContext, now: i64) {
    for mut recovery in ctx.db.item_recovery().iter() {
        let Some(mut player) = ctx.db.player().identity().find(recovery.owner) else {
            clear(ctx, recovery.owner);
            continue;
        };
        if !player.online || player.health == 0 || player.life_sequence != recovery.life_sequence {
            clear(ctx, recovery.owner);
            continue;
        }
        if now < recovery.next_tick_us {
            continue;
        }
        let Some(mut progression) = ctx
            .db
            .character_progression()
            .character_id()
            .find(recovery.owner)
        else {
            clear(ctx, recovery.owner);
            continue;
        };
        let (health, hp) =
            recovery_step(player.health.into(), player.max_health.into(), recovery.hp);
        let (sp_current, sp) =
            recovery_step(progression.current_sp, progression.max_sp, recovery.sp);
        if health != u32::from(player.health) {
            player.health = health as u16;
            ctx.db.player().identity().update(player);
        }
        if sp_current != progression.current_sp {
            progression.current_sp = sp_current;
            ctx.db
                .character_progression()
                .character_id()
                .update(progression);
        }
        if hp == 0 && sp == 0 {
            clear(ctx, recovery.owner);
        } else {
            recovery.hp = hp;
            recovery.sp = sp;
            // A stalled server performs one step, not an unbounded burst of offline healing.
            recovery.next_tick_us = now.saturating_add(RECOVERY_INTERVAL_US);
            ctx.db.item_recovery().owner().update(recovery);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recovery_respects_pool_capacity_and_preserves_unused_resources() {
        assert_eq!(add_recovery(50, 760, 0, 300).unwrap(), 300);
        assert_eq!(add_recovery(50, 760, 300, 800).unwrap(), 1100);
        assert!(add_recovery(50, 760, 1100, 300).is_err());
        assert!(add_recovery(760, 760, 0, 300).is_err());
        assert_eq!(add_recovery(260, 260, 0, 0).unwrap(), 0);
    }

    #[test]
    fn recovery_is_seven_percent_per_second_with_source_rounding_and_tail() {
        assert_eq!(recovery_step(100, 760, 300), (153, 247));
        assert_eq!(recovery_step(100, 760, 35), (135, 0));
        assert_eq!(recovery_step(750, 760, 300), (760, 247));
        assert_eq!(recovery_step(760, 760, 247), (760, 0));
        assert_eq!(recovery_step(0, 260, 80), (18, 62));
    }
}
