//! First shared PvE loop. Targets, cooldowns, damage, respawn and rewards are server-owned.
use crate::{active_controller, collision_bounds, content, controller, inventory, now_us, player};
use spacetimedb::{Identity, ReducerContext, Table};

const PLAYER_DAMAGE: u16 = 25;
const ATTACK_RANGE: f32 = 2.7;
const MONSTER_RANGE: f32 = 1.9;

fn within_reach(a: (f32, f32, f32), b: (f32, f32, f32), range: f32) -> bool {
    (a.0 - b.0).hypot(a.2 - b.2) <= range && (a.1 - b.1).abs() < 2.0
}

#[spacetimedb::table(accessor = monster, public)]
pub struct Monster {
    #[primary_key]
    pub id: u32,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub heading: f32,
    pub health: u16,
    pub max_health: u16,
    pub activity: u8,
    pub attack_sequence: u32,
    pub respawn_at_us: i64,
}

#[spacetimedb::table(accessor = monster_clock)]
pub struct MonsterClock {
    #[primary_key]
    pub id: u32,
    pub next_attack_us: i64,
}

#[spacetimedb::table(accessor = loot, public)]
pub struct Loot {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub gold: u32,
    pub owner: Identity,
    pub reserved_until_us: i64,
    pub expires_at_us: i64,
}

pub fn initialize(ctx: &ReducerContext) {
    ctx.db.monster().insert(fresh_monster());
    ctx.db.monster_clock().insert(MonsterClock {
        id: 1,
        next_attack_us: 0,
    });
}

fn fresh_monster() -> Monster {
    let (x, z) = content::MONSTER_HOME;
    Monster {
        id: 1,
        x,
        y: content::height(x, z),
        z,
        heading: 0.0,
        health: 100,
        max_health: 100,
        activity: 0,
        attack_sequence: 0,
        respawn_at_us: 0,
    }
}

pub fn player_attack(ctx: &ReducerContext) -> Result<(), String> {
    let bounds = collision_bounds(ctx);
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(ctx.sender())
        .ok_or("Enter the world first.")?;
    let target = ctx
        .db
        .monster()
        .iter()
        .filter(|m| m.health > 0)
        .filter(|m| {
            within_reach(
                (player.x, player.y, player.z),
                (m.x, m.y, m.z),
                ATTACK_RANGE,
            )
        })
        .filter(|m| content::clear_path(player.x, player.z, m.x, m.z, &bounds))
        .min_by(|a, b| {
            (a.x - player.x)
                .hypot(a.z - player.z)
                .total_cmp(&(b.x - player.x).hypot(b.z - player.z))
        });
    if let Some(mut monster) = target {
        player.heading = (player.x - monster.x).atan2(player.z - monster.z);
        ctx.db.player().identity().update(player);
        let damage = PLAYER_DAMAGE + inventory::weapon_bonus(ctx, ctx.sender());
        monster.health = monster.health.saturating_sub(damage);
        if monster.health == 0 {
            monster.activity = 3;
            monster.respawn_at_us = now_us(ctx) + 12_000_000;
            inventory::drop_potion(ctx, ctx.sender(), monster.x, monster.y, monster.z);
            ctx.db.loot().insert(Loot {
                id: 0,
                x: monster.x,
                y: monster.y,
                z: monster.z,
                gold: 5,
                owner: ctx.sender(),
                reserved_until_us: now_us(ctx) + 10_000_000,
                expires_at_us: now_us(ctx) + 60_000_000,
            });
        }
        ctx.db.monster().id().update(monster);
    }
    Ok(())
}

#[spacetimedb::reducer]
pub fn pickup_loot(ctx: &ReducerContext, id: u64) -> Result<(), String> {
    active_controller(ctx)?;
    let loot = ctx
        .db
        .loot()
        .id()
        .find(id)
        .ok_or("That loot has already been collected.")?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(ctx.sender())
        .ok_or("Enter the world first.")?;
    let now = now_us(ctx);
    if now >= loot.expires_at_us {
        return Err("That loot has expired.".into());
    }
    if loot.owner != ctx.sender() && now < loot.reserved_until_us {
        return Err("That loot is reserved for its slayer.".into());
    }
    if !within_reach(
        (player.x, player.y, player.z),
        (loot.x, loot.y, loot.z),
        2.5,
    ) || !content::clear_path(player.x, player.z, loot.x, loot.z, &collision_bounds(ctx))
    {
        return Err("Move closer to collect that loot.".into());
    }
    player.gold = player
        .gold
        .checked_add(loot.gold)
        .ok_or("Gold limit reached.")?;
    ctx.db.player().identity().update(player);
    ctx.db.loot().id().delete(id);
    Ok(())
}

pub fn simulate(ctx: &ReducerContext, elapsed: f32) {
    let now = now_us(ctx);
    inventory::expire_drops(ctx);
    let bounds = collision_bounds(ctx);
    for loot in ctx.db.loot().iter() {
        if now >= loot.expires_at_us {
            ctx.db.loot().id().delete(loot.id);
        }
    }
    for mut player in ctx.db.player().iter() {
        if player.health == 0 && now >= player.respawn_at_us {
            player.health = player.max_health;
            player.respawn_at_us = 0;
            player.activity = 0;
            (player.x, player.z) = content::SPAWN;
            player.y = content::height(player.x, player.z);
            ctx.db.player().identity().update(player);
        }
    }
    for mut monster in ctx.db.monster().iter() {
        if monster.health == 0 {
            if now >= monster.respawn_at_us {
                ctx.db.monster().id().update(fresh_monster());
            }
            continue;
        }
        let target = ctx
            .db
            .player()
            .iter()
            .filter(|p| p.online && p.health > 0)
            .filter(|p| (p.x - content::MONSTER_HOME.0).hypot(p.z - content::MONSTER_HOME.1) < 16.0)
            .filter(|p| (p.x - monster.x).hypot(p.z - monster.z) < 8.0)
            .filter(|p| content::clear_path(monster.x, monster.z, p.x, p.z, &bounds))
            .min_by(|a, b| {
                (a.x - monster.x)
                    .hypot(a.z - monster.z)
                    .total_cmp(&(b.x - monster.x).hypot(b.z - monster.z))
            });
        let (tx, tz) = target
            .as_ref()
            .map(|p| (p.x, p.z))
            .unwrap_or(content::MONSTER_HOME);
        let distance = (tx - monster.x).hypot(tz - monster.z);
        let mut clock = ctx.db.monster_clock().id().find(monster.id).unwrap();
        monster.activity = 0;
        if let Some(mut player) = target.filter(|p| {
            within_reach(
                (monster.x, monster.y, monster.z),
                (p.x, p.y, p.z),
                MONSTER_RANGE,
            )
        }) {
            monster.heading = (monster.x - player.x).atan2(monster.z - player.z);
            if now >= clock.next_attack_us {
                clock.next_attack_us = now + 1_300_000;
                monster.attack_sequence = monster.attack_sequence.wrapping_add(1);
                monster.activity = 2;
                player.health = player.health.saturating_sub(20);
                if player.health == 0 {
                    player.activity = 3;
                    player.respawn_at_us = now + 8_000_000;
                    if let Some(mut c) = ctx.db.controller().identity().find(player.identity) {
                        c.mode = 0;
                        c.direction_x = 0.0;
                        c.direction_z = 0.0;
                        ctx.db.controller().identity().update(c);
                    }
                }
                ctx.db.player().identity().update(player);
            }
        } else if distance > 0.1 {
            let travel = (2.4 * elapsed.clamp(0.0, 0.1)).min(distance);
            let (x, z) = content::slide(
                monster.x,
                monster.z,
                (tx - monster.x) / distance * travel,
                (tz - monster.z) / distance * travel,
                &bounds,
            );
            if (x - monster.x).hypot(z - monster.z) > 0.001 {
                monster.activity = 1;
                monster.heading = (monster.x - x).atan2(monster.z - z);
            }
            monster.x = x;
            monster.z = z;
            monster.y = content::height(x, z);
        }
        ctx.db.monster().id().update(monster);
        ctx.db.monster_clock().id().update(clock);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn melee_and_pickup_require_horizontal_and_vertical_reach() {
        let origin = (660.0, 198.0, 575.0);
        assert!(within_reach(origin, (661.5, 199.9, 575.0), MONSTER_RANGE));
        assert!(!within_reach(origin, (662.0, 198.0, 575.0), MONSTER_RANGE));
        assert!(!within_reach(origin, (660.0, 200.0, 575.0), MONSTER_RANGE));
        assert!(!within_reach(origin, (660.0, 195.9, 575.0), MONSTER_RANGE));
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            assert!(!within_reach(origin, (bad, 198.0, 575.0), ATTACK_RANGE));
            assert!(!within_reach(origin, (660.0, bad, 575.0), ATTACK_RANGE));
            assert!(!within_reach(origin, (660.0, 198.0, bad), ATTACK_RANGE));
        }
    }
}
