//! Exact-life monster stun state; clients cannot create or refresh affects.
use crate::combat::{Monster, monster, monster_clock};
use spacetimedb::{ReducerContext, Table};

#[spacetimedb::table(accessor = monster_stun, public)]
pub struct MonsterStun {
    #[primary_key]
    pub monster_id: u32,
    pub life_sequence: u32,
    pub starts_at_us: i64,
    pub expires_at_us: i64,
}

pub fn stunned(ctx: &ReducerContext, victim: &Monster, now: i64) -> bool {
    ctx.db
        .monster_stun()
        .monster_id()
        .find(victim.id)
        .is_some_and(|row| {
            victim.health > 0
                && row.life_sequence == victim.life_sequence
                && row.starts_at_us <= now
                && now < row.expires_at_us
        })
}

pub fn clear(ctx: &ReducerContext, id: u32) {
    ctx.db.monster_stun().monster_id().delete(id);
}

pub fn maintain(ctx: &ReducerContext, now: i64) {
    for row in ctx.db.monster_stun().iter() {
        if now >= row.expires_at_us
            || ctx
                .db
                .monster()
                .id()
                .find(row.monster_id)
                .is_none_or(|victim| {
                    victim.health == 0 || victim.life_sequence != row.life_sequence
                })
        {
            clear(ctx, row.monster_id);
        }
    }
}

pub fn stun(
    ctx: &ReducerContext,
    victim: &mut Monster,
    now: i64,
    duration: i64,
) -> Result<(), String> {
    if !(1..=60_000_000).contains(&duration) || now < 0 || victim.health == 0 {
        return Err("Invalid monster stun state".into());
    }
    if stunned(ctx, victim, now) {
        return Ok(());
    }
    let expires_at_us = now
        .checked_add(duration)
        .ok_or("Monster stun clock overflow")?;
    clear(ctx, victim.id);
    ctx.db.monster_stun().insert(MonsterStun {
        monster_id: victim.id,
        life_sequence: victim.life_sequence,
        starts_at_us: now,
        expires_at_us,
    });
    if let Some(mut clock) = ctx.db.monster_clock().id().find(victim.id) {
        crate::combat::cancel_monster_hit(&mut clock);
        clock.attack_until_us = now;
        ctx.db.monster_clock().id().update(clock);
    }
    crate::combat::clear_monster_attack_target(victim);
    victim.activity = 0;
    victim.action_started_at_us = 0;
    victim.action_ends_at_us = 0;
    Ok(())
}
