//! Shared item capabilities; instance vnums resolve only against compiled definitions.
use crate::definitions::{ITEM_DEFINITIONS, ItemDefinition, ItemKind};

pub fn definition(vnum: u32) -> Result<&'static ItemDefinition, String> {
    ITEM_DEFINITIONS
        .binary_search_by_key(&vnum, |item| item.vnum)
        .map(|index| &ITEM_DEFINITIONS[index])
        .map_err(|_| "Unknown item type.".into())
}

pub fn is_weapon(vnum: u32) -> bool {
    definition(vnum).is_ok_and(|item| matches!(item.kind, ItemKind::Weapon))
}

/// Display name of an installed item, used by quest dialogue and tooling.
pub fn name(vnum: u32) -> Option<&'static str> {
    definition(vnum).ok().map(|item| item.name)
}

pub fn check_requirements(
    item: &ItemDefinition,
    level: u8,
    character_class: u8,
    sex: u8,
) -> Result<(), String> {
    if level < item.minimum_level {
        return Err("Your level is too low for that item.".into());
    }
    if character_class >= 4 || item.allowed_classes & (1 << character_class) == 0 {
        return Err("Your class cannot use that item.".into());
    }
    if sex >= 2 || item.allowed_sexes & (1 << sex) == 0 {
        return Err("Your character cannot use that item.".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn definitions_drive_both_recovery_sizes_and_equipment() {
        assert!(matches!(
            definition(27001).unwrap().kind,
            ItemKind::Recovery { hp: 300, sp: 0 }
        ));
        assert!(matches!(
            definition(27002).unwrap().kind,
            ItemKind::Recovery { hp: 800, sp: 0 }
        ));
        assert!(is_weapon(10));
        assert!(is_weapon(7000));
        for class_id in 0..4 {
            for sex in 0..2 {
                assert_eq!(
                    check_requirements(definition(7000).unwrap(), 1, class_id, sex).is_ok(),
                    class_id == 3
                );
            }
        }
        assert!(!is_weapon(27001));
        assert_eq!(name(27001), Some("Red Potion (S)"));
        assert_eq!(name(999999), None);
        assert!(definition(999999).is_err());
        let sword = definition(10).unwrap();
        assert!(check_requirements(sword, 1, 0, 0).is_ok());
        assert!(check_requirements(sword, 1, 3, 0).is_err());
        assert!(check_requirements(sword, 1, 255, 255).is_err());
    }
}
