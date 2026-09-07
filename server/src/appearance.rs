//! Public render state derived from server-owned character and inventory records.
use crate::accounts::account_character;
use crate::inventory::inventory_item;
use spacetimedb::{Identity, ReducerContext, Table};

const NO_WEAPON: u32 = 0;

#[spacetimedb::table(accessor = player_appearance, public)]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlayerAppearance {
    #[primary_key]
    pub character_id: Identity,
    pub empire: u8,
    pub character_class: u8,
    pub sex: u8,
    pub weapon_vnum: u32,
}

/// Rebuild the public projection from authoritative private state. There is no
/// client reducer for this table: equipment and character creation are the only
/// mutation paths.
pub fn sync(ctx: &ReducerContext, character_id: Identity) {
    let (empire, character_class, sex) = ctx
        .db
        .account_character()
        .character_id()
        .find(character_id)
        .map(|character| (character.empire, character.character_class, character.sex))
        // Guest access exists only in explicitly enabled disposable builds.
        .unwrap_or((1, 0, 0));
    let weapon_vnum = equipped_weapon(
        ctx.db
            .inventory_item()
            .owner()
            .filter(character_id)
            .map(|item| (item.vnum, item.equipped)),
    );
    let appearance = PlayerAppearance {
        character_id,
        empire,
        character_class,
        sex,
        weapon_vnum,
    };
    if ctx
        .db
        .player_appearance()
        .character_id()
        .find(character_id)
        .is_some()
    {
        ctx.db.player_appearance().character_id().update(appearance);
    } else {
        ctx.db.player_appearance().insert(appearance);
    }
}

pub fn remove(ctx: &ReducerContext, character_id: Identity) {
    ctx.db
        .player_appearance()
        .character_id()
        .delete(character_id);
}

fn equipped_weapon(items: impl IntoIterator<Item = (u32, bool)>) -> u32 {
    items
        .into_iter()
        .find_map(|(vnum, equipped)| {
            (equipped && crate::item_catalog::is_weapon(vnum)).then_some(vnum)
        })
        .unwrap_or(NO_WEAPON)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_exposes_only_the_equipped_weapon() {
        assert_eq!(equipped_weapon([(10, false), (27001, false)]), NO_WEAPON);
        assert_eq!(equipped_weapon([(27001, true)]), NO_WEAPON);
        assert_eq!(equipped_weapon([(27001, false), (10, true)]), 10);
    }
}
