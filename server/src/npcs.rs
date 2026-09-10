//! Stationary NPC interaction; immutable content, account-private ephemeral sessions.
//!
//! A session is only a presentation lease: the quest runtime owns every state
//! change and reward. Selecting an answer goes through `npc_choose`, which
//! re-validates the open session before the quest runtime looks at the stored
//! branches, so a client cannot answer a question that was never offered.
use crate::npc_spawns::{npc_spawn, NpcSpawn};
use crate::quest::quest_selection;
use crate::{accounts, active_controller, content, controller, definitions, now_us, player, quest};
use spacetimedb::{Filter, Identity, ReducerContext, Table};

pub const INTERACTION_DISTANCE: f32 = 5.0;
const SESSION_US: i64 = 60_000_000;
/// Bounded presentation sizes; quest text is authored but still untrusted input.
const MAX_TITLE: usize = 160;
const MAX_BODY: usize = 4096;
const MAX_OPTIONS: usize = 8;
const MAX_OPTION: usize = 200;

use definitions::{NpcAreaDialogue as AreaDialogue, NpcDefinition as Definition};

/// Position-independent conversation target. Static placements and the
/// wandering area NPCs share one dialogue path; only the source of the live
/// position differs.
struct Target {
    vnum: u32,
    name: &'static str,
    title: &'static str,
    body: &'static str,
    x: f32,
    y: f32,
    z: f32,
}

impl Target {
    fn placement(npc: &'static Definition) -> Self {
        Self {
            vnum: npc.vnum,
            name: npc.name,
            title: npc.title,
            body: npc.body,
            x: npc.x,
            y: npc.y,
            z: npc.z,
        }
    }

    fn area(dialogue: &'static AreaDialogue, live: &NpcSpawn) -> Self {
        Self {
            vnum: dialogue.vnum,
            name: dialogue.name,
            title: dialogue.title,
            body: dialogue.body,
            x: live.x_cm as f32 / 100.0,
            y: live.height_m,
            z: live.z_cm as f32 / 100.0,
        }
    }
}

/// Resolve a spawn id to its dialogue and current position. An immutable
/// placement answers directly; an area id needs the live `npc_spawn` row that
/// the placement sampler owns.
fn target(ctx: &ReducerContext, spawn_id: &str) -> Result<Target, String> {
    if let Some(npc) = definitions::NPCS.iter().find(|npc| npc.id == spawn_id) {
        return Ok(Target::placement(npc));
    }
    let dialogue = definitions::NPC_AREA_DIALOGUES
        .iter()
        .find(|row| row.id == spawn_id)
        .ok_or("That NPC does not exist in this map.")?;
    let live = ctx
        .db
        .npc_spawn()
        .spawn_id()
        .find(spawn_id.to_owned())
        .ok_or("That NPC is not here right now.")?;
    Ok(Target::area(dialogue, &live))
}

/// Live reachability for one spawn id. Area NPCs are re-checked against the
/// `npc_spawn` row, so a session cannot outlive its placement.
fn reachable(ctx: &ReducerContext, spawn_id: &str, x: f32, y: f32, z: f32) -> bool {
    if let Some(npc) = definitions::NPCS.iter().find(|npc| npc.id == spawn_id) {
        return in_range(x, y, z, npc.x, npc.y, npc.z);
    }
    ctx.db
        .npc_spawn()
        .spawn_id()
        .find(spawn_id.to_owned())
        .is_some_and(|live| {
            in_range(
                x,
                y,
                z,
                live.x_cm as f32 / 100.0,
                live.height_m,
                live.z_cm as f32 / 100.0,
            )
        })
}

#[spacetimedb::table(accessor = npc_interaction, public)]
pub struct NpcInteraction {
    #[primary_key]
    pub character_id: Identity,
    pub account: Identity,
    #[unique]
    #[auto_inc]
    pub session_id: u64,
    pub spawn_id: String,
    /// Original NPC number, the identity quest scripts trigger on.
    pub vnum: u32,
    pub title: String,
    pub body: String,
    /// Scripted answers, empty for an ordinary one-shot line.
    pub options: Vec<String>,
    pub expires_at_us: i64,
}

#[spacetimedb::client_visibility_filter]
const OWN_NPC_INTERACTION: Filter =
    Filter::Sql("SELECT * FROM npc_interaction WHERE npc_interaction.account = :sender");

fn in_range(x: f32, y: f32, z: f32, target_x: f32, target_y: f32, target_z: f32) -> bool {
    x.is_finite()
        && y.is_finite()
        && z.is_finite()
        && (x - target_x).hypot(z - target_z) <= INTERACTION_DISTANCE
        && (y - target_y).abs() <= 3.0
}

/// Clip authored text to the column budget on a character boundary.
fn bounded(text: &str, limit: usize) -> String {
    if text.chars().count() <= limit {
        return text.to_owned();
    }
    text.chars().take(limit).collect()
}

fn options_for(ctx: &ReducerContext, character: Identity, vnum: u32) -> Vec<String> {
    let Some(selection) = ctx.db.quest_selection().character_id().find(character) else {
        return Vec::new();
    };
    if selection.npc_vnum != 0 && selection.npc_vnum != vnum {
        return Vec::new();
    }
    selection
        .options
        .iter()
        .take(MAX_OPTIONS)
        .map(|option| bounded(&crate::quest::clean_line(option), MAX_OPTION))
        .collect()
}

/// Board heading for an NPC whose script offers no title of its own. The
/// authored profile title wins when present; otherwise the actor name is used,
/// which matches the original board for dynamically built ``mob_name`` titles.
fn authored_title(target: &Target) -> String {
    if target.title.is_empty() {
        bounded(target.name, MAX_TITLE)
    } else {
        bounded(target.title, MAX_TITLE)
    }
}

/// Resolve what the conversation should show. The quest runtime answers first;
/// an NPC that no script knows still says its authored line.
fn presentation(
    ctx: &ReducerContext,
    character: Identity,
    target: &Target,
) -> Result<(String, String, Vec<String>), String> {
    let dialogue = quest::on_npc_click(ctx, character, target.vnum)?;
    let fallback_options = options_for(ctx, character, target.vnum);
    if dialogue.is_empty() {
        let title = authored_title(target);
        let body = bounded(target.body, MAX_BODY);
        if fallback_options.is_empty() {
            return Ok((title, body, Vec::new()));
        }
        // A live question keeps its own text even when no click trigger matched.
        return Ok((title, body, fallback_options));
    }
    let title = if dialogue.title.is_empty() {
        authored_title(target)
    } else {
        bounded(&dialogue.title, MAX_TITLE)
    };
    let body = bounded(&dialogue.body(), MAX_BODY);
    let options = if dialogue.options.is_empty() {
        fallback_options
    } else {
        dialogue
            .options
            .iter()
            .take(MAX_OPTIONS)
            .map(|option| bounded(&crate::quest::clean_line(option), MAX_OPTION))
            .collect()
    };
    Ok((title, body, options))
}

pub fn validate_content() {
    for npc in definitions::NPCS {
        content::valid_npc_position(npc.x, npc.z).expect("NPC placement must be inside the map");
        assert!(
            (content::height(npc.x, npc.z) - npc.y).abs() < 0.02,
            "NPC height differs from terrain"
        );
    }
    // Area dialogue carries no position; the placement sampler owns that. Only
    // the shared presentation budget is checked here.
    for row in definitions::NPC_AREA_DIALOGUES {
        assert!(row.vnum != 0, "Area NPC dialogue needs a vnum");
        assert!(
            !row.name.is_empty() && row.name.len() <= MAX_TITLE,
            "Area NPC dialogue needs a bounded name"
        );
        assert!(
            row.title.chars().count() <= MAX_TITLE && row.body.len() <= MAX_BODY,
            "Area NPC dialogue exceeds the board budget"
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
    let target = target(ctx, &spawn_id)?;
    let player = ctx
        .db
        .player()
        .identity()
        .find(control.identity)
        .ok_or("Enter the world first.")?;
    if !in_range(player.x, player.y, player.z, target.x, target.y, target.z) {
        return Err("Move closer to that NPC.".into());
    }
    if !content::clear_path(
        player.x,
        player.z,
        target.x,
        target.z,
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
        if existing.spawn_id != spawn_id {
            return Err("Close the current conversation first.".into());
        }
        if existing.expires_at_us <= now {
            return Err("Close the current conversation first.".into());
        }
        // Re-clicking the open conversation refreshes it and re-renders the
        // scripted dialogue, exactly like clicking the NPC again in the
        // original client. State changes stay guarded by the quest machine.
        let (title, body, options) = presentation(ctx, control.identity, &target)?;
        let expires_at_us = now
            .checked_add(SESSION_US)
            .ok_or("NPC session deadline exhausted.")?;
        ctx.db
            .npc_interaction()
            .character_id()
            .update(NpcInteraction {
                spawn_id,
                title,
                body,
                options,
                expires_at_us,
                ..existing
            });
        return Ok(());
    }
    let expires_at_us = now
        .checked_add(SESSION_US)
        .ok_or("NPC session deadline exhausted.")?;
    control.mode = 0;
    control.direction_x = 0.0;
    control.direction_z = 0.0;
    crate::combo::cancel_queued_link(&mut control);
    crate::targeting::clear_character_target(ctx, &mut control)?;
    let (title, body, options) = presentation(ctx, control.identity, &target)?;
    ctx.db.npc_interaction().insert(NpcInteraction {
        character_id: control.identity,
        account: accounts::owner_account(ctx, control.identity)
            .ok_or("NPC interaction requires an account.")?,
        session_id: 0,
        spawn_id,
        vnum: target.vnum,
        title,
        body,
        options,
        expires_at_us,
    });
    ctx.db.controller().identity().update(control);
    Ok(())
}

/// Answer a scripted question offered by the open conversation.
#[spacetimedb::reducer]
pub fn npc_choose(ctx: &ReducerContext, session_id: u64, option: u32) -> Result<(), String> {
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
    let now = now_us(ctx);
    if row.expires_at_us <= now {
        clear(ctx, control.identity);
        return Err("That conversation has expired.".into());
    }
    let dialogue = quest::on_npc_choose(ctx, control.identity, row.vnum, option)?;
    let expires_at_us = now
        .checked_add(SESSION_US)
        .ok_or("NPC session deadline exhausted.")?;
    if dialogue.is_empty() {
        ctx.db
            .npc_interaction()
            .character_id()
            .update(NpcInteraction {
                options: Vec::new(),
                expires_at_us,
                ..row
            });
        return Ok(());
    }
    let title = if dialogue.title.is_empty() {
        row.title.clone()
    } else {
        bounded(&dialogue.title, MAX_TITLE)
    };
    ctx.db
        .npc_interaction()
        .character_id()
        .update(NpcInteraction {
            title,
            body: bounded(&dialogue.body(), MAX_BODY),
            options: dialogue
                .options
                .iter()
                .take(MAX_OPTIONS)
                .map(|option| bounded(&crate::quest::clean_line(option), MAX_OPTION))
                .collect(),
            expires_at_us,
            ..row
        });
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
                    p.online && p.health > 0 && reachable(ctx, &row.spawn_id, p.x, p.y, p.z)
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
            vnum: 20_354,
            name: "Guard",
            title: "",
            body: "Hello",
            x: 0.0,
            y: 1.0,
            z: 0.0,
        };
        let at = |x, y, z| in_range(x, y, z, n.x, n.y, n.z);
        assert!(at(3.0, 1.0, 4.0));
        assert!(!at(3.001, 1.0, 4.0));
        assert!(!at(0.0, 4.001, 0.0));
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            assert!(!at(bad, 1.0, 0.0));
            assert!(!at(0.0, bad, 0.0));
            assert!(!at(0.0, 1.0, bad));
        }
    }
    #[test]
    fn compiled_placements_use_server_terrain() {
        validate_content();
    }
}
