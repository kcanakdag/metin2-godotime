//! Reusable learned skills and exact-life, server-owned physical splash casts.
use crate::combat::monster;
use crate::progression::character_progression;
use crate::{accounts, combat, controller, definitions, inventory, now_us, player, progression};
use spacetimedb::{ConnectionId, Filter, Identity, ReducerContext, Table};

#[spacetimedb::table(accessor = character_skill, public)]
#[derive(Clone)]
pub struct CharacterSkill {
    #[primary_key]
    pub id: String,
    #[index(btree)]
    pub account: Identity,
    #[index(btree)]
    pub character_id: Identity,
    pub skill_vnum: u16,
    pub rank: u8,
    pub points_spent: u8,
    pub revision: u32,
    pub ready_at_us: i64,
}
#[spacetimedb::client_visibility_filter]
const OWN_SKILLS: Filter =
    Filter::Sql("SELECT * FROM character_skill WHERE character_skill.account = :sender");

#[derive(Clone, Debug, spacetimedb::SpacetimeType)]
pub struct SkillEventTiming {
    pub starts_at_us: i64,
    pub ends_at_us: i64,
}

#[spacetimedb::table(accessor = pending_skill)]
pub struct PendingSkill {
    #[primary_key]
    pub character_id: Identity,
    pub connection_id: ConnectionId,
    pub skill_vnum: u16,
    pub rank: u8,
    pub action_revision: u64,
    pub source_life: u32,
    pub events: Vec<SkillEventTiming>,
    pub per_life_limit: u8,
    pub attacker: crate::physical_damage::CapturedPlayerAttacker,
    pub vitality: u8,
    pub hit_lives: Vec<String>,
}

pub fn definition(vnum: u16) -> Result<&'static definitions::SkillDefinition, String> {
    definitions::SKILL_DEFINITIONS
        .iter()
        .find(|d| d.vnum == vnum)
        .ok_or("Unknown skill.".into())
}
pub fn is_skill_action(id: &str) -> bool {
    definitions::SKILL_ACTIONS
        .iter()
        .any(|(_, _, action)| action.id == id)
}
fn key(character: Identity, skill: u16) -> String {
    format!("{character}:{skill}")
}
fn revision(next: u32) -> Result<u32, String> {
    next.checked_add(1)
        .ok_or("Skill revision limit reached.".into())
}
fn owned_state(
    ctx: &ReducerContext,
    character: Identity,
    vnum: u16,
) -> Result<CharacterSkill, String> {
    let (_, progression) = progression::selected_supported_progression(ctx)?;
    Ok(ctx
        .db
        .character_skill()
        .id()
        .find(key(character, vnum))
        .unwrap_or(CharacterSkill {
            id: key(character, vnum),
            account: progression.account,
            character_id: character,
            skill_vnum: vnum,
            rank: 0,
            points_spent: 0,
            revision: 0,
            ready_at_us: 0,
        }))
}
fn store(ctx: &ReducerContext, row: CharacterSkill) {
    if ctx.db.character_skill().id().find(&row.id).is_some() {
        ctx.db.character_skill().id().update(row);
    } else {
        ctx.db.character_skill().insert(row);
    }
}
pub fn available_points(level: u8, spent: u16) -> u16 {
    u16::from(level.saturating_sub(4)).saturating_sub(spent)
}
fn check_learning(
    d: &definitions::SkillDefinition,
    class: u8,
    level: u8,
    rank: u8,
) -> Result<(), String> {
    if class != d.class_id {
        return Err("Your class cannot learn this skill.".into());
    }
    if level < d.minimum_level {
        return Err(format!("This skill requires level {}.", d.minimum_level));
    }
    if rank > d.maximum_rank {
        return Err("Skill rank exceeds the supported maximum.".into());
    }
    Ok(())
}
#[spacetimedb::reducer]
pub fn learn_skill(
    ctx: &ReducerContext,
    skill_vnum: u16,
    expected_revision: u32,
) -> Result<(), String> {
    let (character, p) = progression::selected_supported_progression(ctx)?;
    let d = definition(skill_vnum)?;
    let mut row = owned_state(ctx, character, skill_vnum)?;
    if row.revision != expected_revision {
        return Err("Skill changed; refresh before upgrading.".into());
    }
    let rank = row.rank.checked_add(1).ok_or("Skill rank overflow.")?;
    check_learning(d, p.character_class, p.level, rank)?;
    let spent: u16 = ctx
        .db
        .character_skill()
        .character_id()
        .filter(character)
        .map(|s| u16::from(s.points_spent))
        .sum();
    if available_points(p.level, spent) == 0 {
        return Err("No skill points available.".into());
    }
    row.rank = rank;
    row.points_spent = row
        .points_spent
        .checked_add(1)
        .ok_or("Skill points overflow.")?;
    row.revision = revision(row.revision)?;
    store(ctx, row);
    Ok(())
}
/// Called only after the audited admin reducer authorizes its account.
pub(crate) fn set_rank(ctx: &ReducerContext, skill_vnum: u16, rank: u8) -> Result<String, String> {
    let (character, p) = progression::selected_supported_progression(ctx)?;
    check_learning(definition(skill_vnum)?, p.character_class, p.level, rank)?;
    let mut row = owned_state(ctx, character, skill_vnum)?;
    let message = format!(
        "Skill {skill_vnum}: rank {} -> {rank}. Developer grant; invested points refunded.",
        row.rank
    );
    row.rank = rank;
    row.points_spent = 0;
    row.revision = revision(row.revision)?;
    // Rank changes deliberately preserve cooldown and any already captured cast.
    store(ctx, row);
    Ok(message)
}
pub fn sp_cost(d: &definitions::SkillDefinition, rank: u8) -> Result<u32, String> {
    let power = *definitions::SKILL_POWERS
        .get(usize::from(rank))
        .ok_or("Invalid skill rank.")?;
    Ok(u32::from(d.sp_base) + u32::from(d.sp_per_power) * u32::from(power) / 100)
}
pub fn damage(
    d: &definitions::SkillDefinition,
    rank: u8,
    atk: i32,
    stats: [u8; 3],
    defense: i32,
    resistance: u8,
) -> Result<u16, String> {
    let [strength, dexterity, vitality] = stats;
    let power = i64::from(
        *definitions::SKILL_POWERS
            .get(usize::from(rank))
            .ok_or("Invalid rank.")?,
    );
    if rank == 0 || atk < 0 || defense < 0 || resistance > 100 {
        return Err("Invalid skill damage inputs.".into());
    }
    let [constant, base, scaled, st, dx, ht] = d.damage_milli;
    let attack = i64::from(atk);
    let amount = ((constant + base * attack) * 100
        + (scaled * attack
            + st * i64::from(strength)
            + dx * i64::from(dexterity)
            + ht * i64::from(vitality))
            * power)
        / 100_000;
    let final_damage = (amount * i64::from(100 - resistance) / 100 - i64::from(defense)).max(1);
    u16::try_from(final_damage).map_err(|_| "Skill damage exceeds supported range.".into())
}
#[spacetimedb::reducer]
pub fn cast_skill(
    ctx: &ReducerContext,
    skill_vnum: u16,
    expected_revision: u32,
) -> Result<(), String> {
    let mut control = crate::active_controller(ctx)?;
    let (character, mut p) = progression::selected_supported_progression(ctx)?;
    let d = definition(skill_vnum)?;
    let mut state = owned_state(ctx, character, skill_vnum)?;
    check_learning(d, p.character_class, p.level, state.rank)?;
    if state.rank == 0 {
        return Err("Learn this skill first.".into());
    }
    if state.revision != expected_revision {
        return Err("Skill changed; refresh before casting.".into());
    }
    let now = now_us(ctx);
    if now < state.ready_at_us {
        return Err("Skill is cooling down.".into());
    }
    if now < control.attack_until_us || now < control.next_attack_us {
        return Err("Finish the current attack first.".into());
    }
    let player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Enter the world first.")?;
    if player.health == 0 {
        return Err("You cannot use a skill while dead.".into());
    }
    let weapon = crate::item_catalog::definition(inventory::equipped_weapon(ctx, character))?;
    if !weapon
        .weapon
        .is_some_and(|w| matches!(w.class, definitions::PhysicalWeaponClass::Sword))
    {
        return Err("This skill requires an equipped sword.".into());
    }
    let appearance = crate::characters::owned_appearance(ctx, character)?;
    let action = &definitions::SKILL_ACTIONS
        .iter()
        .find(|(id, actor, _)| *id == skill_vnum && *actor == appearance.actor_id)
        .ok_or("Skill animation is unavailable.")?
        .2;
    let windows = definitions::SKILL_EVENT_WINDOWS
        .iter()
        .find(|(id, actor, _)| *id == skill_vnum && *actor == appearance.actor_id)
        .ok_or("Skill event definitions are unavailable.")?
        .2;
    let events = crate::skill_hits::capture_events(windows, now)?;
    let cost = sp_cost(d, state.rank)?;
    if p.current_sp < cost {
        return Err("Not enough SP.".into());
    }
    let attacker = crate::physical_damage::capture_player(ctx, character, true)?;
    state.ready_at_us = now
        .checked_add(d.cooldown_us)
        .ok_or("Skill clock overflow.")?;
    state.revision = revision(state.revision)?;
    crate::root_motion::advance_for_replacement(ctx, &mut control, now)?;
    crate::combo::clear_chain(&mut control);
    crate::combat::cancel_player_attack(&mut control);
    crate::npcs::clear(ctx, character);
    combat::start_player_action(
        ctx,
        &mut control,
        combat::PlayerAttackPlan {
            definition: action,
            target_id: 0,
            target_generation: 0,
            heading: None,
            can_select_target: false,
        },
        now,
    )?;
    p.current_sp -= cost;
    ctx.db
        .character_progression()
        .character_id()
        .update(p.clone());
    clear(ctx, character);
    ctx.db.pending_skill().insert(PendingSkill {
        character_id: character,
        connection_id: control.connection_id,
        skill_vnum,
        rank: state.rank,
        action_revision: control.action_revision,
        source_life: player.life_sequence,
        events: events
            .into_iter()
            .map(|[starts_at_us, ends_at_us]| SkillEventTiming {
                starts_at_us,
                ends_at_us,
            })
            .collect(),
        per_life_limit: d.hits_per_life,
        attacker,
        vitality: p.vitality,
        hit_lives: Vec::new(),
    });
    ctx.db.controller().identity().update(control);
    store(ctx, state);
    Ok(())
}
pub fn clear(ctx: &ReducerContext, character: Identity) {
    ctx.db.pending_skill().character_id().delete(character);
}

pub fn simulate(ctx: &ReducerContext, now: i64) -> Result<(), String> {
    let casts: Vec<_> = ctx.db.pending_skill().iter().collect();
    for mut cast in casts {
        let control = ctx.db.controller().identity().find(cast.character_id);
        let owner = ctx.db.player().identity().find(cast.character_id);
        let valid = control.as_ref().zip(owner.as_ref()).is_some_and(|(c, p)| {
            c.connection_id == cast.connection_id
                && c.action_revision == cast.action_revision
                && p.online
                && p.health > 0
                && p.life_sequence == cast.source_life
                && accounts::controller_has_active_lease(ctx, c)
        });
        let windows: Vec<_> = cast
            .events
            .iter()
            .map(|event| [event.starts_at_us, event.ends_at_us])
            .collect();
        if !valid || windows.iter().all(|window| now > window[1]) {
            clear(ctx, cast.character_id);
            continue;
        }
        let active = crate::skill_hits::active_events(&windows, now)?;
        if active == 0 {
            continue;
        }
        let owner = owner.expect("validated owner");
        let d = definition(cast.skill_vnum)?;
        let bounds = crate::collision_bounds(ctx);
        for event_index in 0..windows.len() {
            if active & (1 << event_index) == 0 {
                continue;
            }
            let mut victims: Vec<_> = ctx
                .db
                .monster()
                .iter()
                .filter(|m| {
                    m.health > 0
                        && m.x.is_finite()
                        && m.z.is_finite()
                        && (m.x - owner.x).hypot(m.z - owner.z) <= d.radius_m
                        && crate::content::clear_path(owner.x, owner.z, m.x, m.z, &bounds)
                })
                .collect();
            victims.sort_by_key(|m| m.id);
            for mut victim in victims {
                if cast.hit_lives.len() >= usize::from(d.max_targets) {
                    break;
                }
                if !crate::skill_hits::admits(
                    &cast.hit_lives,
                    victim.id,
                    victim.life_sequence,
                    event_index as u8,
                    cast.per_life_limit,
                    u16::from(d.max_targets),
                )? {
                    continue;
                }
                let amount = crate::physical_damage::roll_skill_hit(
                    ctx,
                    d,
                    cast.rank,
                    cast.attacker,
                    cast.vitality,
                    &victim,
                )?;
                cast.hit_lives.push(crate::skill_hits::receipt(
                    victim.id,
                    victim.life_sequence,
                    event_index as u8,
                ));
                combat::record_damage(
                    ctx,
                    victim.id,
                    victim.life_sequence,
                    cast.character_id,
                    cast.connection_id,
                    u32::from(amount),
                    crate::mob_threat::DamageKind::MeleeSkill,
                )?;
                if combat::apply_damage(&mut victim.health, amount) {
                    combat::kill_monster(ctx, &mut victim, cast.character_id);
                }
                ctx.db.monster().id().update(victim);
            }
        }
        ctx.db.pending_skill().character_id().update(cast);
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn event_list_survives_bsatn_with_stable_event_order() {
        let captured =
            crate::skill_hits::capture_events(&[[10, 20], [30, 40], [50, 60]], 1_000).unwrap();
        let events: Vec<_> = captured
            .iter()
            .map(|&[starts_at_us, ends_at_us]| SkillEventTiming {
                starts_at_us,
                ends_at_us,
            })
            .collect();
        let bytes = spacetimedb::sats::bsatn::to_vec(&events).unwrap();
        let restored: Vec<SkillEventTiming> = spacetimedb::sats::bsatn::from_slice(&bytes).unwrap();
        let windows: Vec<_> = restored
            .iter()
            .map(|event| [event.starts_at_us, event.ends_at_us])
            .collect();
        assert_eq!(windows, captured);
        assert_eq!(
            crate::skill_hits::active_events(&windows, 1_035).unwrap(),
            2
        );
        assert_eq!(
            crate::skill_hits::active_events(&windows, 1_045).unwrap(),
            0
        );
        assert_eq!(
            crate::skill_hits::active_events(&windows, 1_055).unwrap(),
            4
        );
    }

    #[test]
    fn progression_budget_and_rank_boundaries() {
        let d = definition(2).unwrap();
        assert_eq!(d.hits_per_life, 1);
        assert_eq!(available_points(4, 0), 0);
        assert_eq!(available_points(5, 0), 1);
        assert_eq!(available_points(8, 3), 1);
        assert_eq!(available_points(5, 20), 0);
        assert!(check_learning(d, 1, 5, 1).is_err());
        assert!(check_learning(d, 0, 4, 1).is_err());
        assert!(check_learning(d, 0, 5, 21).is_err());
        assert!(check_learning(d, 0, 5, 1).is_ok());
        assert!(revision(u32::MAX).is_err());
    }
    #[test]
    fn original_international_costs_and_damage_order() {
        let d = definition(2).unwrap();
        assert_eq!(sp_cost(d, 1).unwrap(), 56);
        assert_eq!(sp_cost(d, 20).unwrap(), 115);
        // 3*30 + (.8*30 + 5*6 + 3*3 + 4)*.05 = 93.35; truncate, resist, defend.
        assert_eq!(damage(d, 1, 30, [6, 3, 4], 5, 0).unwrap(), 88);
        assert_eq!(damage(d, 1, 30, [6, 3, 4], 5, 20).unwrap(), 69);
        assert!(damage(d, 0, 30, [6, 3, 4], 5, 0).is_err());
    }
}
