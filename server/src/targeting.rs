//! Private combat targeting state and the owner-private target projection.

use crate::accounts;
use crate::combat::{Monster, monster};
use crate::{Controller, active_controller, controller, now_us};
use spacetimedb::{Filter, Identity, ReducerContext, Table};

const TARGET_CHANGE_INTERVAL_US: i64 = 1_000_000;

#[spacetimedb::table(accessor = combat_target_view, public)]
#[derive(Clone)]
pub struct CombatTargetView {
    pub account: Identity,
    #[primary_key]
    pub character_id: Identity,
    pub target_id: u32,
    pub target_life_sequence: u32,
}

#[spacetimedb::client_visibility_filter]
const OWN_COMBAT_TARGET: Filter =
    Filter::Sql("SELECT * FROM combat_target_view WHERE combat_target_view.account = :sender");

fn checked_revision(revision: u64) -> Result<u64, String> {
    revision
        .checked_add(1)
        .ok_or("Combat target revision limit reached.".into())
}

fn checked_deadline(now: i64) -> Result<i64, String> {
    now.checked_add(TARGET_CHANGE_INTERVAL_US)
        .ok_or("Combat target deadline is outside the supported range.".into())
}

fn target_change_allowed(same_target: bool, now: i64, deadline: i64) -> bool {
    same_target || now >= deadline
}

fn valid_target(ctx: &ReducerContext, target_id: u32, life: u32) -> Result<Monster, String> {
    let target = ctx
        .db
        .monster()
        .id()
        .find(target_id)
        .ok_or("That combat target does not exist.")?;
    if target.life_sequence != life || target.health == 0 {
        return Err("That combat target life is no longer active.".into());
    }
    if target.definition_vnum != crate::definitions::MOB_VNUM
        || target.actor_id != crate::definitions::MOB_ACTOR_ID
        || target.level != crate::definitions::MOB_LEVEL
        || target.max_health != crate::definitions::MOB_MAX_HEALTH
        || !target.x.is_finite()
        || !target.y.is_finite()
        || !target.z.is_finite()
    {
        return Err("That combat target is not supported by this world definition.".into());
    }
    Ok(target)
}

fn upsert_view(
    ctx: &ReducerContext,
    account: Identity,
    character_id: Identity,
    target_id: u32,
    target_life_sequence: u32,
) {
    let row = CombatTargetView {
        account,
        character_id,
        target_id,
        target_life_sequence,
    };
    if ctx
        .db
        .combat_target_view()
        .character_id()
        .find(character_id)
        .is_some()
    {
        ctx.db.combat_target_view().character_id().update(row);
    } else {
        ctx.db.combat_target_view().insert(row);
    }
}

fn clear_fields(control: &mut Controller) -> Result<(), String> {
    control.combat_target_revision = checked_revision(control.combat_target_revision)?;
    control.combat_target_id = 0;
    control.combat_target_life_sequence = 0;
    Ok(())
}

#[spacetimedb::reducer]
pub fn select_combat_target(
    ctx: &ReducerContext,
    target_id: u32,
    target_life_sequence: u32,
) -> Result<(), String> {
    let mut control = active_controller(ctx)?;
    valid_target(ctx, target_id, target_life_sequence)?;
    let now = now_us(ctx);
    let same_target = control.combat_target_id == target_id
        && control.combat_target_life_sequence == target_life_sequence;
    if !target_change_allowed(same_target, now, control.combat_target_change_not_before_us) {
        return Err("Wait one second before changing combat targets.".into());
    }
    let revision = checked_revision(control.combat_target_revision)?;
    let deadline = checked_deadline(now)?;
    control.combat_target_id = target_id;
    control.combat_target_life_sequence = target_life_sequence;
    control.combat_target_change_not_before_us = deadline;
    control.combat_target_revision = revision;
    if !same_target {
        crate::combo::cancel_queued_link(&mut control);
    }
    let character = control.identity;
    ctx.db.controller().identity().update(control);
    upsert_view(
        ctx,
        ctx.sender(),
        character,
        target_id,
        target_life_sequence,
    );
    Ok(())
}

#[spacetimedb::reducer]
pub fn clear_combat_target(ctx: &ReducerContext) -> Result<(), String> {
    let mut control = active_controller(ctx)?;
    clear_fields(&mut control)?;
    crate::combo::cancel_queued_link(&mut control);
    let character = control.identity;
    ctx.db.controller().identity().update(control);
    ctx.db.combat_target_view().character_id().delete(character);
    Ok(())
}

pub fn clear_character_target(
    ctx: &ReducerContext,
    control: &mut Controller,
) -> Result<(), String> {
    clear_fields(control)?;
    ctx.db
        .combat_target_view()
        .character_id()
        .delete(control.identity);
    Ok(())
}

pub fn clear_monster_targets(
    ctx: &ReducerContext,
    target_id: u32,
    target_life_sequence: u32,
) -> Result<(), String> {
    let characters: Vec<_> = ctx
        .db
        .controller()
        .iter()
        .filter(|control| {
            control.combat_target_id == target_id
                && control.combat_target_life_sequence == target_life_sequence
        })
        .map(|control| control.identity)
        .collect();
    for character in characters {
        let mut control = ctx
            .db
            .controller()
            .identity()
            .find(character)
            .expect("target cleanup controller disappeared during one reducer");
        clear_character_target(ctx, &mut control)?;
        ctx.db.controller().identity().update(control);
    }
    Ok(())
}

/// Publish the existing nearest-target fallback only when no target-changing
/// intent occurred after swing start. Failure never invalidates the resolved hit.
pub fn select_fallback_after_hit(
    ctx: &ReducerContext,
    character: Identity,
    target_id: u32,
    target_life_sequence: u32,
    expected_revision: u64,
) -> bool {
    let Some(mut control) = ctx.db.controller().identity().find(character) else {
        return false;
    };
    let now = now_us(ctx);
    if control.combat_target_id != 0
        || control.combat_target_life_sequence != 0
        || control.combat_target_revision != expected_revision
        || now < control.combat_target_change_not_before_us
        || valid_target(ctx, target_id, target_life_sequence).is_err()
    {
        return false;
    }
    let Some(revision) = control.combat_target_revision.checked_add(1) else {
        return false;
    };
    let Some(deadline) = now.checked_add(TARGET_CHANGE_INTERVAL_US) else {
        return false;
    };
    let Some(account) = accounts::owner_account(ctx, character) else {
        return false;
    };
    control.combat_target_id = target_id;
    control.combat_target_life_sequence = target_life_sequence;
    control.combat_target_change_not_before_us = deadline;
    control.combat_target_revision = revision;
    ctx.db.controller().identity().update(control);
    upsert_view(ctx, account, character, target_id, target_life_sequence);
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn target_arithmetic_is_checked() {
        assert_eq!(checked_revision(6).unwrap(), 7);
        assert!(checked_revision(u64::MAX).is_err());
        assert_eq!(checked_deadline(4).unwrap(), 1_000_004);
        assert!(checked_deadline(i64::MAX).is_err());
    }

    #[test]
    fn target_change_boundary_and_same_target_extension_are_exact() {
        assert!(target_change_allowed(true, 999_999, 1_000_000));
        assert!(!target_change_allowed(false, 999_999, 1_000_000));
        assert!(target_change_allowed(false, 1_000_000, 1_000_000));
    }
}
