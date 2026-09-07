//! Class IDs and appearances resolve only against the compiled character catalog.

use crate::accounts::account_character;
use crate::definitions::{self, AttackDefinition};
use crate::definitions::{
    CHARACTER_APPEARANCES, CHARACTER_CLASSES, CharacterAppearanceDefinition,
    CharacterClassDefinition,
};
use spacetimedb::{Identity, ReducerContext};

pub fn class(id: u8) -> Result<&'static CharacterClassDefinition, String> {
    CHARACTER_CLASSES
        .get(usize::from(id))
        .filter(|row| row.id == id)
        .ok_or("Unknown character class.".into())
}

pub fn appearance(class_id: u8, sex: u8) -> Result<&'static CharacterAppearanceDefinition, String> {
    CHARACTER_APPEARANCES
        .iter()
        .find(|row| row.class_id == class_id && row.sex == sex)
        .ok_or("Unknown character appearance.".into())
}

pub fn owned_appearance(
    ctx: &ReducerContext,
    character: Identity,
) -> Result<&'static CharacterAppearanceDefinition, String> {
    let row = ctx
        .db
        .account_character()
        .character_id()
        .find(character)
        .ok_or("Character ownership is missing.")?;
    appearance(row.character_class, row.sex)
}

pub fn stat_attack(
    class_id: u8,
    strength: u8,
    dexterity: u8,
    intelligence: u8,
) -> Result<i32, String> {
    class(class_id)?;
    let strength = i32::from(strength);
    Ok(match class_id {
        1 => (4 * strength + 2 * i32::from(dexterity)) / 3,
        3 => (4 * strength + 2 * i32::from(intelligence)) / 3,
        _ => 2 * strength,
    })
}

pub fn attack(
    ctx: &ReducerContext,
    character: Identity,
    weapon: u32,
) -> Result<&'static AttackDefinition, String> {
    let selected = owned_appearance(ctx, character)?;
    if selected.actor_id == "actor.player.warrior-male" {
        return match weapon {
            0 => Ok(&definitions::PLAYER_GENERAL_ATTACK),
            10 => Ok(&definitions::PLAYER_ONEHAND_ATTACK),
            _ => Err("Unsupported character weapon.".into()),
        };
    }
    definitions::CHARACTER_BASIC_ATTACKS
        .iter()
        .find(|(actor, vnum, _)| *actor == selected.actor_id && *vnum == weapon)
        .map(|(_, _, definition)| definition)
        .ok_or("This character has no action for that weapon.".into())
}

pub fn requires_weapon(action_id: &str) -> bool {
    definitions::PLAYER_ONEHAND_COMBO
        .iter()
        .any(|action| action.id == action_id)
        || definitions::CHARACTER_BASIC_ATTACKS
            .iter()
            .any(|(_, weapon, action)| *weapon != 0 && action.id == action_id)
}

pub fn combo_start(action_id: &str) -> bool {
    action_id == definitions::PLAYER_ONEHAND_COMBO[0].id
        || definitions::CHARACTER_BASIC_ATTACKS
            .iter()
            .any(|(_, weapon, action)| {
                *weapon == 10 && action.id == action_id && action.id.ends_with(".combo_1")
            })
}

pub fn combo_step(
    ctx: &ReducerContext,
    character: Identity,
    step: u8,
) -> Result<&'static AttackDefinition, String> {
    if !(1..=4).contains(&step) {
        return Err("Invalid common combo step.".into());
    }
    let selected = owned_appearance(ctx, character)?;
    if selected.actor_id == "actor.player.warrior-male" {
        return Ok(&definitions::PLAYER_ONEHAND_COMBO[usize::from(step - 1)]);
    }
    let suffix = format!(".combo_{step}");
    definitions::CHARACTER_BASIC_ATTACKS
        .iter()
        .find(|(actor, weapon, action)| {
            *actor == selected.actor_id && *weapon == 10 && action.id.ends_with(&suffix)
        })
        .map(|(_, _, action)| action)
        .ok_or("The selected class has no common sword combo.".into())
}

pub fn root_actions() -> impl Iterator<Item = &'static AttackDefinition> {
    definitions::PLAYER_ONEHAND_COMBO.iter().chain(
        definitions::CHARACTER_BASIC_ATTACKS
            .iter()
            .map(|(_, _, action)| action),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_added_sword_chain_has_three_links_and_a_valid_terminal_hit() {
        for appearance in CHARACTER_APPEARANCES {
            if appearance.class_id == 3 || appearance.actor_id == "actor.player.warrior-male" {
                continue;
            }
            let steps: Vec<_> = definitions::CHARACTER_BASIC_ATTACKS
                .iter()
                .filter(|(actor, weapon, _)| *actor == appearance.actor_id && *weapon == 10)
                .map(|(_, _, action)| action)
                .collect();
            assert_eq!(steps.len(), 4);
            for (index, action) in steps.iter().enumerate() {
                assert!(action.id.ends_with(&format!(".combo_{}", index + 1)));
                assert_eq!(action.combo_input.is_some(), index < 3);
                assert_eq!(combo_start(action.id), index == 0);
                assert!(requires_weapon(action.id));
                if let Some(input) = action.combo_input {
                    assert!(input.pre_input_us < input.direct_input_us);
                    assert!(input.direct_input_us <= input.input_limit_us);
                    assert!(input.input_limit_us <= action.duration_us);
                }
                if action.special_area.is_some() {
                    assert_eq!((action.hit_start_us, action.hit_end_us), (0, 0));
                    assert_eq!(action.ordinary_hit_invulnerability_us, 0);
                } else {
                    assert!(action.hit_start_us > 0 && action.hit_start_us < action.hit_end_us);
                }
                crate::special_area::validate_action_definition(action).unwrap();
                crate::root_motion::validate_action_definition(action).unwrap();
            }
        }
    }

    #[test]
    fn all_class_appearances_and_source_stats_resolve() {
        for id in 0..4 {
            for sex in 0..2 {
                assert!(appearance(id, sex).is_ok());
            }
        }
        assert!(appearance(4, 0).is_err());
        assert!(appearance(0, 2).is_err());
        assert_eq!(class(0).unwrap().base_hp, 600);
        assert_eq!(class(1).unwrap().dexterity, 6);
        assert_eq!(class(2).unwrap().intelligence, 5);
        assert_eq!(class(3).unwrap().base_hp, 700);
        assert_eq!(stat_attack(0, 6, 3, 3).unwrap(), 12);
        assert_eq!(stat_attack(1, 4, 6, 3).unwrap(), 9);
        assert_eq!(stat_attack(2, 5, 3, 5).unwrap(), 10);
        assert_eq!(stat_attack(3, 3, 3, 6).unwrap(), 8);
        assert!(stat_attack(255, 3, 3, 6).is_err());
    }
}
