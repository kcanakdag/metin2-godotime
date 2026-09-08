//! Stationary NPC interaction; immutable content, account-private ephemeral sessions.
use crate::{accounts, active_controller, content, controller, definitions, now_us, player};
use spacetimedb::{Filter, Identity, ReducerContext, Table};

pub const INTERACTION_DISTANCE: f32 = 5.0;
const SESSION_US: i64 = 60_000_000;

use definitions::NpcDefinition as Definition;

#[spacetimedb::table(accessor = npc_interaction, public)]
pub struct NpcInteraction {
    #[primary_key]
    pub character_id: Identity,
    pub account: Identity,
    #[unique]
    #[auto_inc]
    pub session_id: u64,
    pub spawn_id: String,
    pub title: String,
    pub body: String,
    pub expires_at_us: i64,
}

#[spacetimedb::client_visibility_filter]
const OWN_NPC_INTERACTION: Filter =
    Filter::Sql("SELECT * FROM npc_interaction WHERE npc_interaction.account = :sender");

fn in_range(x: f32, y: f32, z: f32, npc: &Definition) -> bool {
    x.is_finite()
        && y.is_finite()
        && z.is_finite()
        && (x - npc.x).hypot(z - npc.z) <= INTERACTION_DISTANCE
        && (y - npc.y).abs() <= 3.0
}

pub fn validate_content() {
    for npc in definitions::NPCS {
        content::valid_npc_position(npc.x, npc.z).expect("NPC placement must be inside the map");
        assert!(
            (content::height(npc.x, npc.z) - npc.y).abs() < 0.02,
            "NPC height differs from terrain"
        );
    }
}

#[spacetimedb::reducer]
pub fn interact_npc(
    ctx: &ReducerContext,
    spawn_id: String,
    catalog_hash: String,
) -> Result<(), String> {
    let mut control = active_controller(ctx)?;
    if catalog_hash != definitions::NPC_CATALOG_HASH {
        return Err("NPC content differs from the server. Update the client.".into());
    }
    let npc = definitions::NPCS
        .iter()
        .find(|npc| npc.id == spawn_id)
        .ok_or("That NPC does not exist in this map.")?;
    let player = ctx
        .db
        .player()
        .identity()
        .find(control.identity)
        .ok_or("Enter the world first.")?;
    if !in_range(player.x, player.y, player.z, npc) {
        return Err("Move closer to that NPC.".into());
    }
    if !content::clear_path(
        player.x,
        player.z,
        npc.x,
        npc.z,
        &crate::collision_bounds(ctx),
    ) {
        return Err("The path to that NPC is blocked.".into());
    }
    let now = now_us(ctx);
    if control.attack_until_us > now {
        return Err("Finish your attack before talking.".into());
    }
    if let Some(existing) = ctx
        .db
        .npc_interaction()
        .character_id()
        .find(control.identity)
    {
        if existing.spawn_id == spawn_id && existing.expires_at_us > now {
            return Ok(());
        }
        return Err("Close the current conversation first.".into());
    }
    let expires_at_us = now
        .checked_add(SESSION_US)
        .ok_or("NPC session deadline exhausted.")?;
    control.mode = 0;
    control.direction_x = 0.0;
    control.direction_z = 0.0;
    crate::combo::cancel_queued_link(&mut control);
    ctx.db.npc_interaction().insert(NpcInteraction {
        character_id: control.identity,
        account: accounts::owner_account(ctx, control.identity)
            .ok_or("NPC interaction requires an account.")?,
        session_id: 0,
        spawn_id,
        title: npc.name.into(),
        body: npc.body.into(),
        expires_at_us,
    });
    ctx.db.controller().identity().update(control);
    Ok(())
}

#[spacetimedb::reducer]
pub fn close_npc_interaction(ctx: &ReducerContext, session_id: u64) -> Result<(), String> {
    let control = active_controller(ctx)?;
    let row = ctx
        .db
        .npc_interaction()
        .character_id()
        .find(control.identity)
        .ok_or("That conversation is already closed.")?;
    if row.session_id != session_id {
        return Err("That conversation is no longer current.".into());
    }
    clear(ctx, control.identity);
    Ok(())
}

pub fn clear(ctx: &ReducerContext, character: Identity) {
    ctx.db.npc_interaction().character_id().delete(character);
}

pub fn maintain(ctx: &ReducerContext, now: i64) {
    for row in ctx.db.npc_interaction().iter() {
        let valid = row.expires_at_us > now
            && ctx
                .db
                .player()
                .identity()
                .find(row.character_id)
                .is_some_and(|p| {
                    p.online
                        && p.health > 0
                        && definitions::NPCS
                            .iter()
                            .any(|n| n.id == row.spawn_id && in_range(p.x, p.y, p.z, n))
                });
        if !valid {
            clear(ctx, row.character_id);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn range_rejects_nonfinite_wrong_height_and_boundary_overflow() {
        let n = Definition {
            id: "n",
            name: "Guard",
            body: "Hello",
            x: 0.0,
            y: 1.0,
            z: 0.0,
        };
        assert!(in_range(3.0, 1.0, 4.0, &n));
        assert!(!in_range(3.001, 1.0, 4.0, &n));
        assert!(!in_range(0.0, 4.001, 0.0, &n));
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            assert!(!in_range(bad, 1.0, 0.0, &n));
            assert!(!in_range(0.0, bad, 0.0, &n));
            assert!(!in_range(0.0, 1.0, bad, &n));
        }
    }
    #[test]
    fn compiled_placements_use_server_terrain() {
        validate_content();
    }
}
