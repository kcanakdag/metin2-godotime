//! Server-owned spawn origins, separate from mutable monster position and AI clocks.
use crate::definitions::{self, MonsterSpawnDefinition};
use spacetimedb::{ReducerContext, Table};

#[spacetimedb::table(accessor = monster_origin)]
pub struct MonsterOrigin {
    #[primary_key]
    pub monster_id: u32,
    pub definition_vnum: u32,
    pub home_x: f32,
    pub home_z: f32,
}

pub fn initialize(ctx: &ReducerContext) {
    for spawn in definitions::MONSTER_SPAWNS
        .iter()
        .chain(definitions::TRAINING_TARGET_SPAWNS)
    {
        ctx.db.monster_origin().insert(MonsterOrigin {
            monster_id: spawn.id,
            definition_vnum: spawn.definition_vnum,
            home_x: spawn.home_x,
            home_z: spawn.home_z,
        });
    }
}

/// Fail closed if persisted origin data differs from the currently installed
/// authored registry. Regenerated instances will need explicit owner validation
/// here when the original population is installed; an arbitrary ID is not enough.
pub fn resolve(ctx: &ReducerContext, id: u32) -> Result<MonsterSpawnDefinition, String> {
    let origin = ctx
        .db
        .monster_origin()
        .monster_id()
        .find(id)
        .ok_or("Monster has no trusted spawn origin")?;
    let expected = definitions::MONSTER_SPAWNS
        .iter()
        .chain(definitions::TRAINING_TARGET_SPAWNS)
        .find(|spawn| spawn.id == id)
        .ok_or("Monster origin is outside the installed registry")?;
    validate(&origin, expected)?;
    Ok(*expected)
}

fn validate(origin: &MonsterOrigin, expected: &MonsterSpawnDefinition) -> Result<(), String> {
    if origin.monster_id != expected.id
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn origin_validation_rejects_identity_and_home_drift() {
        let spawn = definitions::MONSTER_SPAWNS[0];
        let make = || MonsterOrigin {
            monster_id: spawn.id,
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
