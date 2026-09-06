//! Server-owned item instances, grid placement, equipment, consumables and item drops.
use crate::accounts::inventory_access;
use crate::{active_controller, collision_bounds, content, now_us, player};
use spacetimedb::{Identity, ReducerContext, Table};

const SWORD: u32 = 10;
const RED_POTION: u32 = 27001;
const EQUIPPED_CELL: u8 = 255;

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
    pub cell: u8,
    pub equipped: bool,
}

#[spacetimedb::table(accessor = inventory_state)]
pub struct InventoryState {
    #[primary_key]
    pub owner: Identity,
    pub next_potion_us: i64,
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
    match vnum {
        SWORD => Ok((2, 1)),
        RED_POTION => Ok((1, 200)),
        _ => Err("Unknown item type.".into()),
    }
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
    let mut items: Vec<_> = ctx
        .db
        .inventory_item()
        .iter()
        .filter(|i| i.owner == owner)
        .collect();
    items.sort_by_key(|i| i.id);
    items
}

fn owned_item(ctx: &ReducerContext, id: u64) -> Result<InventoryItem, String> {
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
    Ok(item)
}

// Reducer transactions roll back all stack changes if a later allocation has no room.
fn grant(ctx: &ReducerContext, owner: Identity, vnum: u32, count: u16) -> Result<(), String> {
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
    for item in items
        .iter_mut()
        .filter(|i| !i.equipped && i.vnum == vnum && i.count < limit)
    {
        let added = remaining.min(limit - item.count);
        item.count += added;
        remaining -= added;
        ctx.db.inventory_item().id().update(item.clone());
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
            cell,
            equipped: false,
        });
        items.push(item);
        remaining -= count;
    }
    Ok(())
}

pub fn ensure_starter(ctx: &ReducerContext, owner: Identity) -> Result<(), String> {
    if ctx.db.inventory_state().owner().find(owner).is_some() {
        return Ok(());
    }
    grant(ctx, owner, SWORD, 1)?;
    grant(ctx, owner, RED_POTION, 5)?;
    ctx.db.inventory_state().insert(InventoryState {
        owner,
        next_potion_us: 0,
    });
    Ok(())
}

#[spacetimedb::reducer]
pub fn move_item(ctx: &ReducerContext, id: u64, cell: u8) -> Result<(), String> {
    let mut item = owned_item(ctx, id)?;
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
    ctx.db.inventory_item().id().update(item);
    Ok(())
}

#[spacetimedb::reducer]
pub fn equip_item(ctx: &ReducerContext, id: u64) -> Result<(), String> {
    let mut item = owned_item(ctx, id)?;
    if item.vnum != SWORD || item.count != 1 {
        return Err("Only a sword can be equipped in the weapon slot.".into());
    }
    if item.equipped {
        return Ok(());
    }
    let items = owned_items(ctx, crate::accounts::selected_character(ctx)?);
    if let Some(mut previous) = items.iter().find(|i| i.equipped).cloned() {
        previous.cell = free_cell(&items, previous.vnum, &[previous.id, id])?;
        previous.equipped = false;
        ctx.db.inventory_item().id().update(previous);
    }
    item.equipped = true;
    item.cell = EQUIPPED_CELL;
    ctx.db.inventory_item().id().update(item);
    Ok(())
}

#[spacetimedb::reducer]
pub fn unequip_item(ctx: &ReducerContext, id: u64, cell: u8) -> Result<(), String> {
    let mut item = owned_item(ctx, id)?;
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
    ctx.db.inventory_item().id().update(item);
    Ok(())
}

fn healed_health(health: u16, max_health: u16) -> Result<u16, String> {
    if health == 0 {
        return Err("You are defeated. Wait for respawn.".into());
    }
    if health >= max_health {
        return Err("Health is already full.".into());
    }
    Ok(health.saturating_add(40).min(max_health))
}

#[spacetimedb::reducer]
pub fn use_item(ctx: &ReducerContext, id: u64) -> Result<(), String> {
    let mut item = owned_item(ctx, id)?;
    if item.vnum != RED_POTION || item.equipped || item.count == 0 {
        return Err("That item cannot be consumed.".into());
    }
    let mut state = ctx
        .db
        .inventory_state()
        .owner()
        .find(crate::accounts::selected_character(ctx)?)
        .ok_or("Enter the world first.")?;
    let now = now_us(ctx);
    if now < state.next_potion_us {
        return Err("Potion is cooling down.".into());
    }
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(crate::accounts::selected_character(ctx)?)
        .ok_or("Enter the world first.")?;
    player.health = healed_health(player.health, player.max_health)?;
    state.next_potion_us = now.saturating_add(1_000_000);
    ctx.db.inventory_state().owner().update(state);
    ctx.db.player().identity().update(player);
    item.count -= 1;
    if item.count == 0 {
        ctx.db.inventory_item().id().delete(id);
    } else {
        ctx.db.inventory_item().id().update(item);
    }
    Ok(())
}

pub fn weapon_bonus(ctx: &ReducerContext, owner: Identity) -> u16 {
    if ctx
        .db
        .inventory_item()
        .iter()
        .any(|i| i.owner == owner && i.equipped && i.vnum == SWORD)
    {
        10
    } else {
        0
    }
}

pub fn drop_potion(ctx: &ReducerContext, owner: Identity, x: f32, y: f32, z: f32) {
    let now = now_us(ctx);
    ctx.db.item_drop().insert(ItemDrop {
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
    )?;
    ctx.db.item_drop().id().delete(id);
    Ok(())
}

pub fn expire_drops(ctx: &ReducerContext) {
    for drop in ctx.db.item_drop().iter() {
        if now_us(ctx) >= drop.expires_at_us {
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
    fn healing_and_stacks_have_server_limits() {
        assert_eq!(item_rules(RED_POTION).unwrap().1, 200);
        assert_eq!(item_rules(SWORD).unwrap().1, 1);
        assert_eq!(healed_health(20, 100).unwrap(), 60);
        assert_eq!(healed_health(90, 100).unwrap(), 100);
        assert!(healed_health(100, 100).is_err());
        assert!(healed_health(0, 100).is_err());
        assert_eq!(healed_health(65530, 65535).unwrap(), 65535);
    }
}
