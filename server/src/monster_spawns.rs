//! Server-owned spawn origins, separate from mutable monster position and AI clocks.
use crate::definitions::{self, MonsterSpawnDefinition};
use spacetimedb::{ReducerContext, Table};

#[spacetimedb::table(accessor = monster_origin)]
pub struct MonsterOrigin {
    #[primary_key]
    pub monster_id: u32,
    pub definition_vnum: u32,
    pub group_owner: u64,
    pub home_x: f32,
    pub home_z: f32,
}

#[spacetimedb::table(accessor = monster_allocation_cursor)]
pub struct MonsterAllocationCursor {
    #[primary_key]
    pub id: u8,
    pub last_issued: u32,
}

#[spacetimedb::table(accessor = monster_spawn_group)]
pub struct MonsterSpawnGroup {
    #[primary_key]
    pub owner: u64,
    pub regeneration_entry: u32,
    pub first_id: u32,
    pub last_id: u32,
}

pub fn initialize(ctx: &ReducerContext) {
    let last_issued = definitions::MONSTER_SPAWNS
        .iter()
        .chain(definitions::TRAINING_TARGET_SPAWNS)
        .map(|s| s.id)
        .max()
        .unwrap_or(0);
    ctx.db
        .monster_allocation_cursor()
        .insert(MonsterAllocationCursor { id: 0, last_issued });
    for spawn in definitions::MONSTER_SPAWNS
        .iter()
        .chain(definitions::TRAINING_TARGET_SPAWNS)
    {
        if definitions::ALLOCATED_MOB_FIXTURE
            && definitions::MONSTER_SPAWNS.iter().any(|s| s.id == spawn.id)
        {
            continue;
        }
        ctx.db.monster_origin().insert(MonsterOrigin {
            group_owner: 0,
            monster_id: spawn.id,
            definition_vnum: spawn.definition_vnum,
            home_x: spawn.home_x,
            home_z: spawn.home_z,
        });
    }
}

/// Authored origins must match the compiled registry. Allocated origins must
/// belong to a persisted group reservation and an installed species. Public IDs
/// alone never establish membership or authorize a spawn.
pub fn resolve(ctx: &ReducerContext, id: u32) -> Result<MonsterSpawnDefinition, String> {
    let origin = ctx
        .db
        .monster_origin()
        .monster_id()
        .find(id)
        .ok_or("Monster has no trusted spawn origin")?;
    if origin.group_owner != 0 {
        let group = ctx
            .db
            .monster_spawn_group()
            .owner()
            .find(origin.group_owner)
            .ok_or("Monster origin has no allocation group")?;
        let cursor = ctx
            .db
            .monster_allocation_cursor()
            .id()
            .find(0)
            .ok_or("Missing monster allocation cursor")?;
        if group.owner != u64::from(group.first_id)
            || group.first_id > group.last_id
            || group.last_id - group.first_id >= 256
            || id < group.first_id
            || id > group.last_id
            || group.last_id > cursor.last_issued
            || !definitions::MOB_DEFINITIONS
                .iter()
                .any(|d| d.vnum == origin.definition_vnum)
            || !origin.home_x.is_finite()
            || !origin.home_z.is_finite()
        {
            return Err("Invalid allocated monster origin".into());
        }
        return Ok(MonsterSpawnDefinition {
            id,
            definition_vnum: origin.definition_vnum,
            home_x: origin.home_x,
            home_z: origin.home_z,
        });
    }
    let expected = definitions::MONSTER_SPAWNS
        .iter()
        .chain(definitions::TRAINING_TARGET_SPAWNS)
        .find(|spawn| spawn.id == id)
        .ok_or("Monster origin is outside the installed registry")?;
    validate(&origin, expected)?;
    Ok(*expected)
}

fn validate(origin: &MonsterOrigin, expected: &MonsterSpawnDefinition) -> Result<(), String> {
    if origin.group_owner != 0
        || origin.monster_id != expected.id
        || origin.definition_vnum != expected.definition_vnum
        || !origin.home_x.is_finite()
        || !origin.home_z.is_finite()
        || origin.home_x != expected.home_x
        || origin.home_z != expected.home_z
    {
        return Err("Persisted monster origin differs from the installed spawn".into());
    }
    Ok(())
}

/// Only trusted server placement supplies templates. Insert returned public mobs
/// and clocks in this same reducer transaction; errors must abort the reducer.
pub fn allocate_group(
    ctx: &ReducerContext,
    templates: &[MonsterSpawnDefinition],
    regeneration_entry: u32,
) -> Result<Vec<MonsterSpawnDefinition>, String> {
    for template in templates {
        if !definitions::MOB_DEFINITIONS
            .iter()
            .any(|d| d.vnum == template.definition_vnum)
        {
            return Err("Group template has no registered species".into());
        }
        crate::content::valid_spawn(template.home_x, template.home_z)?;
    }
    let mut cursor = ctx
        .db
        .monster_allocation_cursor()
        .id()
        .find(0)
        .ok_or("Missing monster allocation cursor")?;
    let allocation = crate::monster_allocation::reserve(cursor.last_issued, templates.len())?;
    let mut result = Vec::new();
    for (id, template) in (allocation.first..=allocation.last).zip(templates) {
        ctx.db.monster_origin().insert(MonsterOrigin {
            monster_id: id,
            group_owner: allocation.owner(),
            definition_vnum: template.definition_vnum,
            home_x: template.home_x,
            home_z: template.home_z,
        });
        result.push(MonsterSpawnDefinition { id, ..*template });
    }
    ctx.db.monster_spawn_group().insert(MonsterSpawnGroup {
        owner: allocation.owner(),
        regeneration_entry,
        first_id: allocation.first,
        last_id: allocation.last,
    });
    cursor.last_issued = allocation.last;
    ctx.db.monster_allocation_cursor().id().update(cursor);
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn origin_validation_rejects_identity_and_home_drift() {
        let spawn = definitions::MONSTER_SPAWNS[0];
        let make = || MonsterOrigin {
            monster_id: spawn.id,
            group_owner: 0,
            definition_vnum: spawn.definition_vnum,
            home_x: spawn.home_x,
            home_z: spawn.home_z,
        };
        assert!(validate(&make(), &spawn).is_ok());
        for field in 0..6 {
            let mut origin = make();
            match field {
                0 => origin.monster_id += 1,
                1 => origin.definition_vnum += 1,
                2 => origin.home_x += 1.0,
                3 => origin.home_z += 1.0,
                4 => origin.home_x = f32::NAN,
                _ => origin.home_z = f32::INFINITY,
            }
            assert!(validate(&origin, &spawn).is_err());
        }
    }
}
