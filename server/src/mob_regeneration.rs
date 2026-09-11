//! Persisted regeneration state; selected training group exercises the live adapter.
use crate::monster_spawns::{monster_origin, monster_spawn_group};
use crate::regeneration::{EntrySnapshot, EntryState};
use spacetimedb::rand::Rng;
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

/// Which registry the persisted `monster_regeneration` rows were last reconciled
/// with. This belongs to the database, so the top-up decision survives hot-swaps
/// and rolls back with the transaction that failed to complete it.
#[spacetimedb::table(accessor = monster_regeneration_registry)]
pub struct MonsterRegenerationRegistry {
    #[primary_key]
    pub id: u8,
    pub receipt: String,
    pub entries: u32,
}

const REGISTRY_MARKER_ID: u8 = 0;

fn registry_definition(id: u32) -> Option<&'static crate::definitions::RegenerationDefinition> {
    crate::definitions::REGENERATION_DEFINITIONS
        .iter()
        .find(|d| d.id == id)
}

fn definition(id: u32) -> Result<&'static crate::definitions::RegenerationDefinition, String> {
    registry_definition(id).ok_or_else(|| {
        format!(
            "Regeneration entry is outside the installed registry ({})",
            crate::definitions::REGENERATION_REGISTRY_RECEIPT
        )
    })
}

/// `monster_regeneration` rows outlive the module that inserted them. Publishing a
/// build whose `REGENERATION_DEFINITIONS` no longer covers a persisted id used to
/// abort the whole `simulate` transaction, which froze movement, combat and the
/// simulation clock for every player in the world. Unresolvable entries are now
/// skipped instead of failing, and the row is left in place so a later build with a
/// covering registry can resume it. See `docs/development.md` on the hot-swap hazard.
fn is_resolvable(id: u32) -> bool {
    registry_definition(id).is_some()
}

fn restore(row: &MonsterRegeneration) -> Result<EntryState, String> {
    let definition = definition(row.id)?;
    EntryState::restore(
        definition.interval_us,
        definition.capacity,
        0, // Saved deadlines already include the one-time sampled jitter.
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

fn pending_registry_ids(existing: impl Fn(u32) -> bool) -> Vec<u32> {
    crate::definitions::REGENERATION_DEFINITIONS
        .iter()
        .map(|definition| definition.id)
        .filter(|id| !existing(*id))
        .collect()
}

/// Persisted rows outlive the module that inserted them, so a module whose
/// registry covers more entries than the database has rows must top up the
/// missing ones from `simulate`; `initialize` only runs when the database is
/// created. Inserting a row for an entry that did not exist when the database was
/// created is safe: it starts pending and the next tick allocates its group.
/// Existing rows are never touched — their owners, capacity and saved deadlines
/// belong to live allocations.
///
/// The marker row keeps the scan out of every tick and makes the decision
/// transactional: a rolled-back tick leaves the previous marker, so the top-up is
/// retried instead of being skipped by a process-local flag.
pub fn maintain(ctx: &ReducerContext) -> Result<(), String> {
    let installed = crate::definitions::REGENERATION_REGISTRY_RECEIPT;
    let entries = crate::definitions::REGENERATION_DEFINITIONS.len() as u32;
    if ctx
        .db
        .monster_regeneration_registry()
        .id()
        .find(REGISTRY_MARKER_ID)
        .is_some_and(|marker| marker.receipt == installed && marker.entries == entries)
    {
        return Ok(());
    }
    for id in pending_registry_ids(|id| ctx.db.monster_regeneration().id().find(id).is_some()) {
        let d = definition(id)?;
        ctx.db
            .monster_regeneration()
            .insert(row(id, &EntryState::new(d.interval_us, d.capacity, 0)?));
    }
    let marker = MonsterRegenerationRegistry {
        id: REGISTRY_MARKER_ID,
        receipt: installed.to_owned(),
        entries,
    };
    if ctx
        .db
        .monster_regeneration_registry()
        .id()
        .find(REGISTRY_MARKER_ID)
        .is_some()
    {
        ctx.db.monster_regeneration_registry().id().update(marker);
    } else {
        ctx.db.monster_regeneration_registry().insert(marker);
    }
    Ok(())
}

pub fn initialize(ctx: &ReducerContext) -> Result<(), String> {
    for d in crate::definitions::REGENERATION_DEFINITIONS {
        ctx.db
            .monster_regeneration()
            .insert(row(d.id, &EntryState::new(d.interval_us, d.capacity, 0)?));
    }
    maintain(ctx)?;
    tick(ctx)?;
    Ok(())
}

pub fn tick(ctx: &ReducerContext) -> Result<(), String> {
    for saved in ctx.db.monster_regeneration().iter() {
        if !is_resolvable(saved.id) {
            continue;
        }
        let mut state = restore(&saved)?;
        if saved.initial {
            let d = definition(saved.id)?;
            if d.interval_us > 0 {
                let jitter = ctx.rng().gen_range(0..=d.startup_jitter_max_seconds);
                state = EntryState::new(d.interval_us, d.capacity, jitter)?;
            }
        }
        let next = state.plan_tick(crate::now_us(ctx), || {
            let definition = definition(saved.id)?;
            let (templates, headings) = if let Some(area) = definition.area {
                let group = area.groups[ctx.rng().gen_range(0..area.groups.len())];
                let placed = crate::npc_placement::sample_group(
                    group,
                    area.bounds_cm,
                    |low, high| ctx.rng().gen_range(low..=high),
                    |_, x, z| {
                        crate::content::valid_spawn(x, z)
                            .ok()
                            .map(|()| crate::content::height(x, z))
                    },
                )?;
                if placed.is_empty() {
                    return Ok(None);
                }
                let templates = placed
                    .iter()
                    .map(|m| crate::definitions::MonsterSpawnDefinition {
                        id: 0,
                        definition_vnum: m.vnum,
                        home_x: m.placement.x_cm as f32 / 100.0,
                        home_z: m.placement.z_cm as f32 / 100.0,
                    })
                    .collect::<Vec<_>>();
                let headings = placed.iter().map(|m| m.placement.yaw()).collect::<Vec<_>>();
                (templates, headings)
            } else {
                (
                    definition.templates.to_vec(),
                    vec![0.0; definition.templates.len()],
                )
            };
            let members = crate::monster_spawns::allocate_group(ctx, &templates, saved.id)?;
            let owner = u64::from(
                members
                    .first()
                    .ok_or("Regeneration allocated an empty group")?
                    .id,
            );
            for (member, heading) in members.into_iter().zip(headings) {
                crate::combat::insert_allocated_monster(ctx, member, heading);
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
    // A group can reference a regeneration entry this module no longer defines.
    // Keep the corpse removal working; there is simply no capacity to release.
    let Some(saved) = ctx
        .db
        .monster_regeneration()
        .id()
        .find(group.regeneration_entry)
    else {
        ctx.db.monster_origin().monster_id().delete(monster_id);
        return Ok(false);
    };
    if u64::from(monster_id) == group.owner {
        if !is_resolvable(saved.id) {
            ctx.db.monster_origin().monster_id().delete(monster_id);
            return Ok(false);
        }
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

/// Entry aggression applies to followers as well as their original leader.
pub fn forces_aggression(ctx: &ReducerContext, monster_id: u32) -> Result<bool, String> {
    let origin = ctx
        .db
        .monster_origin()
        .monster_id()
        .find(monster_id)
        .ok_or("Monster has no origin")?;
    if origin.group_owner == 0 {
        return Ok(false);
    }
    let group = ctx
        .db
        .monster_spawn_group()
        .owner()
        .find(origin.group_owner)
        .ok_or("Monster has no group")?;
    if group.regeneration_entry == 0 {
        return Ok(false);
    }
    // An allocated group can outlive the registry entry that created it, so this
    // reports "no forced aggression" instead of failing the combat tick.
    Ok(registry_definition(group.regeneration_entry).is_some_and(|d| d.force_aggressive))
}

#[cfg(test)]
mod tests {
    use super::pending_registry_ids;
    use std::collections::HashSet;

    #[test]
    fn pending_registry_ids_selects_only_absent_entries_in_registry_order() {
        let installed = crate::definitions::REGENERATION_DEFINITIONS;
        let ids: Vec<u32> = installed.iter().map(|definition| definition.id).collect();
        assert_eq!(pending_registry_ids(|_| false), ids);
        assert!(pending_registry_ids(|_| true).is_empty());

        let existing: HashSet<u32> = ids.iter().copied().step_by(2).collect();
        assert_eq!(
            pending_registry_ids(|id| existing.contains(&id)),
            ids.iter()
                .copied()
                .filter(|id| !existing.contains(id))
                .collect::<Vec<_>>()
        );
    }
}
