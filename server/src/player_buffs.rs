//! Server-owned persisted skill affects. Ordinary skill duration pauses offline.
use crate::buff_lifecycle::{Effects, Modifier, Point, SkillAffect};
use crate::progression::{CharacterProgression, character_progression};
use crate::skills::CharacterSkill;
use crate::{Controller, accounts, controller, definitions, now_us, player};
use spacetimedb::{Identity, ReducerContext, Table};

#[derive(Clone, spacetimedb::SpacetimeType)]
pub struct SavedBuffModifier {
    pub point: u8,
    pub value: i32,
    pub remaining_ticks: u32,
}

#[spacetimedb::table(accessor = character_buff)]
#[derive(Clone)]
pub struct CharacterBuff {
    #[primary_key]
    pub id: String,
    #[index(btree)]
    pub character_id: Identity,
    pub skill_vnum: u16,
    pub life_sequence: u32,
    pub active_since_us: i64,
    pub next_tick_us: i64,
    pub modifiers: Vec<SavedBuffModifier>,
}

fn point(code: u8) -> Result<Point, String> {
    match code {
        0 => Ok(Point::AttackSpeed),
        1 => Ok(Point::MovementSpeed),
        2 => Ok(Point::AttackGrade),
        3 => Ok(Point::NormalDamageTakenPercent),
        _ => Err("Invalid saved buff point".into()),
    }
}

fn saved(modifier: &Modifier) -> SavedBuffModifier {
    SavedBuffModifier {
        point: match modifier.point {
            Point::AttackSpeed => 0,
            Point::MovementSpeed => 1,
            Point::AttackGrade => 2,
            Point::NormalDamageTakenPercent => 3,
        },
        value: modifier.value,
        remaining_ticks: modifier.remaining_ticks,
    }
}

fn restore(row: &CharacterBuff) -> Result<Effects, String> {
    let mut effects = Effects::default();
    effects.replace(SkillAffect {
        skill_vnum: row.skill_vnum,
        modifiers: row
            .modifiers
            .iter()
            .map(|value| {
                Ok(Modifier {
                    point: point(value.point)?,
                    value: value.value,
                    remaining_ticks: value.remaining_ticks,
                })
            })
            .collect::<Result<_, String>>()?,
    })?;
    Ok(effects)
}

pub fn clear(ctx: &ReducerContext, character: Identity) {
    for row in ctx.db.character_buff().character_id().filter(character) {
        ctx.db.character_buff().id().delete(row.id);
    }
    refresh_speed(ctx, character)
        .unwrap_or_else(|error| panic!("cannot refresh cleared buff speed: {error}"));
}

pub fn refresh_speed(ctx: &ReducerContext, character: Identity) -> Result<(), String> {
    if let Some(mut row) = ctx
        .db
        .character_progression()
        .character_id()
        .find(character)
    {
        let speed = crate::attack_timing::equipped_speed(ctx, character)?;
        if row.display_attack_speed != speed {
            row.display_attack_speed = speed;
            ctx.db.character_progression().character_id().update(row);
        }
    }
    Ok(())
}

/// Keep expired intervals until the movement pass has consumed their overlap.
pub fn movement_effects(
    ctx: &ReducerContext,
    control: &Controller,
    owner: &crate::Player,
) -> Result<Vec<crate::movement::SpeedEffect>, String> {
    if control.identity != owner.identity
        || !owner.online
        || owner.health == 0
        || !accounts::controller_has_active_lease(ctx, control)
    {
        return Ok(Vec::new());
    }
    let mut effects = Vec::new();
    for row in ctx
        .db
        .character_buff()
        .character_id()
        .filter(owner.identity)
    {
        if row.life_sequence != owner.life_sequence || row.next_tick_us == 0 {
            continue;
        }
        restore(&row)?;
        for modifier in &row.modifiers {
            if point(modifier.point)? == Point::MovementSpeed {
                let expires_at_us = row
                    .next_tick_us
                    .checked_add(i64::from(modifier.remaining_ticks - 1) * 1_000_000)
                    .ok_or("Buff movement clock overflow")?;
                effects.push(crate::movement::SpeedEffect {
                    starts_at_us: row.active_since_us,
                    expires_at_us,
                    bonus_points: modifier.value,
                });
            }
        }
    }
    Ok(effects)
}

/// Read current contributions without waiting for the next maintenance tick.
/// Paused rows and rows from another life never grant live stats.
pub fn bonus(ctx: &ReducerContext, character: Identity, wanted: Point) -> Result<i32, String> {
    let Some(owner) = ctx.db.player().identity().find(character) else {
        return Ok(0);
    };
    if !owner.online
        || owner.health == 0
        || !ctx
            .db
            .controller()
            .identity()
            .find(character)
            .is_some_and(|control| accounts::controller_has_active_lease(ctx, &control))
    {
        return Ok(0);
    }
    let mut total = 0_i32;
    for row in ctx.db.character_buff().character_id().filter(character) {
        if row.life_sequence != owner.life_sequence || row.next_tick_us == 0 {
            continue;
        }
        if let Some(current) = elapsed_row(row, now_us(ctx), false)? {
            total = total
                .checked_add(restore(&current)?.bonus(wanted))
                .ok_or("Buff contribution overflow")?;
        }
    }
    Ok(total)
}

/// Prepare the complete persisted transition before changing the database.
fn elapsed_row(
    mut row: CharacterBuff,
    now: i64,
    pause: bool,
) -> Result<Option<CharacterBuff>, String> {
    if now < 0 || row.next_tick_us < 0 || row.active_since_us < 0 {
        return Err("Invalid buff clock".into());
    }
    let mut effects = restore(&row)?;
    if row.next_tick_us > 0 && now >= row.next_tick_us {
        let ticks = 1 + (now - row.next_tick_us) / 1_000_000;
        effects.advance(u32::try_from(ticks).unwrap_or(u32::MAX));
        row.next_tick_us = now
            .checked_add(1_000_000 - (now - row.next_tick_us) % 1_000_000)
            .ok_or("Buff clock overflow")?;
    }
    let Some(effect) = effects.entries().first() else {
        return Ok(None);
    };
    row.modifiers = effect.modifiers.iter().map(saved).collect();
    if pause {
        row.next_tick_us = 0;
    }
    Ok(Some(row))
}

fn advance(ctx: &ReducerContext, row: CharacterBuff, now: i64, pause: bool) -> Result<(), String> {
    let character = row.character_id;
    let id = row.id.clone();
    if let Some(updated) = elapsed_row(row, now, pause)? {
        ctx.db.character_buff().id().update(updated);
    } else {
        ctx.db.character_buff().id().delete(id);
    }
    refresh_speed(ctx, character)
}

pub fn pause(ctx: &ReducerContext, character: Identity) -> Result<(), String> {
    for row in ctx.db.character_buff().character_id().filter(character) {
        advance(ctx, row, now_us(ctx), true)?;
    }
    Ok(())
}

pub fn resume(ctx: &ReducerContext, character: Identity) -> Result<(), String> {
    let player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Buff owner missing")?;
    let next_tick = now_us(ctx)
        .checked_add(1_000_000)
        .ok_or("Buff clock overflow")?;
    for mut row in ctx.db.character_buff().character_id().filter(character) {
        if player.health == 0 || row.life_sequence != player.life_sequence {
            ctx.db.character_buff().id().delete(row.id);
        } else if row.next_tick_us == 0 {
            row.active_since_us = now_us(ctx);
            row.next_tick_us = next_tick;
            ctx.db.character_buff().id().update(row);
        }
    }
    Ok(())
}

pub fn maintain(ctx: &ReducerContext, now: i64) -> Result<(), String> {
    for row in ctx.db.character_buff().iter() {
        let Some(owner) = ctx.db.player().identity().find(row.character_id) else {
            ctx.db.character_buff().id().delete(row.id);
            continue;
        };
        if owner.health == 0 || owner.life_sequence != row.life_sequence {
            ctx.db.character_buff().id().delete(row.id);
            refresh_speed(ctx, owner.identity)?;
            continue;
        }
        let online = owner.online
            && ctx
                .db
                .controller()
                .identity()
                .find(owner.identity)
                .is_some_and(|control| accounts::controller_has_active_lease(ctx, &control));
        if row.next_tick_us != 0 && (!online || now >= row.next_tick_us) {
            advance(ctx, row, now, !online)?;
        }
    }
    Ok(())
}

pub fn activate(
    ctx: &ReducerContext,
    control: &mut Controller,
    mut progression: CharacterProgression,
    mut skill: CharacterSkill,
    definition: &crate::buff_capture::Definition<'_>,
    now: i64,
) -> Result<(), String> {
    let owner = ctx
        .db
        .player()
        .identity()
        .find(control.identity)
        .ok_or("Buff owner missing")?;
    if !owner.online
        || owner.health == 0
        || progression.character_id != owner.identity
        || skill.character_id != owner.identity
        || !accounts::controller_has_active_lease(ctx, control)
    {
        return Err("Buff requires the living selected controller".into());
    }
    let power = u8::try_from(
        *definitions::SKILL_POWERS
            .get(usize::from(skill.rank))
            .ok_or("Invalid buff rank")?,
    )
    .map_err(|_| "Invalid buff power")?;
    let mut variables = [0.0; crate::skill_formula::VARIABLE_COUNT];
    variables[1] = f64::from(progression.strength);
    variables[2] = f64::from(progression.dexterity);
    variables[3] = f64::from(progression.vitality);
    variables[5] = f64::from(progression.level);
    variables[6] = f64::from(progression.intelligence);
    let captured = crate::buff_capture::capture(definition, &variables, power)?;
    let appearance = crate::characters::owned_appearance(ctx, owner.identity)?;
    let action = &definitions::SKILL_ACTIONS
        .iter()
        .find(|(vnum, actor, _)| *vnum == skill.skill_vnum && *actor == appearance.actor_id)
        .ok_or("Buff animation is unavailable")?
        .2;
    let events = definitions::SKILL_EVENT_WINDOWS
        .iter()
        .find(|(vnum, actor, _)| *vnum == skill.skill_vnum && *actor == appearance.actor_id)
        .ok_or("Buff event definition is unavailable")?
        .2;
    if !events.is_empty()
        || action.special_area.is_some()
        || action.hit_start_us != 0
        || action.hit_end_us != 0
    {
        return Err("Buff motion cannot schedule damage".into());
    }
    let id = format!("{}:{}", owner.identity, skill.skill_vnum);
    let previous = ctx.db.character_buff().id().find(&id);
    let existing = previous
        .as_ref()
        .map(restore)
        .transpose()?
        .unwrap_or_default();
    let activation = crate::buff_activation::SkillState {
        vnum: skill.skill_vnum,
        rank: skill.rank,
        revision: skill.revision,
        ready_at_us: skill.ready_at_us,
    }
    .activate(
        skill.revision,
        captured,
        progression.current_sp,
        &existing,
        now,
    )?;
    let next_tick_us = ctx
        .db
        .character_buff()
        .character_id()
        .filter(owner.identity)
        .filter(|row| row.next_tick_us > now)
        .map(|row| row.next_tick_us)
        .min()
        .unwrap_or(now.checked_add(1_000_000).ok_or("Buff clock overflow")?);
    let effect = activation
        .effects
        .entries()
        .iter()
        .find(|effect| effect.skill_vnum == skill.skill_vnum)
        .ok_or("Buff activation omitted effect")?;
    let row = CharacterBuff {
        id,
        character_id: owner.identity,
        skill_vnum: skill.skill_vnum,
        life_sequence: owner.life_sequence,
        active_since_us: now,
        next_tick_us,
        modifiers: effect.modifiers.iter().map(saved).collect(),
    };
    // Settle the previous interval before replacing its modifiers. Starting the
    // action then blocks further ordinary travel until its recovery boundary.
    crate::root_motion::advance_for_replacement(ctx, control, now)?;
    crate::combo::clear_chain(control);
    crate::combat::cancel_player_attack(control);
    crate::npcs::clear(ctx, owner.identity);
    crate::skills::clear(ctx, owner.identity);
    crate::combat::start_player_action(
        ctx,
        control,
        crate::combat::PlayerAttackPlan {
            definition: action,
            target_id: 0,
            target_generation: 0,
            heading: None,
            can_select_target: false,
        },
        now,
    )?;
    ctx.db.controller().identity().update(control.clone());
    progression.current_sp = activation.remaining_sp;
    skill.revision = activation.skill.revision;
    skill.ready_at_us = activation.skill.ready_at_us;
    ctx.db
        .character_progression()
        .character_id()
        .update(progression);
    crate::skills::store(ctx, skill);
    if previous.is_some() {
        ctx.db.character_buff().id().update(row);
    } else {
        ctx.db.character_buff().insert(row);
    }
    refresh_speed(ctx, owner.identity)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> CharacterBuff {
        CharacterBuff {
            id: "test:3".into(),
            character_id: Identity::from_byte_array([1; 32]),
            skill_vnum: 3,
            life_sequence: 1,
            active_since_us: 1_000_000,
            next_tick_us: 2_000_000,
            modifiers: vec![
                SavedBuffModifier {
                    point: 0,
                    value: 25,
                    remaining_ticks: 3,
                },
                SavedBuffModifier {
                    point: 1,
                    value: 10,
                    remaining_ticks: 5,
                },
            ],
        }
    }

    #[test]
    fn buff_saved_ticks_preserve_phase_catch_up_and_expire_each_modifier() {
        let before = elapsed_row(fixture(), 1_999_999, false).unwrap().unwrap();
        assert_eq!(before.modifiers[0].remaining_ticks, 3);
        let due = elapsed_row(before, 2_000_000, false).unwrap().unwrap();
        assert_eq!(due.modifiers[0].remaining_ticks, 2);
        assert_eq!(due.next_tick_us, 3_000_000);
        let late = elapsed_row(due, 4_700_000, false).unwrap().unwrap();
        assert_eq!(late.next_tick_us, 5_000_000);
        assert_eq!(late.modifiers.len(), 1);
        assert_eq!(late.modifiers[0].point, 1);
        assert_eq!(late.modifiers[0].remaining_ticks, 2);
        assert!(elapsed_row(late, 6_000_000, false).unwrap().is_none());
    }

    #[test]
    fn buff_pause_consumes_only_due_ticks_and_offline_duration_is_preserved() {
        let paused = elapsed_row(fixture(), 2_500_000, true).unwrap().unwrap();
        assert_eq!(paused.next_tick_us, 0);
        assert_eq!(paused.modifiers[0].remaining_ticks, 2);
        let offline = elapsed_row(paused, 900_000_000, true).unwrap().unwrap();
        assert_eq!(offline.modifiers[0].remaining_ticks, 2);
        assert_eq!(offline.modifiers[1].remaining_ticks, 4);
    }

    #[test]
    fn buff_saved_transition_rejects_invalid_points_and_clocks() {
        let mut invalid = fixture();
        invalid.modifiers[1].point = 255;
        assert!(elapsed_row(invalid, 2_000_000, false).is_err());
        assert!(elapsed_row(fixture(), -1, false).is_err());
        assert!(elapsed_row(fixture(), i64::MAX, false).is_err());
        let mut invalid = fixture();
        invalid.next_tick_us = -1;
        assert!(elapsed_row(invalid, 2_000_000, false).is_err());
    }
}
