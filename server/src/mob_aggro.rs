//! Server-private threat and retained victims. XP attribution stays in MonsterDamage.
use crate::combat::Monster;
use crate::mob_threat;
use crate::{Player, player};
use spacetimedb::{Identity, ReducerContext, Table};

#[spacetimedb::table(accessor = monster_threat, index(accessor = by_monster, btree(columns = [monster_id])), index(accessor = by_character, btree(columns = [character_id])))]
pub struct MonsterThreat {
    #[primary_key]
    pub id: String,
    pub monster_id: u32,
    pub monster_life: u32,
    pub character_id: Identity,
    pub character_life: u32,
    pub score: i32,
}

#[spacetimedb::table(accessor = monster_victim)]
pub struct MonsterVictim {
    #[primary_key]
    pub monster_id: u32,
    pub monster_life: u32,
    pub character_id: Identity,
    pub character_life: u32,
    pub last_set_us: i64,
    pub maximum: i32,
}

fn live_player(ctx: &ReducerContext, id: Identity, life: u32) -> Option<Player> {
    ctx.db.player().identity().find(id).filter(|p| {
        p.online
            && p.health > 0
            && p.life_sequence == life
            && p.x.is_finite()
            && p.y.is_finite()
            && p.z.is_finite()
    })
}

pub fn victim(ctx: &ReducerContext, monster: &Monster) -> Option<Player> {
    let state = ctx.db.monster_victim().monster_id().find(monster.id)?;
    if state.monster_life != monster.life_sequence {
        return None;
    }
    live_player(ctx, state.character_id, state.character_life)
}

pub fn acquire(ctx: &ReducerContext, monster: &Monster, player: &Player) {
    ctx.db.monster_victim().monster_id().delete(monster.id);
    ctx.db.monster_victim().insert(MonsterVictim {
        monster_id: monster.id,
        monster_life: monster.life_sequence,
        character_id: player.identity,
        character_life: player.life_sequence,
        last_set_us: crate::now_us(ctx),
        maximum: 0,
    });
}

pub fn record_hit(
    ctx: &ReducerContext,
    monster: &Monster,
    character: Identity,
    damage: u32,
    kind: mob_threat::DamageKind,
) -> Result<(), String> {
    let attacker = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Threat attacker is missing")?;
    if !attacker.online || attacker.health == 0 {
        return Err("Threat attacker is inactive".into());
    }
    // BeginFight establishes an initial victim before normal damage reaches the ledger.
    if victim(ctx, monster).is_none() {
        acquire(ctx, monster, &attacker);
    }
    let mut state = ctx
        .db
        .monster_victim()
        .monster_id()
        .find(monster.id)
        .ok_or("Missing threat victim")?;
    let id = format!(
        "{}/{}/{}/{}",
        monster.id, monster.life_sequence, character, attacker.life_sequence
    );
    let previous = ctx.db.monster_threat().id().find(&id);
    let total = mob_threat::accumulate(
        previous.as_ref().map_or(0, |r| r.score),
        i32::try_from(damage).map_err(|_| "Threat damage exceeds i32")?,
        kind,
        state.character_id == character && state.character_life == attacker.life_sequence,
        None,
    )
    .map_err(str::to_owned)?
    .total;
    let row = MonsterThreat {
        id,
        monster_id: monster.id,
        monster_life: monster.life_sequence,
        character_id: character,
        character_life: attacker.life_sequence,
        score: total,
    };
    if previous.is_some() {
        ctx.db.monster_threat().id().update(row);
    } else {
        ctx.db.monster_threat().insert(row);
    }
    let now = crate::now_us(ctx);
    if !mob_threat::can_reconsider(state.last_set_us, now) {
        return Ok(());
    }
    if state.character_id != character || state.character_life != attacker.life_sequence {
        if total > state.maximum {
            state.character_id = character;
            state.character_life = attacker.life_sequence;
            state.maximum = total;
            state.last_set_us = now;
        }
    } else if total > state.maximum {
        state.maximum = total;
    } else {
        let mut candidates: Vec<_> = ctx
            .db
            .monster_threat()
            .by_monster()
            .filter(monster.id)
            .filter(|r| r.monster_life == monster.life_sequence && r.score > total)
            .filter_map(|r| live_player(ctx, r.character_id, r.character_life).map(|p| (r, p)))
            .filter(|(_, p)| {
                crate::combat::source_distance_between_meters((p.x, p.z), (monster.x, monster.z))
                    .is_some_and(|distance| distance < 5000)
            })
            .collect();
        candidates.sort_by(|(a, _), (b, _)| b.score.cmp(&a.score).then_with(|| a.id.cmp(&b.id)));
        if let Some((score, p)) = candidates.first() {
            state.character_id = p.identity;
            state.character_life = p.life_sequence;
            state.maximum = score.score;
            state.last_set_us = now;
        }
    }
    ctx.db.monster_victim().monster_id().update(state);
    Ok(())
}

pub fn clear_monster(ctx: &ReducerContext, id: u32) {
    ctx.db.monster_victim().monster_id().delete(id);
    let rows: Vec<_> = ctx
        .db
        .monster_threat()
        .by_monster()
        .filter(id)
        .map(|r| r.id)
        .collect();
    for id in rows {
        ctx.db.monster_threat().id().delete(id);
    }
}

pub fn forget_character(ctx: &ReducerContext, id: Identity) {
    let rows: Vec<_> = ctx
        .db
        .monster_threat()
        .by_character()
        .filter(id)
        .map(|r| r.id)
        .collect();
    for key in rows {
        ctx.db.monster_threat().id().delete(key);
    }
    let states: Vec<_> = ctx
        .db
        .monster_victim()
        .iter()
        .filter(|r| r.character_id == id)
        .map(|r| r.monster_id)
        .collect();
    for key in states {
        ctx.db.monster_victim().monster_id().delete(key);
    }
}
