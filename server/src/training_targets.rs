//! Passive practice actors share real combat, but cannot generate any rewards.
use crate::{combat::Monster, definitions};

pub fn definition(id: u32) -> Option<&'static definitions::TrainingTargetDefinition> {
    definitions::TRAINING_TARGET_SPAWNS
        .iter()
        .any(|s| s.id == id)
        .then_some(&definitions::TRAINING_TARGET)
}

pub fn validate(
    monster: &Monster,
) -> Result<Option<&'static definitions::TrainingTargetDefinition>, String> {
    let Some(d) = definition(monster.id) else {
        return Ok(None);
    };
    if monster.definition_vnum != d.vnum
        || monster.actor_id != d.actor_id
        || monster.max_health != d.health
        || monster.level != d.level
    {
        return Err("Training target differs from its trusted definition".into());
    }
    Ok(Some(d))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn training_spawns_are_distinct_and_traversable() {
        for spawn in definitions::TRAINING_TARGET_SPAWNS {
            assert!(!definitions::MONSTER_SPAWNS.iter().any(|s| s.id == spawn.id));
            crate::content::valid_spawn(spawn.home_x, spawn.home_z).unwrap();
            assert!(crate::content::clear_path(
                crate::content::SPAWN.0,
                crate::content::SPAWN.1,
                spawn.home_x,
                spawn.home_z,
                &[]
            ));
            assert!(definition(spawn.id).is_some());
        }
        assert!(definition(0).is_none());
    }
}
