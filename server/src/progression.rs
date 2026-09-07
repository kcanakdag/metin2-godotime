//! Source-backed class, level, EXP and stat progression.

use crate::accounts::{account_character, authenticated_controlled_account};
use crate::definitions;
use crate::inventory::{self, AutomaticGrantOutcome};
use crate::{controller, player};
use spacetimedb::rand::Rng;
use spacetimedb::{Identity, ReducerContext, Table};

#[spacetimedb::table(accessor = character_progression, public)]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CharacterProgression {
    #[primary_key]
    pub character_id: Identity,
    #[index(btree)]
    pub account: Identity,
    pub character_class: u8,
    pub level: u8,
    pub experience: u32,
    pub next_exp: u32,
    pub level_step: u8,
    pub unspent_stat_points: u16,
    pub strength: u8,
    pub vitality: u8,
    pub dexterity: u8,
    pub intelligence: u8,
    pub random_hp: u32,
    pub random_sp: u32,
    pub current_sp: u32,
    pub max_sp: u32,
    pub display_attack_min: u16,
    pub display_attack_max: u16,
    pub display_defense: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProgressionSnapshot {
    pub level: u8,
    pub experience: u32,
    pub level_step: u8,
    pub unspent_stat_points: u16,
    pub strength: u8,
    pub vitality: u8,
    pub dexterity: u8,
    pub intelligence: u8,
    pub random_hp: u32,
    pub random_sp: u32,
    pub health: u16,
    pub max_health: u16,
    pub current_sp: u32,
    pub max_sp: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LevelRoll {
    pub resulting_level: u8,
    pub hp: u32,
    pub sp: u32,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct AutomaticItemSummary {
    pub small_potions: u16,
    pub medium_potions: u16,
    pub stacked: u16,
    pub inserted: u16,
    pub dropped: u16,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProgressionOutcome {
    pub applied_experience: u64,
    pub before: ProgressionSnapshot,
    pub after: ProgressionSnapshot,
    pub level_rolls: Vec<LevelRoll>,
    pub automatic_items: AutomaticItemSummary,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct QuarterEffect {
    potion_vnum: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct PlannedProgression {
    row: CharacterProgression,
    level_rolls: Vec<LevelRoll>,
    quarter_effects: Vec<QuarterEffect>,
}

fn next_exp(level: u8) -> Result<u32, String> {
    if level == definitions::DEFAULT_LEVEL_CAP {
        return Ok(0);
    }
    definitions::EXPERIENCE_TABLE
        .get(usize::from(level))
        .copied()
        .filter(|value| *value > 0)
        .ok_or("Progression level is outside the selected EXP table.".into())
}

fn max_health(row: &CharacterProgression) -> Result<u16, String> {
    let class = crate::characters::class(row.character_class)?;
    let value = class
        .base_hp
        .checked_add(row.random_hp)
        .and_then(|value| value.checked_add(u32::from(row.vitality) * class.hp_per_vitality))
        .ok_or("Maximum HP overflowed.")?;
    u16::try_from(value).map_err(|_| "Maximum HP exceeds the public combat field.".into())
}

fn max_sp(row: &CharacterProgression) -> Result<u32, String> {
    let class = crate::characters::class(row.character_class)?;
    class
        .base_sp
        .checked_add(row.random_sp)
        .and_then(|value| {
            value.checked_add(u32::from(row.intelligence) * class.sp_per_intelligence)
        })
        .ok_or("Maximum SP overflowed.".into())
}

fn expected_level_step(row: &CharacterProgression) -> Result<u8, String> {
    if row.level == definitions::DEFAULT_LEVEL_CAP {
        return Ok(0);
    }
    let thresholds = definitions::QUARTER_THRESHOLDS
        .get(usize::from(row.level))
        .ok_or("Progression level has no quarter thresholds.")?;
    Ok(thresholds[..3]
        .iter()
        .filter(|threshold| row.experience >= **threshold)
        .count() as u8)
}

fn validate_row(row: &CharacterProgression) -> Result<(), String> {
    if row.level == 0 || row.level > definitions::DEFAULT_LEVEL_CAP {
        return Err("Progression level is outside the selected profile.".into());
    }
    if row.level == definitions::DEFAULT_LEVEL_CAP {
        if row.experience != 0 || row.next_exp != 0 || row.level_step != 0 {
            return Err("A capped progression row must have zero EXP and level step.".into());
        }
    } else {
        let expected_next = next_exp(row.level)?;
        if row.next_exp != expected_next || row.experience >= expected_next {
            return Err("Progression EXP state is inconsistent with its level.".into());
        }
        if row.level_step != expected_level_step(row)? {
            return Err("Progression level step is inconsistent with EXP.".into());
        }
    }
    if row.level_step > 3
        || row.strength > definitions::STAT_CAP
        || row.vitality > definitions::STAT_CAP
        || row.dexterity > definitions::STAT_CAP
        || row.intelligence > definitions::STAT_CAP
        || row.max_sp != max_sp(row)?
        || row.current_sp > row.max_sp
    {
        return Err("Progression stats or resources are inconsistent.".into());
    }
    Ok(())
}

pub fn create_character(
    ctx: &ReducerContext,
    character_id: Identity,
    account: Identity,
) -> Result<(), String> {
    if ctx
        .db
        .character_progression()
        .character_id()
        .find(character_id)
        .is_some()
    {
        return Err("Character progression already exists.".into());
    }
    let character = ctx
        .db
        .account_character()
        .character_id()
        .find(character_id)
        .ok_or("Character ownership is missing.")?;
    if character.account != account {
        return Err("Character progression ownership does not match.".into());
    }
    crate::characters::appearance(character.character_class, character.sex)?;
    let class = crate::characters::class(character.character_class)?;
    let mut row = CharacterProgression {
        character_id,
        account,
        character_class: character.character_class,
        level: 1,
        experience: 0,
        next_exp: next_exp(1)?,
        level_step: 0,
        unspent_stat_points: 0,
        strength: class.strength,
        vitality: class.vitality,
        dexterity: class.dexterity,
        intelligence: class.intelligence,
        random_hp: 0,
        random_sp: 0,
        current_sp: class.base_sp + u32::from(class.intelligence) * class.sp_per_intelligence,
        max_sp: class.base_sp + u32::from(class.intelligence) * class.sp_per_intelligence,
        display_attack_min: 0,
        display_attack_max: 0,
        display_defense: 0,
    };
    refresh_display_values(ctx, character_id, &mut row)?;
    validate_row(&row)?;
    ctx.db.character_progression().insert(row);
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character_id)
        .ok_or("Character player row is missing.")?;
    let initial_health = max_health(
        &ctx.db
            .character_progression()
            .character_id()
            .find(character_id)
            .expect("progression row was inserted"),
    )?;
    if player.health == player.max_health && player.health > 0 {
        player.health = initial_health;
    }
    player.max_health = initial_health;
    ctx.db.player().identity().update(player);
    Ok(())
}

pub fn rebuild_projection(ctx: &ReducerContext, character_id: Identity) -> Result<(), String> {
    let Some(mut row) = ctx
        .db
        .character_progression()
        .character_id()
        .find(character_id)
    else {
        return Ok(());
    };
    row.next_exp = next_exp(row.level)?;
    row.max_sp = max_sp(&row)?;
    row.current_sp = row.current_sp.min(row.max_sp);
    refresh_display_values(ctx, character_id, &mut row)?;
    validate_row(&row)?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character_id)
        .ok_or("Character player row is missing.")?;
    player.max_health = max_health(&row)?;
    player.health = player.health.min(player.max_health);
    ctx.db.character_progression().character_id().update(row);
    ctx.db.player().identity().update(player);
    Ok(())
}

pub fn selected_supported_progression(
    ctx: &ReducerContext,
) -> Result<(Identity, CharacterProgression), String> {
    let (state, connection_id) = authenticated_controlled_account(ctx)?;
    if !state.in_world || state.selected_character == Identity::ZERO {
        return Err("Enter the selected character first.".into());
    }
    let character = ctx
        .db
        .account_character()
        .character_id()
        .find(state.selected_character)
        .filter(|character| character.account == ctx.sender())
        .ok_or("That character does not belong to your account.")?;
    crate::characters::appearance(character.character_class, character.sex)?;
    ctx.db
        .controller()
        .identity()
        .find(state.selected_character)
        .filter(|control| control.connection_id == connection_id)
        .ok_or("The selected character is not controlled by this connection.")?;
    let row = ctx
        .db
        .character_progression()
        .character_id()
        .find(state.selected_character)
        .filter(|row| row.account == ctx.sender())
        .ok_or("Character progression is missing.")?;
    validate_row(&row)?;
    Ok((state.selected_character, row))
}

fn refresh_display_values(
    ctx: &ReducerContext,
    character_id: Identity,
    row: &mut CharacterProgression,
) -> Result<(), String> {
    let display = crate::physical_damage::display_values(ctx, character_id, row)?;
    row.display_attack_min = display.attack_min;
    row.display_attack_max = display.attack_max;
    row.display_defense = display.defense;
    Ok(())
}

pub fn rebuild_display_projection(
    ctx: &ReducerContext,
    character_id: Identity,
) -> Result<(), String> {
    let mut row = ctx
        .db
        .character_progression()
        .character_id()
        .find(character_id)
        .ok_or("Character progression is missing.")?;
    refresh_display_values(ctx, character_id, &mut row)?;
    validate_row(&row)?;
    ctx.db.character_progression().character_id().update(row);
    Ok(())
}

pub fn remaining_experience_capacity(row: &CharacterProgression) -> Result<u64, String> {
    validate_row(row)?;
    if row.level == definitions::DEFAULT_LEVEL_CAP {
        return Ok(0);
    }
    let mut result = u64::from(row.next_exp - row.experience);
    for level in row.level + 1..definitions::DEFAULT_LEVEL_CAP {
        result = result
            .checked_add(u64::from(next_exp(level)?))
            .ok_or("Progression capacity overflowed.")?;
    }
    Ok(result)
}

pub fn experience_to_reach_level(row: &CharacterProgression, target: u8) -> Result<u64, String> {
    validate_row(row)?;
    if target <= row.level || target > definitions::DEFAULT_LEVEL_CAP {
        return Err("Target level must be above the current level and at most 99.".into());
    }
    let mut result = u64::from(row.next_exp - row.experience);
    for level in row.level + 1..target {
        result = result
            .checked_add(u64::from(next_exp(level)?))
            .ok_or("Target level EXP overflowed.")?;
    }
    Ok(result)
}

fn plan_exact_experience(
    row: &CharacterProgression,
    amount: u64,
    alive: bool,
    mut roll: impl FnMut(u32, u32) -> u32,
) -> Result<PlannedProgression, String> {
    validate_row(row)?;
    if amount == 0 {
        return Err("Experience amount must be positive.".into());
    }
    if amount > remaining_experience_capacity(row)? {
        return Err("Experience amount exceeds the selected level cap.".into());
    }
    let mut row = row.clone();
    let mut remaining = amount;
    let mut level_rolls = Vec::new();
    let mut quarter_effects = Vec::new();
    while remaining > 0 {
        let needed = u64::from(row.next_exp - row.experience);
        let applied = remaining.min(needed);
        row.experience = row
            .experience
            .checked_add(u32::try_from(applied).map_err(|_| "EXP step exceeds u32.")?)
            .ok_or("Experience overflowed.")?;
        remaining -= applied;
        let thresholds = definitions::QUARTER_THRESHOLDS[usize::from(row.level)];
        while row.level_step < 4 && row.experience >= thresholds[usize::from(row.level_step)] {
            row.level_step += 1;
            if row.level_step < 4 {
                if row.level < definitions::STAT_POINT_LAST_LEVEL_EXCLUSIVE {
                    row.unspent_stat_points = row
                        .unspent_stat_points
                        .checked_add(1)
                        .ok_or("Unspent stat points overflowed.")?;
                }
            } else {
                let class = crate::characters::class(row.character_class)?;
                let hp = roll(class.hp_gain_min, class.hp_gain_max);
                let sp = roll(class.sp_gain_min, class.sp_gain_max);
                if !(class.hp_gain_min..=class.hp_gain_max).contains(&hp)
                    || !(class.sp_gain_min..=class.sp_gain_max).contains(&sp)
                {
                    return Err("Progression random growth is outside the selected ranges.".into());
                }
                row.random_hp = row
                    .random_hp
                    .checked_add(hp)
                    .ok_or("Random HP growth overflowed.")?;
                row.random_sp = row
                    .random_sp
                    .checked_add(sp)
                    .ok_or("Random SP growth overflowed.")?;
                row.level = row.level.checked_add(1).ok_or("Level overflowed.")?;
                row.experience = 0;
                row.level_step = 0;
                row.next_exp = next_exp(row.level)?;
                row.max_sp = max_sp(&row)?;
                level_rolls.push(LevelRoll {
                    resulting_level: row.level,
                    hp,
                    sp,
                });
            }
            let potion_vnum = if row.level <= definitions::SMALL_POTION_RESULTING_LEVEL_MAX {
                definitions::SMALL_POTION_VNUM
            } else {
                definitions::MEDIUM_POTION_VNUM
            };
            quarter_effects.push(QuarterEffect { potion_vnum });
            if alive {
                row.current_sp = row.max_sp;
            }
        }
    }
    validate_row(&row)?;
    Ok(PlannedProgression {
        row,
        level_rolls,
        quarter_effects,
    })
}

fn snapshot(row: &CharacterProgression, health: u16, max_health: u16) -> ProgressionSnapshot {
    ProgressionSnapshot {
        level: row.level,
        experience: row.experience,
        level_step: row.level_step,
        unspent_stat_points: row.unspent_stat_points,
        strength: row.strength,
        vitality: row.vitality,
        dexterity: row.dexterity,
        intelligence: row.intelligence,
        random_hp: row.random_hp,
        random_sp: row.random_sp,
        health,
        max_health,
        current_sp: row.current_sp,
        max_sp: row.max_sp,
    }
}

fn add_grant(
    summary: &mut AutomaticItemSummary,
    vnum: u32,
    grant: AutomaticGrantOutcome,
) -> Result<(), String> {
    let selected = if vnum == definitions::SMALL_POTION_VNUM {
        &mut summary.small_potions
    } else {
        &mut summary.medium_potions
    };
    let delivered = grant
        .stacked
        .checked_add(grant.inserted)
        .and_then(|value| value.checked_add(grant.dropped))
        .ok_or("Automatic item summary overflowed.")?;
    *selected = selected
        .checked_add(delivered)
        .ok_or("Automatic item summary overflowed.")?;
    summary.stacked = summary
        .stacked
        .checked_add(grant.stacked)
        .ok_or("Automatic item summary overflowed.")?;
    summary.inserted = summary
        .inserted
        .checked_add(grant.inserted)
        .ok_or("Automatic item summary overflowed.")?;
    summary.dropped = summary
        .dropped
        .checked_add(grant.dropped)
        .ok_or("Automatic item summary overflowed.")?;
    Ok(())
}

pub fn apply_exact_experience(
    ctx: &ReducerContext,
    character: Identity,
    amount: u64,
) -> Result<ProgressionOutcome, String> {
    let row = ctx
        .db
        .character_progression()
        .character_id()
        .find(character)
        .ok_or("Character progression is missing.")?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .ok_or("Character player row is missing.")?;
    let before = snapshot(&row, player.health, player.max_health);
    let mut planned =
        plan_exact_experience(&row, amount, player.health > 0, |minimum, maximum| {
            ctx.rng().gen_range(minimum..=maximum)
        })?;
    refresh_display_values(ctx, character, &mut planned.row)?;
    let new_max_health = max_health(&planned.row)?;
    let refill = !planned.quarter_effects.is_empty() && player.health > 0;
    player.max_health = new_max_health;
    if refill {
        player.health = new_max_health;
    } else {
        player.health = player.health.min(new_max_health);
    }
    ctx.db
        .character_progression()
        .character_id()
        .update(planned.row.clone());
    ctx.db.player().identity().update(player);
    let mut automatic_items = AutomaticItemSummary::default();
    for effect in &planned.quarter_effects {
        let grant = inventory::grant_automatic_progression(
            ctx,
            character,
            effect.potion_vnum,
            definitions::QUARTER_REWARD_COUNT,
        )?;
        add_grant(&mut automatic_items, effect.potion_vnum, grant)?;
    }
    let player = ctx
        .db
        .player()
        .identity()
        .find(character)
        .expect("player row was updated");
    Ok(ProgressionOutcome {
        applied_experience: amount,
        before,
        after: snapshot(&planned.row, player.health, player.max_health),
        level_rolls: planned.level_rolls,
        automatic_items,
    })
}

pub fn normalize_combat_experience(
    row: &CharacterProgression,
    monster_level: u8,
    distributed: u32,
) -> Result<u32, String> {
    validate_row(row)?;
    if distributed == 0 || row.level == definitions::DEFAULT_LEVEL_CAP {
        return Ok(0);
    }
    let delta = i16::from(monster_level) + 15 - i16::from(row.level);
    let index = usize::try_from(delta.clamp(0, 30)).expect("clamped nonnegative delta");
    let percent = definitions::NORMAL_LEVEL_DELTA_PERCENT[index];
    let adjusted = u64::from(distributed)
        .checked_mul(u64::from(percent))
        .ok_or("Combat EXP adjustment overflowed.")?
        / 100;
    let adjusted = adjusted
        .checked_mul(100)
        .ok_or("Mob EXP rate overflowed.")?
        / 100;
    Ok(u32::try_from(adjusted)
        .map_err(|_| "Combat EXP exceeds u32.")?
        .min(row.next_exp / 10))
}

pub fn apply_combat_experience(
    ctx: &ReducerContext,
    character: Identity,
    monster_level: u8,
    distributed: u32,
) -> Result<Option<ProgressionOutcome>, String> {
    let row = ctx
        .db
        .character_progression()
        .character_id()
        .find(character)
        .ok_or("Character progression is missing.")?;
    let amount = normalize_combat_experience(&row, monster_level, distributed)?;
    let amount = u64::from(amount).min(remaining_experience_capacity(&row)?);
    if amount == 0 {
        return Ok(None);
    }
    apply_exact_experience(ctx, character, amount).map(Some)
}

fn plan_stat_allocation(
    row: &CharacterProgression,
    stat_code: &str,
) -> Result<CharacterProgression, String> {
    validate_row(row)?;
    if row.unspent_stat_points == 0 {
        return Err("No unspent stat points are available.".into());
    }
    let mut row = row.clone();
    let stat = match stat_code {
        "st" => &mut row.strength,
        "ht" => &mut row.vitality,
        "dx" => &mut row.dexterity,
        "iq" => &mut row.intelligence,
        _ => return Err("Stat code must be one of st, ht, dx or iq.".into()),
    };
    if *stat >= definitions::STAT_CAP {
        return Err("That stat is already at its cap.".into());
    }
    *stat += 1;
    row.unspent_stat_points -= 1;
    row.max_sp = max_sp(&row)?;
    row.current_sp = row.current_sp.min(row.max_sp);
    validate_row(&row)?;
    Ok(row)
}

#[spacetimedb::reducer]
pub fn allocate_stat(
    ctx: &ReducerContext,
    character_id: Identity,
    stat_code: String,
) -> Result<(), String> {
    let (selected, row) = selected_supported_progression(ctx)?;
    if selected != character_id {
        return Err("Only the currently selected character can allocate stats.".into());
    }
    let mut row = plan_stat_allocation(&row, &stat_code)?;
    refresh_display_values(ctx, character_id, &mut row)?;
    let mut player = ctx
        .db
        .player()
        .identity()
        .find(character_id)
        .ok_or("Character player row is missing.")?;
    player.max_health = max_health(&row)?;
    player.health = player.health.min(player.max_health);
    ctx.db.character_progression().character_id().update(row);
    ctx.db.player().identity().update(player);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn initial() -> CharacterProgression {
        CharacterProgression {
            character_id: Identity::ZERO,
            account: Identity::ZERO,
            character_class: 0,
            level: 1,
            experience: 0,
            next_exp: 300,
            level_step: 0,
            unspent_stat_points: 0,
            strength: 6,
            vitality: 4,
            dexterity: 3,
            intelligence: 3,
            random_hp: 0,
            random_sp: 0,
            current_sp: 260,
            max_sp: 260,
            display_attack_min: 10,
            display_attack_max: 10,
            display_defense: 5,
        }
    }

    #[test]
    fn exact_level_one_quarters_and_level_up_apply_every_common_side_effect() {
        let planned = plan_exact_experience(&initial(), 300, true, |minimum, _| minimum).unwrap();
        assert_eq!(planned.row.level, 2);
        assert_eq!(planned.row.experience, 0);
        assert_eq!(planned.row.level_step, 0);
        assert_eq!(planned.row.unspent_stat_points, 3);
        assert_eq!(planned.row.random_hp, 36);
        assert_eq!(planned.row.random_sp, 18);
        assert_eq!(planned.row.current_sp, 278);
        assert_eq!(planned.quarter_effects.len(), 4);
        assert!(
            planned
                .quarter_effects
                .iter()
                .all(|effect| effect.potion_vnum == 27001)
        );
        assert_eq!(
            planned.level_rolls,
            [LevelRoll {
                resulting_level: 2,
                hp: 36,
                sp: 18
            }]
        );
    }

    #[test]
    fn each_positive_quarter_step_refills_sp_but_dead_guard_preserves_it() {
        let mut row = initial();
        row.current_sp = 7;
        let alive = plan_exact_experience(&row, 75, true, |minimum, _| minimum).unwrap();
        let dead = plan_exact_experience(&row, 75, false, |minimum, _| minimum).unwrap();
        assert_eq!(alive.row.current_sp, 260);
        assert_eq!(dead.row.current_sp, 7);
        assert_eq!(alive.row.unspent_stat_points, 1);
        assert_eq!(dead.row.unspent_stat_points, 1);
    }

    #[test]
    fn level_ten_step_four_selects_medium_potions_after_increment() {
        let mut row = initial();
        row.level = 10;
        row.next_exp = definitions::EXPERIENCE_TABLE[10];
        row.experience = definitions::QUARTER_THRESHOLDS[10][2];
        row.level_step = 3;
        let remaining = row.next_exp - row.experience;
        let planned =
            plan_exact_experience(&row, u64::from(remaining), true, |_, maximum| maximum).unwrap();
        assert_eq!(planned.row.level, 11);
        assert_eq!(planned.quarter_effects[0].potion_vnum, 27002);
    }

    #[test]
    fn combat_reward_uses_level_delta_before_ten_percent_cap() {
        let mut row = initial();
        assert_eq!(normalize_combat_experience(&row, 1, 15).unwrap(), 15);
        row.level = 2;
        row.next_exp = 800;
        assert_eq!(normalize_combat_experience(&row, 1, 15).unwrap(), 15);
        row.level = 3;
        row.next_exp = 1500;
        assert_eq!(normalize_combat_experience(&row, 1, 15).unwrap(), 14);
        assert_eq!(normalize_combat_experience(&initial(), 1, 300).unwrap(), 30);
    }

    #[test]
    fn float32_quarter_mismatch_is_preserved_at_high_level() {
        let level = 82usize;
        assert_ne!(
            definitions::QUARTER_THRESHOLDS[level][0],
            definitions::EXPERIENCE_TABLE[level] / 4
        );
    }

    #[test]
    fn exact_capacity_and_raise_target_include_partial_current_level() {
        let mut row = initial();
        row.experience = 75;
        row.level_step = 1;
        assert_eq!(experience_to_reach_level(&row, 2).unwrap(), 225);
        assert!(remaining_experience_capacity(&row).unwrap() > 225);
        assert!(plan_exact_experience(&row, 226, true, |minimum, _| minimum).is_ok());
        assert!(plan_exact_experience(&row, 0, true, |minimum, _| minimum).is_err());
    }

    #[test]
    fn combat_grant_clamps_to_last_level_capacity_and_cap_grants_zero() {
        let mut row = initial();
        row.level = definitions::DEFAULT_LEVEL_CAP - 1;
        row.next_exp = definitions::EXPERIENCE_TABLE[usize::from(row.level)];
        row.experience = row.next_exp - 1;
        row.level_step = 3;
        assert!(normalize_combat_experience(&row, row.level, 1_000_000).unwrap() > 1);
        assert_eq!(remaining_experience_capacity(&row).unwrap(), 1);

        row.level = definitions::DEFAULT_LEVEL_CAP;
        row.experience = 0;
        row.next_exp = 0;
        row.level_step = 0;
        assert_eq!(normalize_combat_experience(&row, 1, 15).unwrap(), 0);
        assert_eq!(remaining_experience_capacity(&row).unwrap(), 0);
    }

    #[test]
    fn stat_allocation_is_closed_capped_and_does_not_refill_resources() {
        let mut row = initial();
        row.unspent_stat_points = 1;
        row.current_sp = 7;
        let vitality = plan_stat_allocation(&row, "ht").unwrap();
        assert_eq!(vitality.vitality, 5);
        assert_eq!(max_health(&vitality).unwrap(), 800);
        assert_eq!(vitality.current_sp, 7);

        let intelligence = plan_stat_allocation(&row, "iq").unwrap();
        assert_eq!(intelligence.intelligence, 4);
        assert_eq!(intelligence.max_sp, 280);
        assert_eq!(intelligence.current_sp, 7);
        assert!(plan_stat_allocation(&row, "vit").is_err());

        row.strength = definitions::STAT_CAP;
        assert!(plan_stat_allocation(&row, "st").is_err());
        row.unspent_stat_points = 0;
        assert!(plan_stat_allocation(&row, "ht").is_err());
    }
}
