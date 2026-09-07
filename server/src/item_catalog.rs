//! Shared item capabilities; instance vnums resolve only against compiled definitions.
use crate::definitions::{ITEM_DEFINITIONS, ItemDefinition, ItemKind};

pub fn definition(vnum: u32) -> Result<&'static ItemDefinition, String> {
    ITEM_DEFINITIONS
        .binary_search_by_key(&vnum, |item| item.vnum)
        .map(|index| &ITEM_DEFINITIONS[index])
        .map_err(|_| "Unknown item type.".into())
}

pub fn is_weapon(vnum: u32) -> bool {
    definition(vnum).is_ok_and(|item| matches!(item.kind, ItemKind::Sword))
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
        assert!(!is_weapon(27001));
        assert!(definition(999999).is_err());
        let sword = definition(10).unwrap();
        assert!(check_requirements(sword, 1, 0, 0).is_ok());
        assert!(check_requirements(sword, 1, 3, 0).is_err());
        assert!(check_requirements(sword, 1, 255, 255).is_err());
    }
}
