//! Persisted regeneration state; selected training group exercises the live adapter.
use crate::monster_spawns::{monster_origin, monster_spawn_group};
use crate::regeneration::{EntrySnapshot, EntryState};
use spacetimedb::{ReducerContext, Table};

#[spacetimedb::table(accessor = monster_regeneration)]
pub struct MonsterRegeneration {
    #[primary_key]
    pub id: u32,
    pub next_tick_us: Option<i64>,
    pub initial: bool,
    pub owners: Vec<u64>,
    pub last_owner: u64,
}

fn restore(row: &MonsterRegeneration) -> Result<EntryState, String> {
    if !crate::definitions::REGENERATING_MOB_FIXTURE || row.id != 1 {
        return Err("Regeneration entry is outside the installed fixture".into());
    }
    EntryState::restore(
        5_000_000,
        1,
        0,
        EntrySnapshot {
            next_tick_us: row.next_tick_us,
            initial: row.initial,
            owners: row.owners.clone(),
            last_owner: row.last_owner,
        },
    )
}

fn row(id: u32, state: &EntryState) -> MonsterRegeneration {
    let s = state.snapshot();
    MonsterRegeneration {
        id,
        next_tick_us: s.next_tick_us,
        initial: s.initial,
        owners: s.owners,
        last_owner: s.last_owner,
    }
}

pub fn initialize(ctx: &ReducerContext) -> Result<(), String> {
    if crate::definitions::REGENERATING_MOB_FIXTURE {
        ctx.db
            .monster_regeneration()
            .insert(row(1, &EntryState::new(5_000_000, 1, 0)?));
        tick(ctx)?;
    }
    Ok(())
}

pub fn tick(ctx: &ReducerContext) -> Result<(), String> {
    for saved in ctx.db.monster_regeneration().iter() {
        let state = restore(&saved)?;
        let next = state.plan_tick(crate::now_us(ctx), || {
            let members = crate::monster_spawns::allocate_group(
                ctx,
                crate::definitions::MONSTER_SPAWNS,
                saved.id,
            )?;
            let owner = u64::from(
                members
                    .first()
                    .ok_or("Regeneration allocated an empty group")?
                    .id,
            );
            for member in members {
                crate::combat::insert_allocated_monster(ctx, member);
            }
            Ok(Some(owner))
        })?;
        if state != next {
            ctx.db
                .monster_regeneration()
                .id()
                .update(row(saved.id, &next));
        }
    }
    Ok(())
}

/// Called at corpse destruction, never lethal damage. Surviving followers retain
/// their origins/group even when their leader releases the entry's capacity.
pub fn destroy(ctx: &ReducerContext, monster_id: u32) -> Result<bool, String> {
    let origin = ctx
        .db
        .monster_origin()
        .monster_id()
        .find(monster_id)
        .ok_or("Destroyed monster has no origin")?;
    if origin.group_owner == 0 {
        return Ok(false);
    }
    let group = ctx
        .db
        .monster_spawn_group()
        .owner()
        .find(origin.group_owner)
        .ok_or("Destroyed monster has no allocation group")?;
    if group.regeneration_entry == 0 {
        return Ok(false);
    }
    let saved = ctx
        .db
        .monster_regeneration()
        .id()
        .find(group.regeneration_entry)
        .ok_or("Destroyed monster has no regeneration entry")?;
    if u64::from(monster_id) == group.owner {
        let mut state = restore(&saved)?;
        if !state.owner_destroyed(group.owner) {
            return Err("Leader has no regeneration capacity to release".into());
        }
        ctx.db
            .monster_regeneration()
            .id()
            .update(row(saved.id, &state));
    }
    ctx.db.monster_origin().monster_id().delete(monster_id);
    if !(group.first_id..=group.last_id)
        .any(|id| ctx.db.monster_origin().monster_id().find(id).is_some())
    {
        ctx.db.monster_spawn_group().owner().delete(group.owner);
    }
    Ok(true)
}
