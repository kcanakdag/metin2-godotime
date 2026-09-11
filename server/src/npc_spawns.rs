//! Persistent area NPC placement. No client reducer can move or reroll these rows.
use crate::{content, definitions, now_us, npc_placement};
use spacetimedb::{ReducerContext, Table, rand::Rng};

#[spacetimedb::table(accessor = npc_spawn, public)]
pub struct NpcSpawn {
    #[primary_key]
    pub spawn_id: String,
    pub actor_id: String,
    pub map_id: String,
    pub x_cm: i32,
    pub z_cm: i32,
    pub height_m: f32,
    pub heading_degrees: u16,
    pub yaw: f32,
}

#[spacetimedb::table(accessor = npc_spawn_retry)]
pub struct NpcSpawnRetry {
    #[primary_key]
    pub spawn_id: String,
    pub next_attempt_us: i64,
}

pub fn validate_content() {
    for area in definitions::NPC_AREAS {
        npc_placement::Area::new(area.bounds_cm).expect("Valid original NPC area");
        let [x0, z0, x1, z1] = area.bounds_cm;
        for (x, z) in [(x0, z0), (x0, z1), (x1, z0), (x1, z1)] {
            content::valid_npc_position(x as f32 / 100.0, z as f32 / 100.0)
                .expect("NPC area lies inside its map");
        }
        // The client renders every live area row with the same picking proxy it
        // uses for a static placement, so the conversation must exist too.
        let mut rows = definitions::NPC_AREA_DIALOGUES
            .iter()
            .filter(|row| row.id == area.id);
        let row = rows.next().expect("Area NPC needs a dialogue row");
        assert!(rows.next().is_none(), "Area NPC dialogue is duplicated");
        assert!(row.vnum != 0 && !row.name.is_empty());
    }
    for row in definitions::NPC_AREA_DIALOGUES {
        assert!(
            definitions::NPC_AREAS.iter().any(|area| area.id == row.id),
            "Area dialogue has no placement area"
        );
    }
}

pub fn maintain(ctx: &ReducerContext) -> Result<(), String> {
    let now = now_us(ctx);
    for area in definitions::NPC_AREAS {
        // The persistent primary key is the authority across connections and restarts.
        if ctx
            .db
            .npc_spawn()
            .spawn_id()
            .find(area.id.to_owned())
            .is_some()
        {
            continue;
        }
        if ctx
            .db
            .npc_spawn_retry()
            .spawn_id()
            .find(area.id.to_owned())
            .is_some_and(|r| r.next_attempt_us > now)
        {
            continue;
        }
        let result = npc_placement::Area::new(area.bounds_cm)?.sample(
            |lo, hi| ctx.rng().gen_range(lo..=hi),
            |x, z| {
                content::valid_npc_position(x, z)
                    .ok()
                    .map(|()| content::height(x, z))
            },
        )?;
        ctx.db
            .npc_spawn_retry()
            .spawn_id()
            .delete(area.id.to_owned());
        if let Some(p) = result {
            ctx.db.npc_spawn().insert(NpcSpawn {
                spawn_id: area.id.into(),
                actor_id: area.actor_id.into(),
                map_id: "metin2_map_a1".into(),
                x_cm: p.x_cm,
                z_cm: p.z_cm,
                height_m: p.height_m,
                heading_degrees: p.heading_degrees,
                yaw: p.yaw(),
            });
        } else {
            ctx.db.npc_spawn_retry().insert(NpcSpawnRetry {
                spawn_id: area.id.into(),
                next_attempt_us: now
                    .checked_add(area.respawn_interval_us)
                    .ok_or("NPC retry timestamp overflow")?,
            });
        }
    }
    Ok(())
}
