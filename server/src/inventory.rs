//! Server-owned item instances, grid placement, equipment, consumables and item drops.
use crate::accounts::account_character;
use crate::accounts::inventory_access;
use crate::item_security::{self, Cause};
use crate::progression::character_progression;
use crate::{active_controller, collision_bounds, content, now_us, player};
use spacetimedb::{Identity, ReducerContext, Table};

#[cfg(test)]
pub(crate) const SWORD: u32 = crate::definitions::WEAPON_VNUM;
const RED_POTION: u32 = crate::definitions::SMALL_POTION_VNUM;
const EQUIPPED_CELL: u8 = 255;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct AutomaticGrantOutcome {
    pub stacked: u16,
    pub inserted: u16,
    pub dropped: u16,
}

#[spacetimedb::table(accessor = inventory_item, public)]
#[derive(Clone)]
pub struct InventoryItem {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub owner: Identity,
    #[index(btree)]
    pub account: Identity,
    pub vnum: u32,
    pub count: u16,
    pub revision: u32,
    pub cell: u8,
    pub equipped: bool,
}

#[spacetimedb::table(accessor = inventory_state)]
pub struct InventoryState {
    #[primary_key]
    pub owner: Identity,
}

#[spacetimedb::table(accessor = item_drop, public)]
pub struct ItemDrop {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub vnum: u32,
    pub count: u16,
    pub owner: Identity,
    pub reserved_until_us: i64,
    pub expires_at_us: i64,
}

fn item_rules(vnum: u32) -> Result<(u8, u16), String> {
    let definition = crate::item_catalog::definition(vnum)?;
    Ok((definition.height, definition.stack_limit))
}

fn footprint(vnum: u32, cell: u8) -> Result<Vec<u8>, String> {
    let (height, _) = item_rules(vnum)?;
    if cell >= 90 || cell % 45 / 5 + height > 9 {
        return Err("Item must fit inside one inventory page.".into());
    }
    Ok((0..height).map(|row| cell + row * 5).collect())
}

fn can_place(items: &[InventoryItem], vnum: u32, cell: u8, exclude: &[u64]) -> Result<(), String> {
    let wanted = footprint(vnum, cell)?;
    for item in items
        .iter()
        .filter(|i| !i.equipped && !exclude.contains(&i.id))
    {
        if footprint(item.vnum, item.cell)?
            .iter()
            .any(|c| wanted.contains(c))
        {
            return Err("Those inventory cells are occupied.".into());
        }
    }
    Ok(())
}

fn free_cell(items: &[InventoryItem], vnum: u32, exclude: &[u64]) -> Result<u8, String> {
    (0..90)
        .find(|cell| can_place(items, vnum, *cell, exclude).is_ok())
        .ok_or("Not enough inventory space.".into())
}

fn owned_items(ctx: &ReducerContext, owner: Identity) -> Vec<InventoryItem> {
    let mut items: Vec<_> = ctx.db.inventory_item().owner().filter(owner).collect();
    items.sort_by_key(|i| (i.cell, i.id));
    items
}

/// Apply the source quarter-step item award without making progression depend
/// on free bag capacity. Schema/invariant failures abort the transaction; a full bag uses
/// the source's owner-reserved ground fallback in the same transaction.
pub fn grant_automatic_progression(
    ctx: &ReducerContext,
    owner: Identity,
    vnum: u32,
    count: u16,
) -> Result<AutomaticGrantOutcome, String> {
    let mut outcome = AutomaticGrantOutcome::default();
    let (_, limit) = item_rules(vnum)?;
    if count == 0 {
        return Err("Cannot grant an empty item stack.".into());
    }
    let access = ctx
        .db
        .inventory_access()
        .character_id()
        .find(owner)
        .ok_or("Automatic item owner has no inventory access.")?;
    let mut remaining = count;
    let mut items = owned_items(ctx, owner);
    validate_items(&items, access.account)?;
    for item in items
        .iter_mut()
        .filter(|item| !item.equipped && item.vnum == vnum && item.count < limit)
    {
        let added = remaining.min(limit - item.count);
        let previous_count = item.count;
        item.revision = item_security::next_revision(item.revision, item.revision)?;
        item.count += added;
        remaining -= added;
        outcome.stacked += added;
        ctx.db.inventory_item().id().update(item.clone());
        item_security::inventory(ctx, item, previous_count, Cause::Progression);
        if remaining == 0 {
            return Ok(outcome);
        }
    }
    while remaining > 0 {
        let Ok(cell) = free_cell(&items, vnum, &[]) else {
            break;
        };
        let inserted = remaining.min(limit);
        let item = ctx.db.inventory_item().insert(InventoryItem {
            id: 0,
            owner,
            account: access.account,
            vnum,
            count: inserted,
            revision: 1,
            cell,
            equipped: false,
        });
        item_security::inventory(ctx, &item, 0, Cause::Progression);
        items.push(item);
        outcome.inserted += inserted;
        remaining -= inserted;
    }
    if remaining > 0 {
        let player = ctx
            .db
            .player()
            .identity()
            .find(owner)
            .ok_or("Automatic item owner has no player row.")?;
        let now = now_us(ctx);
        while remaining > 0 {
            let count = remaining.min(limit);
            let drop = ctx.db.item_drop().insert(ItemDrop {
                id: 0,
                x: player.x,
                y: player.y,
                z: player.z,
                vnum,
                count,
                owner,
                reserved_until_us: now
                    .saturating_add(crate::definitions::AUTOMATIC_DROP_RESERVATION_US),
                expires_at_us: now.saturating_add(crate::definitions::AUTOMATIC_DROP_EXPIRY_US),
            });
            item_security::ground(ctx, &drop, true, Cause::Progression);
            outcome.dropped += count;
            remaining -= count;
        }
    }
    Ok(outcome)
}

fn validate_items(items: &[InventoryItem], account: Identity) -> Result<(), String> {
    for item in items {
        let (_, limit) = item_rules(item.vnum)?;
        if item.account != account || item.count == 0 || item.count > limit || item.revision == 0 {
            return Err("Inventory integrity check failed.".into());
        }
    }
    Ok(())
}

fn owned_item(
    ctx: &ReducerContext,
    id: u64,
    expected_revision: u32,
) -> Result<InventoryItem, String> {
    active_controller(ctx)?;
    let item = ctx
        .db
        .inventory_item()
        .id()
        .find(id)
        .ok_or("That item does not exist.")?;
    if item.owner != crate::accounts::selected_character(ctx)? {
        return Err("That item belongs to another player.".into());
    }
    validate_items(std::slice::from_ref(&item), ctx.sender())?;
    item_security::next_revision(item.revision, expected_revision)?;
    Ok(item)
}

// Reducer transactions roll back all stack changes if a later allocation has no room.
pub fn grant(
    ctx: &ReducerContext,
    owner: Identity,
    vnum: u32,
    count: u16,
    cause: Cause,
) -> Result<(), String> {
    let account = ctx
        .db
        .inventory_access()
        .character_id()
        .find(owner)
        .ok_or("Character inventory ownership is missing.")?
        .account;
    let (_, limit) = item_rules(vnum)?;
    if count == 0 {
        return Err("Cannot grant an empty item stack.".into());
    }
    let mut remaining = count;
    let mut items = owned_items(ctx, owner);
    validate_items(&items, account)?;
    for item in items
        .iter_mut()
        .filter(|i| !i.equipped && i.vnum == vnum && i.count < limit)
    {
        let added = remaining.min(limit - item.count);
        let previous_count = item.count;
        item.revision = item_security::next_revision(item.revision, item.revision)?;
        item.count += added;
        remaining -= added;
        ctx.db.inventory_item().id().update(item.clone());
        item_security::inventory(ctx, item, previous_count, cause);
        if remaining == 0 {
            return Ok(());
        }
    }
    while remaining > 0 {
        let cell = free_cell(&items, vnum, &[])?;
        let count = remaining.min(limit);
        let item = ctx.db.inventory_item().insert(InventoryItem {
            id: 0,
            owner,
            account,
            vnum,
            count,
            revision: 1,
            cell,
            equipped: false,
        });
        item_security::inventory(ctx, &item, 0, cause);
        items.push(item);
        remaining -= count;
    }
    Ok(())
}

pub fn ensure_starter(ctx: &ReducerContext, owner: Identity) -> Result<(), String> {
    if ctx.db.inventory_state().owner().find(owner).is_some() {
        return Ok(());
    }
    let appearance = crate::characters::owned_appearance(ctx, owner)?;
    let weapon = crate::characters::class(appearance.class_id)?.starter_weapon_vnum;
    if !crate::item_catalog::is_weapon(weapon) {
        return Err("The configured starter item is not a weapon.".into());
    }
    crate::item_catalog::check_requirements(
        crate::item_catalog::definition(weapon)?,
        1,
        appearance.class_id,
        appearance.sex,
    )?;
    crate::characters::attack(ctx, owner, weapon)?;
    grant(ctx, owner, weapon, 1, Cause::Starter)?;
    grant(ctx, owner, RED_POTION, 5, Cause::Starter)?;
    if crate::definitions::ITEM_RECOVERY_TEST_STARTER {
        grant(
            ctx,
            owner,
            crate::definitions::MEDIUM_POTION_VNUM,
            2,
            Cause::Starter,
        )?;
    }
    ctx.db.inventory_state().insert(InventoryState { owner });
    Ok(())
}

#[spacetimedb::reducer]
pub fn move_item(
    ctx: &ReducerContext,
    id: u64,
    cell: u8,
    expected_revision: u32,
) -> Result<(), String> {
    let mut item = owned_item(ctx, id, expected_revision)?;
    if item.equipped {
        return Err("Unequip that item before moving it.".into());
    }
    can_place(
        &owned_items(ctx, crate::accounts::selected_character(ctx)?),
        item.vnum,
        cell,
        &[id],
    )?;
    item.cell = cell;
    item.revision = item_security::next_revision(item.revision, expected_revision)?;
    ctx.db.inventory_item().id().update(item);
    Ok(())
}

#[spacetimedb::reducer]
pub fn equip_item(ctx: &ReducerContext, id: u64, expected_revision: u32) -> Result<(), String> {
    let mut item = owned_item(ctx, id, expected_revision)?;
    if !crate::item_catalog::is_weapon(item.vnum) || item.count != 1 {
        return Err("That item cannot be equipped in the weapon slot.".into());
    }
    check_item_requirements(ctx, &item)?;
    if item.equipped {
        crate::appearance::sync(ctx, item.owner);
        crate::progression::rebuild_display_projection(ctx, item.owner)?;
        return Ok(());
    }
    let items = owned_items(ctx, crate::accounts::selected_character(ctx)?);
    validate_items(&items, item.account)?;
    if let Some(mut previous) = items.iter().find(|i| i.equipped).cloned() {
        previous.cell = free_cell(&items, previous.vnum, &[previous.id, id])?;
        previous.equipped = false;
        previous.revision = item_security::next_revision(previous.revision, previous.revision)?;
        ctx.db.inventory_item().id().update(previous);
    }
    item.equipped = true;
    item.cell = EQUIPPED_CELL;
    item.revision = item_security::next_revision(item.revision, expected_revision)?;
    ctx.db.inventory_item().id().update(item);
    let character = crate::accounts::selected_character(ctx)?;
    crate::combo::cancel_queued_link_for_character(ctx, character);
    crate::appearance::sync(ctx, character);
    crate::progression::rebuild_display_projection(ctx, character)?;
    Ok(())
}

#[spacetimedb::reducer]
pub fn unequip_item(
    ctx: &ReducerContext,
    id: u64,
    cell: u8,
    expected_revision: u32,
) -> Result<(), String> {
    let mut item = owned_item(ctx, id, expected_revision)?;
    if !item.equipped {
        return Err("That item is not equipped.".into());
    }
    can_place(
        &owned_items(ctx, crate::accounts::selected_character(ctx)?),
        item.vnum,
        cell,
        &[id],
    )?;
    item.equipped = false;
    item.cell = cell;
    item.revision = item_security::next_revision(item.revision, expected_revision)?;
    ctx.db.inventory_item().id().update(item);
    let character = crate::accounts::selected_character(ctx)?;
    crate::combo::cancel_queued_link_for_character(ctx, character);
    crate::appearance::sync(ctx, character);
    crate::progression::rebuild_display_projection(ctx, character)?;
    Ok(())
}

fn check_item_requirements(ctx: &ReducerContext, item: &InventoryItem) -> Result<(), String> {
    let definition = crate::item_catalog::definition(item.vnum)?;
    let progression = ctx
        .db
        .character_progression()
        .character_id()
        .find(item.owner)
        .ok_or("Character progression is missing.")?;
    let (class, sex) = ctx
        .db
        .account_character()
        .character_id()
        .find(item.owner)
        .map_or((0, 0), |character| {
            (character.character_class, character.sex)
        });
    crate::item_catalog::check_requirements(definition, progression.level, class, sex)
}

#[spacetimedb::reducer]
pub fn use_item(ctx: &ReducerContext, id: u64, expected_revision: u32) -> Result<(), String> {
    let mut item = owned_item(ctx, id, expected_revision)?;
    if item.equipped || item.count == 0 {
        return Err("That item cannot be consumed.".into());
    }
    check_item_requirements(ctx, &item)?;
    let definition = crate::item_catalog::definition(item.vnum)?;
    crate::item_effects::apply(ctx, item.owner, definition.kind)?;
    let previous_count = item.count;
    item.count -= 1;
    item.revision = item_security::next_revision(item.revision, expected_revision)?;
    item_security::inventory(ctx, &item, previous_count, Cause::Consume);
    if item.count == 0 {
        ctx.db.inventory_item().id().delete(id);
    } else {
        ctx.db.inventory_item().id().update(item);
    }
    Ok(())
}

pub fn equipped_weapon(ctx: &ReducerContext, owner: Identity) -> u32 {
    equipped_weapon_item(ctx, owner).map_or(0, |(_, vnum)| vnum)
}

/// Total owned count of one vnum, including equipped and stacked instances.
pub fn owned_count(ctx: &ReducerContext, owner: Identity, vnum: u32) -> u32 {
    ctx.db
        .inventory_item()
        .owner()
        .filter(owner)
        .filter(|item| item.vnum == vnum)
        .map(|item| u32::from(item.count))
        .sum()
}

/// Consume up to ``count`` of one vnum, failing when the character holds less.
pub fn consume_owned(
    ctx: &ReducerContext,
    owner: Identity,
    vnum: u32,
    count: u32,
) -> Result<(), String> {
    if owned_count(ctx, owner, vnum) < count {
        return Err("You do not hold the required item.".into());
    }
    let mut remaining = count;
    let mut items: Vec<_> = ctx.db.inventory_item().owner().filter(owner).collect();
    items.sort_by_key(|item| (item.cell, item.id));
    for item in items {
        if remaining == 0 {
            break;
        }
        if item.vnum != vnum {
            continue;
        }
        let taken = remaining.min(u32::from(item.count));
        let mut updated = item.clone();
        updated.revision = item_security::next_revision(item.revision, item.revision)?;
        updated.count = item.count - taken as u16;
        if updated.count == 0 {
            item_security::inventory(ctx, &item, item.count, Cause::Quest);
            ctx.db.inventory_item().id().delete(item.id);
        } else {
            ctx.db.inventory_item().id().update(updated.clone());
            item_security::inventory(ctx, &updated, item.count, Cause::Quest);
        }
        remaining -= taken;
    }
    if remaining != 0 {
        return Err("The held item quantity changed during the exchange.".into());
    }
    Ok(())
}

pub fn equipped_weapon_item(ctx: &ReducerContext, owner: Identity) -> Option<(u64, u32)> {
    ctx.db
        .inventory_item()
        .owner()
        .filter(owner)
        .find_map(|item| {
            (item.equipped && crate::item_catalog::is_weapon(item.vnum))
                .then_some((item.id, item.vnum))
        })
}

pub fn drop_potion(ctx: &ReducerContext, owner: Identity, x: f32, y: f32, z: f32) {
    let now = now_us(ctx);
    let drop = ctx.db.item_drop().insert(ItemDrop {
        id: 0,
        x,
        y,
        z,
        vnum: RED_POTION,
        count: 1,
        owner,
        reserved_until_us: now.saturating_add(10_000_000),
        expires_at_us: now.saturating_add(60_000_000),
    });
    item_security::ground(ctx, &drop, true, Cause::Monster);
}

#[spacetimedb::reducer]
pub fn pickup_item_drop(ctx: &ReducerContext, id: u64) -> Result<(), String> {
    active_controller(ctx)?;
    let drop = ctx
        .db
        .item_drop()
        .id()
        .find(id)
        .ok_or("That item drop has already been collected.")?;
    let now = now_us(ctx);
    if now >= drop.expires_at_us {
        return Err("That item drop has expired.".into());
    }
    if drop.owner != crate::accounts::selected_character(ctx)? && now < drop.reserved_until_us {
        return Err("That item drop is reserved for its slayer.".into());
    }
    let player = ctx
        .db
        .player()
        .identity()
        .find(crate::accounts::selected_character(ctx)?)
        .ok_or("Enter the world first.")?;
    if (drop.x - player.x).hypot(drop.z - player.z) > 2.5
        || (drop.y - player.y).abs() >= 2.0
        || !content::clear_path(player.x, player.z, drop.x, drop.z, &collision_bounds(ctx))
    {
        return Err("Move closer to collect that item drop.".into());
    }
    grant(
        ctx,
        crate::accounts::selected_character(ctx)?,
        drop.vnum,
        drop.count,
        Cause::Pickup(drop.id),
    )?;
    item_security::ground(ctx, &drop, false, Cause::Pickup(drop.id));
    ctx.db.item_drop().id().delete(id);
    Ok(())
}

pub fn expire_drops(ctx: &ReducerContext) {
    for drop in ctx.db.item_drop().iter() {
        if now_us(ctx) >= drop.expires_at_us {
            item_security::ground(ctx, &drop, false, Cause::Expiry);
            ctx.db.item_drop().id().delete(drop.id);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn potion(id: u64, cell: u8) -> InventoryItem {
        InventoryItem {
            id,
            owner: Identity::ZERO,
            account: Identity::ZERO,
            vnum: RED_POTION,
            count: 1,
            revision: 1,
            cell,
            equipped: false,
        }
    }

    #[test]
    fn vertical_items_fit_each_page_without_wrapping() {
        assert_eq!(footprint(SWORD, 39).unwrap(), [39, 44]);
        assert_eq!(footprint(SWORD, 84).unwrap(), [84, 89]);
        for cell in [40, 44, 85, 89, 90, 255] {
            assert!(footprint(SWORD, cell).is_err());
        }
        assert_eq!(footprint(RED_POTION, 89).unwrap(), [89]);
        assert!(footprint(RED_POTION, 90).is_err());
        assert!(footprint(123, 0).is_err());
    }

    #[test]
    fn occupancy_checks_every_cell_and_excludes_only_the_moved_item() {
        let items = [potion(1, 5), potion(2, 46)];
        assert!(can_place(&items, SWORD, 0, &[]).is_err());
        assert!(can_place(&items, SWORD, 0, &[1]).is_ok());
        assert!(can_place(&items, SWORD, 1, &[]).is_ok());
        assert!(can_place(&items, SWORD, 46, &[1]).is_err());
    }

    #[test]
    fn full_inventory_cannot_accept_an_unequipped_weapon() {
        let mut items: Vec<_> = (0..90)
            .map(|cell| potion(u64::from(cell) + 1, cell))
            .collect();
        assert!(free_cell(&items, SWORD, &[]).is_err());
        items.retain(|i| ![39, 44].contains(&i.cell));
        assert_eq!(free_cell(&items, SWORD, &[]).unwrap(), 39);
    }

    #[test]
    fn stacks_have_definition_limits() {
        assert_eq!(item_rules(RED_POTION).unwrap().1, 200);
        assert_eq!(item_rules(SWORD).unwrap().1, 1);
    }
}
