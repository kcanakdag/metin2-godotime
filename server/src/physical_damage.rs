//! Source-ordered physical damage and runtime capture for the selected physical slice.
//!
//! The calculation core accepts explicit rolls. Runtime adapters below it consume only generated
//! physical definitions plus canonical progression and inventory. No client projection or legacy
//! fixed-damage constant is an authority input.

use crate::combat::Monster;
use crate::progression::character_progression;
use crate::{definitions, inventory, progression};
use spacetimedb::rand::Rng;
use spacetimedb::{Identity, ReducerContext};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CombatantKind {
    Player,
    Npc,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PhysicalWeaponClass {
    Unarmed,
    Sword,
    Fan,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PhysicalPowerSource {
    pub class: PhysicalWeaponClass,
    pub power_min: u16,
    pub power_max: u16,
    pub refine_attack: u16,
}

#[cfg(test)]
const UNARMED_POWER: PhysicalPowerSource = PhysicalPowerSource {
    class: PhysicalWeaponClass::Unarmed,
    power_min: 0,
    power_max: 0,
    refine_attack: 0,
};

#[cfg(test)]
const SWORD_10_POWER: PhysicalPowerSource = PhysicalPowerSource {
    class: PhysicalWeaponClass::Sword,
    power_min: 13,
    power_max: 15,
    refine_attack: 0,
};

#[cfg(test)]
const WILD_DOG_101_POWER: PhysicalPowerSource = PhysicalPowerSource {
    class: PhysicalWeaponClass::Unarmed,
    power_min: 20,
    power_max: 24,
    refine_attack: 0,
};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PhysicalAttackerSnapshot {
    pub kind: CombatantKind,
    pub level: u8,
    pub strength: u8,
    pub dexterity: u8,
    pub stat_attack: i32,
    pub power: PhysicalPowerSource,
    pub attack_grade_bonus: i16,
    pub party_attack_bonus: i16,
    pub attack_percent: i16,
    pub melee_magic_attack_percent: i16,
    pub npc_damage_multiplier: f32,
    pub final_multiplier: f32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PhysicalVictimSnapshot {
    pub kind: CombatantKind,
    pub level: u8,
    pub vitality: u8,
    pub dexterity: u8,
    pub proto_or_armor_defense: u16,
    pub defense_grade_bonus: i16,
    pub party_defender_bonus: i16,
    pub defense_percent: i16,
    pub npc_attacker_marriage_defense_bonus: i16,
    pub sword_resistance_percent: u8,
    pub fan_resistance_percent: u8,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DamageDiagnostics {
    pub attacker_rating_source: i32,
    pub victim_rating_source: i32,
    pub rating_bits: u32,
    pub attack_grade: i32,
    pub defense_grade: i32,
    pub applied_defense: i32,
    pub attack_before_npc_multiplier: i32,
    pub attack_after_npc_multiplier: i32,
    pub pre_floor_damage: i32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DamageBeforeFloor {
    Retained(u16),
    NeedsLowFloor,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PreFloorCalculation {
    pub outcome: DamageBeforeFloor,
    pub diagnostics: DamageDiagnostics,
    weapon_resistance_percent: u8,
    final_multiplier_bits: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FinalDamage {
    pub damage: u16,
    pub diagnostics: DamageDiagnostics,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DisplayBattleValues {
    pub attack_min: u16,
    pub attack_max: u16,
    pub defense: u16,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WarriorDisplaySnapshot {
    pub level: u8,
    pub strength: u8,
    pub vitality: u8,
    pub dexterity: u8,
    pub power: PhysicalPowerSource,
    pub armor_defense: u16,
    pub defense_grade_bonus: i16,
    pub party_defender_bonus: i16,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct SelectedZeroStages {
    pub calc_att_bonus_percent: i16,
    pub block_percent: i16,
    pub normal_affect_damage: i16,
    pub reflect_percent: i16,
    pub critical_percent: i16,
    pub resist_critical_percent: i16,
    pub penetrate_percent: i16,
    pub resist_penetrate_percent: i16,
    pub hp_steal_percent: i16,
    pub sp_steal_percent: i16,
    pub gold_steal_percent: i16,
    pub hit_hp_recovery: i16,
    pub hit_sp_recovery: i16,
    pub mana_burn_percent: i16,
    pub normal_hit_damage_bonus_percent: i16,
    pub normal_hit_defense_bonus_percent: i16,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PhysicalDamageError {
    InvalidLevel,
    InvalidStat,
    InvalidPowerRange,
    InvalidPowerRoll,
    InvalidLowFloorRoll,
    UnexpectedLowFloorRoll,
    InvalidPercent,
    InvalidMultiplier,
    InvalidResistance,
    UnsupportedSelectedPolicy,
    ArithmeticOverflow,
    ResultOutOfRange,
}

const MAX_LEVEL: u8 = 99;
const MAX_STAT: u8 = 90;
const MAX_POWER: u16 = 10_000;
const MAX_DEFENSE: u16 = 10_000;
const MAX_BONUS: i16 = 10_000;
const MIN_PERCENT: i16 = -100;
const MAX_PERCENT: i16 = 10_000;
const MAX_MULTIPLIER: f32 = 100.0;

#[cfg(test)]
fn warrior(
    level: u8,
    strength: u8,
    dexterity: u8,
    power: PhysicalPowerSource,
) -> PhysicalAttackerSnapshot {
    PhysicalAttackerSnapshot {
        kind: CombatantKind::Player,
        level,
        strength,
        dexterity,
        stat_attack: 2 * i32::from(strength),
        power,
        attack_grade_bonus: 0,
        party_attack_bonus: 0,
        attack_percent: 0,
        melee_magic_attack_percent: 0,
        npc_damage_multiplier: 1.0,
        final_multiplier: 1.0,
    }
}

#[cfg(test)]
fn wild_dog_attacker() -> PhysicalAttackerSnapshot {
    PhysicalAttackerSnapshot {
        kind: CombatantKind::Npc,
        level: 1,
        strength: 3,
        dexterity: 6,
        stat_attack: 6,
        power: WILD_DOG_101_POWER,
        attack_grade_bonus: 0,
        party_attack_bonus: 0,
        attack_percent: 0,
        melee_magic_attack_percent: 0,
        npc_damage_multiplier: 1.0,
        final_multiplier: 1.0,
    }
}

#[cfg(test)]
fn warrior_victim(level: u8, vitality: u8, dexterity: u8) -> PhysicalVictimSnapshot {
    PhysicalVictimSnapshot {
        kind: CombatantKind::Player,
        level,
        vitality,
        dexterity,
        proto_or_armor_defense: 0,
        defense_grade_bonus: 0,
        party_defender_bonus: 0,
        defense_percent: 0,
        npc_attacker_marriage_defense_bonus: 0,
        sword_resistance_percent: 0,
        fan_resistance_percent: 0,
    }
}

#[cfg(test)]
fn wild_dog_victim() -> PhysicalVictimSnapshot {
    PhysicalVictimSnapshot {
        kind: CombatantKind::Npc,
        level: 1,
        vitality: 5,
        dexterity: 6,
        proto_or_armor_defense: 4,
        defense_grade_bonus: 0,
        party_defender_bonus: 0,
        defense_percent: 0,
        npc_attacker_marriage_defense_bonus: 0,
        sword_resistance_percent: 0,
        fan_resistance_percent: 0,
    }
}

/// Enforce the deliberately narrow policy values before using this arithmetic in gameplay.
///
/// The calculation helpers admit bounded synthetic modifiers so ordering can be unit-tested.
/// The selected integration remains limited to the classic classes, selected weapons/unarmed, and Wild Dog 101
/// rows, with excluded bonus stages at zero, bounded authored resistances, and unit multipliers.
pub fn validate_selected_policy(
    attacker: PhysicalAttackerSnapshot,
    victim: PhysicalVictimSnapshot,
    zero_stages: SelectedZeroStages,
) -> Result<(), PhysicalDamageError> {
    validate_level_and_stats(attacker.level, attacker.strength, attacker.dexterity)?;
    server_defense_grade(victim)?;
    let direction_matches = matches!(
        (attacker.kind, victim.kind),
        (CombatantKind::Player, CombatantKind::Npc) | (CombatantKind::Npc, CombatantKind::Player)
    );
    if !direction_matches
        || attacker.attack_grade_bonus != 0
        || attacker.party_attack_bonus != 0
        || attacker.attack_percent != 0
        || attacker.melee_magic_attack_percent != 0
        || attacker.npc_damage_multiplier.to_bits() != 1.0_f32.to_bits()
        || attacker.final_multiplier.to_bits() != 1.0_f32.to_bits()
        || victim.defense_grade_bonus != 0
        || victim.party_defender_bonus != 0
        || victim.defense_percent != 0
        || victim.npc_attacker_marriage_defense_bonus != 0
        || zero_stages != SelectedZeroStages::default()
    {
        return Err(PhysicalDamageError::UnsupportedSelectedPolicy);
    }
    Ok(())
}

fn checked_add(left: i32, right: i32) -> Result<i32, PhysicalDamageError> {
    left.checked_add(right)
        .ok_or(PhysicalDamageError::ArithmeticOverflow)
}

fn checked_mul(left: i32, right: i32) -> Result<i32, PhysicalDamageError> {
    left.checked_mul(right)
        .ok_or(PhysicalDamageError::ArithmeticOverflow)
}

fn validate_level_and_stats(
    level: u8,
    strength: u8,
    dexterity: u8,
) -> Result<(), PhysicalDamageError> {
    if level == 0 || level > MAX_LEVEL {
        return Err(PhysicalDamageError::InvalidLevel);
    }
    if strength > MAX_STAT || dexterity > MAX_STAT {
        return Err(PhysicalDamageError::InvalidStat);
    }
    Ok(())
}

fn validate_bonus(value: i16) -> Result<(), PhysicalDamageError> {
    if value.unsigned_abs() > MAX_BONUS as u16 {
        return Err(PhysicalDamageError::ArithmeticOverflow);
    }
    Ok(())
}

fn validate_percent(value: i16) -> Result<(), PhysicalDamageError> {
    if !(MIN_PERCENT..=MAX_PERCENT).contains(&value) {
        return Err(PhysicalDamageError::InvalidPercent);
    }
    Ok(())
}

fn validate_multiplier(value: f32) -> Result<(), PhysicalDamageError> {
    if !value.is_finite() || value < 0.0 || value > MAX_MULTIPLIER {
        return Err(PhysicalDamageError::InvalidMultiplier);
    }
    Ok(())
}

fn trunc_f32_i32(value: f32) -> Result<i32, PhysicalDamageError> {
    // i32::MAX rounds up to 2^31 in binary32. Keep that upper edge exclusive so
    // Rust's saturating float-to-int cast can never disguise an overflow.
    if !value.is_finite() || value < -2_147_483_648.0_f32 || value >= 2_147_483_648.0_f32 {
        return Err(PhysicalDamageError::ArithmeticOverflow);
    }
    Ok(value.trunc() as i32)
}

fn percent_stage(value: i32, first: i16, second: i16) -> Result<i32, PhysicalDamageError> {
    validate_percent(first)?;
    validate_percent(second)?;
    let percent = checked_add(100, checked_add(i32::from(first), i32::from(second))?)?;
    Ok(checked_mul(value, percent)? / 100)
}

pub fn rating_source(dexterity: u8, level_term: u8) -> Result<i32, PhysicalDamageError> {
    if dexterity > MAX_STAT {
        return Err(PhysicalDamageError::InvalidStat);
    }
    if level_term == 0 || level_term > MAX_LEVEL {
        return Err(PhysicalDamageError::InvalidLevel);
    }
    let numerator = checked_add(
        checked_mul(i32::from(dexterity), 4)?,
        checked_mul(i32::from(level_term), 2)?,
    )?;
    Ok((numerator / 6).min(90))
}

pub fn attack_rating(
    attacker_dexterity: u8,
    attacker_level: u8,
    victim_dexterity: u8,
) -> Result<(f32, i32, i32), PhysicalDamageError> {
    let attacker_source = rating_source(attacker_dexterity, attacker_level)?;
    // The pinned source assigns victim_lv from the attacker. Preserve that exact quirk.
    let victim_source = rating_source(victim_dexterity, attacker_level)?;
    let attack_rating = (attacker_source as f32 + 210.0_f32) / 300.0_f32;
    let evasion_rating =
        ((victim_source * 2 + 5) as f32 / (victim_source + 95) as f32) * 3.0_f32 / 10.0_f32;
    Ok((
        attack_rating - evasion_rating,
        attacker_source,
        victim_source,
    ))
}

fn attack_grade(snapshot: PhysicalAttackerSnapshot) -> Result<i32, PhysicalDamageError> {
    validate_level_and_stats(snapshot.level, snapshot.strength, snapshot.dexterity)?;
    validate_bonus(snapshot.attack_grade_bonus)?;
    if !(0..=2 * i32::from(MAX_STAT)).contains(&snapshot.stat_attack) {
        return Err(PhysicalDamageError::InvalidStat);
    }
    let base = checked_add(
        checked_mul(i32::from(snapshot.level), 2)?,
        snapshot.stat_attack,
    )?;
    checked_add(base, i32::from(snapshot.attack_grade_bonus))
}

pub fn server_defense_grade(snapshot: PhysicalVictimSnapshot) -> Result<i32, PhysicalDamageError> {
    if snapshot.level == 0 || snapshot.level > MAX_LEVEL {
        return Err(PhysicalDamageError::InvalidLevel);
    }
    if snapshot.vitality > MAX_STAT || snapshot.dexterity > MAX_STAT {
        return Err(PhysicalDamageError::InvalidStat);
    }
    if snapshot.proto_or_armor_defense > MAX_DEFENSE {
        return Err(PhysicalDamageError::ArithmeticOverflow);
    }
    validate_bonus(snapshot.defense_grade_bonus)?;
    validate_bonus(snapshot.party_defender_bonus)?;
    validate_bonus(snapshot.npc_attacker_marriage_defense_bonus)?;
    validate_percent(snapshot.defense_percent)?;
    if snapshot.sword_resistance_percent > 100 || snapshot.fan_resistance_percent > 100 {
        return Err(PhysicalDamageError::InvalidResistance);
    }
    let vitality = match snapshot.kind {
        CombatantKind::Player => checked_mul(i32::from(snapshot.vitality), 4)? / 5,
        CombatantKind::Npc => i32::from(snapshot.vitality),
    };
    let grade = checked_add(
        checked_add(i32::from(snapshot.level), vitality)?,
        i32::from(snapshot.proto_or_armor_defense),
    )?;
    checked_add(
        checked_add(grade, i32::from(snapshot.defense_grade_bonus))?,
        i32::from(snapshot.party_defender_bonus),
    )
}

pub fn npc_multiply_then_defend(
    attack: i32,
    npc_multiplier: f32,
    defense: i32,
) -> Result<(i32, i32), PhysicalDamageError> {
    validate_multiplier(npc_multiplier)?;
    let multiplied = trunc_f32_i32(attack as f32 * npc_multiplier)?;
    let damage = multiplied
        .checked_sub(defense)
        .ok_or(PhysicalDamageError::ArithmeticOverflow)?
        .max(0);
    Ok((multiplied, damage))
}

pub fn calculate_pre_floor(
    attacker: PhysicalAttackerSnapshot,
    victim: PhysicalVictimSnapshot,
    base_power_roll: u16,
) -> Result<PreFloorCalculation, PhysicalDamageError> {
    validate_level_and_stats(attacker.level, attacker.strength, attacker.dexterity)?;
    if attacker.power.power_min > attacker.power.power_max
        || attacker.power.power_max > MAX_POWER
        || attacker.power.refine_attack > MAX_POWER
    {
        return Err(PhysicalDamageError::InvalidPowerRange);
    }
    if !(attacker.power.power_min..=attacker.power.power_max).contains(&base_power_roll) {
        return Err(PhysicalDamageError::InvalidPowerRoll);
    }
    for bonus in [attacker.attack_grade_bonus, attacker.party_attack_bonus] {
        validate_bonus(bonus)?;
    }
    validate_multiplier(attacker.npc_damage_multiplier)?;
    validate_multiplier(attacker.final_multiplier)?;
    let defense_grade = server_defense_grade(victim)?;
    let (rating, attacker_source, victim_source) =
        attack_rating(attacker.dexterity, attacker.level, victim.dexterity)?;
    let grade = attack_grade(attacker)?;
    let doubled_level = checked_mul(i32::from(attacker.level), 2)?;
    let doubled_power = checked_mul(i32::from(base_power_roll), 2)?;
    let before_rating = checked_add(grade, doubled_power)?
        .checked_sub(doubled_level)
        .ok_or(PhysicalDamageError::ArithmeticOverflow)?;
    let rated = trunc_f32_i32(before_rating as f32 * rating)?;
    let mut attack = checked_add(rated, doubled_level)?;
    attack = checked_add(
        attack,
        checked_mul(i32::from(attacker.power.refine_attack), 2)?,
    )?;
    attack = checked_add(attack, i32::from(attacker.party_attack_bonus))?;
    attack = percent_stage(
        attack,
        attacker.attack_percent,
        attacker.melee_magic_attack_percent,
    )?;
    let defense = percent_stage(defense_grade, victim.defense_percent, 0)?;
    let defense = if attacker.kind == CombatantKind::Npc {
        checked_add(
            defense,
            i32::from(victim.npc_attacker_marriage_defense_bonus),
        )?
    } else {
        defense
    };
    let attack_before_npc_multiplier = attack;
    let (attack_after_npc_multiplier, pre_floor) = if attacker.kind == CombatantKind::Npc {
        npc_multiply_then_defend(attack, attacker.npc_damage_multiplier, defense)?
    } else {
        (
            attack,
            attack
                .checked_sub(defense)
                .ok_or(PhysicalDamageError::ArithmeticOverflow)?
                .max(0),
        )
    };
    let diagnostics = DamageDiagnostics {
        attacker_rating_source: attacker_source,
        victim_rating_source: victim_source,
        rating_bits: rating.to_bits(),
        attack_grade: grade,
        defense_grade,
        applied_defense: defense,
        attack_before_npc_multiplier,
        attack_after_npc_multiplier,
        pre_floor_damage: pre_floor,
    };
    let outcome = if pre_floor < 3 {
        DamageBeforeFloor::NeedsLowFloor
    } else {
        DamageBeforeFloor::Retained(
            u16::try_from(pre_floor).map_err(|_| PhysicalDamageError::ResultOutOfRange)?,
        )
    };
    Ok(PreFloorCalculation {
        outcome,
        diagnostics,
        weapon_resistance_percent: match attacker.power.class {
            PhysicalWeaponClass::Unarmed => 0,
            PhysicalWeaponClass::Sword => victim.sword_resistance_percent,
            PhysicalWeaponClass::Fan => victim.fan_resistance_percent,
        },
        final_multiplier_bits: attacker.final_multiplier.to_bits(),
    })
}

pub fn finish_damage(
    calculation: PreFloorCalculation,
    low_floor_roll: Option<u8>,
) -> Result<FinalDamage, PhysicalDamageError> {
    let final_multiplier = f32::from_bits(calculation.final_multiplier_bits);
    validate_multiplier(final_multiplier)?;
    let damage = match (calculation.outcome, low_floor_roll) {
        (DamageBeforeFloor::NeedsLowFloor, Some(roll @ 1..=5)) => i32::from(roll),
        (DamageBeforeFloor::NeedsLowFloor, _) => {
            return Err(PhysicalDamageError::InvalidLowFloorRoll);
        }
        (DamageBeforeFloor::Retained(damage), None) => i32::from(damage),
        (DamageBeforeFloor::Retained(_), Some(_)) => {
            return Err(PhysicalDamageError::UnexpectedLowFloorRoll);
        }
    };
    if calculation.weapon_resistance_percent > 100 {
        return Err(PhysicalDamageError::InvalidResistance);
    }
    let resisted = checked_mul(
        damage,
        i32::from(100_u8 - calculation.weapon_resistance_percent),
    )? / 100;
    let rounded = trunc_f32_i32(final_multiplier * resisted as f32 + 0.5_f32)?;
    Ok(FinalDamage {
        damage: u16::try_from(rounded).map_err(|_| PhysicalDamageError::ResultOutOfRange)?,
        diagnostics: calculation.diagnostics,
    })
}

#[cfg(test)]
fn calculate_damage(
    attacker: PhysicalAttackerSnapshot,
    victim: PhysicalVictimSnapshot,
    base_power_roll: u16,
    low_floor_roll: Option<u8>,
) -> Result<FinalDamage, PhysicalDamageError> {
    let calculation = calculate_pre_floor(attacker, victim, base_power_roll)?;
    finish_damage(calculation, low_floor_roll)
}

#[cfg(test)]
fn calculate_selected_damage(
    attacker: PhysicalAttackerSnapshot,
    victim: PhysicalVictimSnapshot,
    zero_stages: SelectedZeroStages,
    base_power_roll: u16,
    low_floor_roll: Option<u8>,
) -> Result<FinalDamage, PhysicalDamageError> {
    validate_selected_policy(attacker, victim, zero_stages)?;
    calculate_damage(attacker, victim, base_power_roll, low_floor_roll)
}

#[cfg(test)]
pub fn warrior_display_values(
    snapshot: WarriorDisplaySnapshot,
) -> Result<DisplayBattleValues, PhysicalDamageError> {
    class_display_values(snapshot, 2 * i32::from(snapshot.strength))
}

fn class_display_values(
    snapshot: WarriorDisplaySnapshot,
    stat_attack: i32,
) -> Result<DisplayBattleValues, PhysicalDamageError> {
    validate_level_and_stats(snapshot.level, snapshot.strength, snapshot.dexterity)?;
    if snapshot.vitality > MAX_STAT || snapshot.armor_defense > MAX_DEFENSE {
        return Err(PhysicalDamageError::InvalidStat);
    }
    validate_bonus(snapshot.defense_grade_bonus)?;
    validate_bonus(snapshot.party_defender_bonus)?;
    if snapshot.power.power_min > snapshot.power.power_max
        || snapshot.power.power_max > MAX_POWER
        || snapshot.power.refine_attack > MAX_POWER
    {
        return Err(PhysicalDamageError::InvalidPowerRange);
    }
    let hit_rate_percent = checked_mul(
        checked_add(rating_source(snapshot.dexterity, snapshot.level)?, 210)?,
        100,
    )? / 300;
    let attack_for = |rolled_power: u16| -> Result<u16, PhysicalDamageError> {
        let stat_and_power = checked_add(
            stat_attack,
            checked_mul(
                checked_add(
                    i32::from(rolled_power),
                    i32::from(snapshot.power.refine_attack),
                )?,
                2,
            )?,
        )?;
        let attack = checked_add(
            checked_mul(i32::from(snapshot.level), 2)?,
            checked_mul(stat_and_power, hit_rate_percent)? / 100,
        )?;
        u16::try_from(attack).map_err(|_| PhysicalDamageError::ResultOutOfRange)
    };
    let defense = checked_add(
        checked_add(
            checked_add(i32::from(snapshot.level), i32::from(snapshot.vitality))?,
            i32::from(snapshot.armor_defense),
        )?,
        checked_add(
            i32::from(snapshot.defense_grade_bonus),
            i32::from(snapshot.party_defender_bonus),
        )?,
    )?;
    Ok(DisplayBattleValues {
        attack_min: attack_for(snapshot.power.power_min)?,
        attack_max: attack_for(snapshot.power.power_max)?,
        defense: u16::try_from(defense).map_err(|_| PhysicalDamageError::ResultOutOfRange)?,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, spacetimedb::SpacetimeType)]
pub struct CapturedPlayerAttacker {
    pub level: u8,
    pub strength: u8,
    pub dexterity: u8,
    pub stat_attack: i32,
    pub equipped_item_id: u64,
    pub equipped_vnum: u32,
}

fn validate_generated_policy() -> Result<(), String> {
    let policy = definitions::SELECTED_PHYSICAL_POLICY;
    let supported = policy.formula_id == "combat.physical.normal-melee.v1"
        && policy.rating_policy_id == "combat.attack-rating.attacker-level-victim-term.v1"
        && policy.rng_policy_id == "combat.rng.accepted-action-area-per-victim.v1"
        && policy.attack_grade_bonus == 0
        && policy.party_attack_bonus == 0
        && policy.attack_percent == 0
        && policy.melee_magic_attack_percent == 0
        && policy.defense_grade_bonus == 0
        && policy.party_defender_bonus == 0
        && policy.defense_percent == 0
        && policy.npc_attacker_marriage_defense_bonus == 0
        && policy.final_multiplier.to_bits() == 1.0_f32.to_bits()
        && policy.calc_att_bonus_percent == 0
        && policy.block_percent == 0
        && policy.normal_affect_damage == 0
        && policy.reflect_percent == 0
        && policy.critical_percent == 0
        && policy.resist_critical_percent == 0
        && policy.penetrate_percent == 0
        && policy.resist_penetrate_percent == 0
        && policy.hp_steal_percent == 0
        && policy.sp_steal_percent == 0
        && policy.gold_steal_percent == 0
        && policy.hit_hp_recovery == 0
        && policy.hit_sp_recovery == 0
        && policy.mana_burn_percent == 0
        && policy.normal_hit_damage_bonus_percent == 0
        && policy.normal_hit_defense_bonus_percent == 0;
    supported
        .then_some(())
        .ok_or_else(|| "The generated physical-damage policy is unsupported.".into())
}

fn zero_stages() -> SelectedZeroStages {
    SelectedZeroStages::default()
}

fn player_power(captured: CapturedPlayerAttacker) -> Result<PhysicalPowerSource, String> {
    if captured.equipped_vnum == 0 && captured.equipped_item_id == 0 {
        return Ok(PhysicalPowerSource {
            class: PhysicalWeaponClass::Unarmed,
            power_min: 0,
            power_max: 0,
            refine_attack: 0,
        });
    }
    let definition = crate::item_catalog::definition(captured.equipped_vnum)?;
    let weapon = definition
        .weapon
        .ok_or("The captured item is not a physical weapon.")?;
    if captured.equipped_item_id == 0
        || captured.equipped_vnum != weapon.vnum
        || weapon.item_id != definition.id
    {
        return Err("The captured physical weapon is unsupported.".into());
    }
    Ok(PhysicalPowerSource {
        class: match weapon.class {
            definitions::PhysicalWeaponClass::Sword => PhysicalWeaponClass::Sword,
            definitions::PhysicalWeaponClass::Fan => PhysicalWeaponClass::Fan,
        },
        power_min: weapon.power_min,
        power_max: weapon.power_max,
        refine_attack: weapon.refine_attack,
    })
}

fn policy_attacker(
    kind: CombatantKind,
    level: u8,
    strength: u8,
    dexterity: u8,
    power: PhysicalPowerSource,
    npc_damage_multiplier: f32,
) -> PhysicalAttackerSnapshot {
    let policy = definitions::SELECTED_PHYSICAL_POLICY;
    PhysicalAttackerSnapshot {
        kind,
        level,
        strength,
        dexterity,
        stat_attack: 2 * i32::from(strength),
        power,
        attack_grade_bonus: policy.attack_grade_bonus,
        party_attack_bonus: policy.party_attack_bonus,
        attack_percent: policy.attack_percent,
        melee_magic_attack_percent: policy.melee_magic_attack_percent,
        npc_damage_multiplier,
        final_multiplier: policy.final_multiplier,
    }
}

fn player_attacker(captured: CapturedPlayerAttacker) -> Result<PhysicalAttackerSnapshot, String> {
    validate_generated_policy()?;
    Ok(player_attacker_with_power(
        captured,
        player_power(captured)?,
    ))
}

fn player_attacker_with_power(
    captured: CapturedPlayerAttacker,
    power: PhysicalPowerSource,
) -> PhysicalAttackerSnapshot {
    let mut snapshot = policy_attacker(
        CombatantKind::Player,
        captured.level,
        captured.strength,
        captured.dexterity,
        power,
        1.0,
    );
    snapshot.stat_attack = captured.stat_attack;
    snapshot
}

fn dog_attacker() -> Result<PhysicalAttackerSnapshot, String> {
    validate_generated_policy()?;
    let dog = definitions::WILD_DOG_101_PHYSICAL;
    if dog.actor_id != definitions::MOB_ACTOR_ID || dog.vnum != definitions::MOB_VNUM {
        return Err("The generated Wild Dog physical definition is unsupported.".into());
    }
    Ok(policy_attacker(
        CombatantKind::Npc,
        dog.level,
        dog.strength,
        dog.dexterity,
        PhysicalPowerSource {
            class: PhysicalWeaponClass::Unarmed,
            power_min: dog.power_min,
            power_max: dog.power_max,
            refine_attack: 0,
        },
        dog.damage_multiplier,
    ))
}

fn policy_victim(
    kind: CombatantKind,
    level: u8,
    vitality: u8,
    dexterity: u8,
    proto_or_armor_defense: u16,
    sword_resistance_percent: u8,
    fan_resistance_percent: u8,
) -> PhysicalVictimSnapshot {
    let policy = definitions::SELECTED_PHYSICAL_POLICY;
    PhysicalVictimSnapshot {
        kind,
        level,
        vitality,
        dexterity,
        proto_or_armor_defense,
        defense_grade_bonus: policy.defense_grade_bonus,
        party_defender_bonus: policy.party_defender_bonus,
        defense_percent: policy.defense_percent,
        npc_attacker_marriage_defense_bonus: policy.npc_attacker_marriage_defense_bonus,
        sword_resistance_percent,
        fan_resistance_percent,
    }
}

fn dog_victim(monster: &Monster) -> Result<PhysicalVictimSnapshot, String> {
    validate_generated_policy()?;
    if let Some(d) = crate::training_targets::validate(monster)? {
        return Ok(policy_victim(
            CombatantKind::Npc,
            d.level,
            d.vitality,
            d.dexterity,
            d.defense,
            d.sword_resistance,
            d.fan_resistance,
        ));
    }
    let dog = definitions::WILD_DOG_101_PHYSICAL;
    if monster.definition_vnum != dog.vnum
        || monster.actor_id != dog.actor_id
        || monster.max_health != definitions::MOB_MAX_HEALTH
        || crate::combat::trusted_spawn(monster.id).is_none()
    {
        return Err("The physical victim is not the selected trusted Wild Dog.".into());
    }
    Ok(policy_victim(
        CombatantKind::Npc,
        dog.level,
        dog.vitality,
        dog.dexterity,
        dog.proto_defense,
        dog.sword_resistance_percent,
        dog.fan_resistance_percent,
    ))
}

fn player_victim(
    ctx: &ReducerContext,
    character: Identity,
) -> Result<PhysicalVictimSnapshot, String> {
    validate_generated_policy()?;
    let row = ctx
        .db
        .character_progression()
        .character_id()
        .find(character)
        .ok_or("Character progression is missing.")?;
    Ok(policy_victim(
        CombatantKind::Player,
        row.level,
        row.vitality,
        row.dexterity,
        0,
        0,
        0,
    ))
}

pub fn capture_player(
    ctx: &ReducerContext,
    character: Identity,
    requires_weapon: bool,
) -> Result<CapturedPlayerAttacker, String> {
    validate_generated_policy()?;
    let row = ctx
        .db
        .character_progression()
        .character_id()
        .find(character)
        .ok_or("Character progression is missing.")?;
    let equipped = inventory::equipped_weapon_item(ctx, character);
    let (equipped_item_id, equipped_vnum) = equipped.unwrap_or((0, 0));
    if requires_weapon && !crate::item_catalog::is_weapon(equipped_vnum) {
        return Err("The accepted physical action requires an equipped weapon.".into());
    }
    if !requires_weapon && equipped.is_some() {
        return Err("The accepted unarmed action cannot capture an equipped weapon.".into());
    }
    let captured = CapturedPlayerAttacker {
        level: row.level,
        strength: row.strength,
        dexterity: row.dexterity,
        stat_attack: crate::characters::stat_attack(
            row.character_class,
            row.strength,
            row.dexterity,
            row.intelligence,
        )?,
        equipped_item_id,
        equipped_vnum,
    };
    player_attacker(captured)?;
    Ok(captured)
}

fn calculate_with_rolls(
    attacker: PhysicalAttackerSnapshot,
    victim: PhysicalVictimSnapshot,
    mut power_roll: impl FnMut(u16, u16) -> u16,
    mut low_floor_roll: impl FnMut() -> u8,
) -> Result<u16, String> {
    validate_selected_policy(attacker, victim, zero_stages())
        .map_err(|error| format!("Unsupported selected physical snapshot: {error:?}"))?;
    let power = if attacker.power.power_min == attacker.power.power_max {
        attacker.power.power_min
    } else {
        power_roll(attacker.power.power_min, attacker.power.power_max)
    };
    let calculation = calculate_pre_floor(attacker, victim, power)
        .map_err(|error| format!("Physical damage calculation failed: {error:?}"))?;
    let low_floor =
        matches!(calculation.outcome, DamageBeforeFloor::NeedsLowFloor).then(&mut low_floor_roll);
    finish_damage(calculation, low_floor)
        .map(|result| result.damage)
        .map_err(|error| format!("Physical damage finalization failed: {error:?}"))
}

fn roll_damage(
    ctx: &ReducerContext,
    attacker: PhysicalAttackerSnapshot,
    victim: PhysicalVictimSnapshot,
) -> Result<u16, String> {
    calculate_with_rolls(
        attacker,
        victim,
        |minimum, maximum| ctx.rng().gen_range(minimum..=maximum),
        || ctx.rng().gen_range(1_u8..=5_u8),
    )
}

pub fn capture_ordinary_damage<T>(
    has_ordinary_target: bool,
    validated_target: Option<T>,
    mut draw: impl FnMut(T) -> Result<u16, String>,
) -> Result<u16, String> {
    if !has_ordinary_target {
        return Ok(0);
    }
    draw(validated_target.ok_or("The captured physical target is no longer valid.")?)
}

pub fn roll_player_hit(
    ctx: &ReducerContext,
    captured: CapturedPlayerAttacker,
    monster: &Monster,
) -> Result<u16, String> {
    roll_damage(ctx, player_attacker(captured)?, dog_victim(monster)?)
}

pub fn roll_skill_hit(
    ctx: &ReducerContext,
    definition: &definitions::SkillDefinition,
    rank: u8,
    captured: CapturedPlayerAttacker,
    vitality: u8,
    monster: &Monster,
) -> Result<u16, String> {
    let attacker = player_attacker(captured)?;
    let victim = dog_victim(monster)?;
    let power = ctx
        .rng()
        .gen_range(attacker.power.power_min..=attacker.power.power_max);
    let calculation = calculate_pre_floor(attacker, victim, power)
        .map_err(|error| format!("Invalid skill physical snapshot: {error:?}"))?;
    crate::skills::damage(
        definition,
        rank,
        calculation.diagnostics.attack_after_npc_multiplier,
        [captured.strength, captured.dexterity, vitality],
        calculation.diagnostics.applied_defense,
        victim.sword_resistance_percent,
    )
}

pub fn roll_monster_hit(
    ctx: &ReducerContext,
    monster: &Monster,
    target: Identity,
) -> Result<u16, String> {
    if monster.definition_vnum != definitions::WILD_DOG_101_PHYSICAL.vnum
        || monster.actor_id != definitions::WILD_DOG_101_PHYSICAL.actor_id
        || monster.max_health != definitions::MOB_MAX_HEALTH
        || crate::combat::trusted_spawn(monster.id).is_none()
    {
        return Err("The physical attacker is not the selected trusted Wild Dog.".into());
    }
    roll_damage(ctx, dog_attacker()?, player_victim(ctx, target)?)
}

pub fn display_values(
    ctx: &ReducerContext,
    character: Identity,
    row: &progression::CharacterProgression,
) -> Result<DisplayBattleValues, String> {
    validate_generated_policy()?;
    let (item_id, vnum) = inventory::equipped_weapon_item(ctx, character).unwrap_or((0, 0));
    let power = player_power(CapturedPlayerAttacker {
        level: row.level,
        strength: row.strength,
        dexterity: row.dexterity,
        stat_attack: crate::characters::stat_attack(
            row.character_class,
            row.strength,
            row.dexterity,
            row.intelligence,
        )?,
        equipped_item_id: item_id,
        equipped_vnum: vnum,
    })?;
    class_display_values(
        WarriorDisplaySnapshot {
            level: row.level,
            strength: row.strength,
            vitality: row.vitality,
            dexterity: row.dexterity,
            power,
            armor_defense: 0,
            defense_grade_bonus: definitions::SELECTED_PHYSICAL_POLICY.defense_grade_bonus,
            party_defender_bonus: definitions::SELECTED_PHYSICAL_POLICY.party_defender_bonus,
        },
        crate::characters::stat_attack(
            row.character_class,
            row.strength,
            row.dexterity,
            row.intelligence,
        )?,
    )
    .map_err(|error| format!("Physical display projection failed: {error:?}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    fn initial_warrior(power: PhysicalPowerSource) -> PhysicalAttackerSnapshot {
        warrior(1, 6, 3, power)
    }

    fn display_snapshot(
        strength: u8,
        vitality: u8,
        dexterity: u8,
        power: PhysicalPowerSource,
    ) -> WarriorDisplaySnapshot {
        WarriorDisplaySnapshot {
            level: 1,
            strength,
            vitality,
            dexterity,
            power,
            armor_defense: 0,
            defense_grade_bonus: 0,
            party_defender_bonus: 0,
        }
    }

    fn damage_domain(
        attacker: PhysicalAttackerSnapshot,
        victim: PhysicalVictimSnapshot,
    ) -> Vec<u16> {
        (attacker.power.power_min..=attacker.power.power_max)
            .map(|roll| {
                calculate_selected_damage(
                    attacker,
                    victim,
                    SelectedZeroStages::default(),
                    roll,
                    None,
                )
                .unwrap()
                .damage
            })
            .collect()
    }

    #[test]
    fn runtime_roll_adapter_draws_only_the_required_random_values() {
        let power_calls = Cell::new(0_u8);
        let floor_calls = Cell::new(0_u8);
        let sword = calculate_with_rolls(
            initial_warrior(SWORD_10_POWER),
            wild_dog_victim(),
            |minimum, _| {
                power_calls.set(power_calls.get() + 1);
                minimum
            },
            || {
                floor_calls.set(floor_calls.get() + 1);
                1
            },
        )
        .unwrap();
        assert_eq!(sword, 17);
        assert_eq!((power_calls.get(), floor_calls.get()), (1, 0));

        power_calls.set(0);
        let unarmed = calculate_with_rolls(
            initial_warrior(UNARMED_POWER),
            wild_dog_victim(),
            |_, _| {
                power_calls.set(power_calls.get() + 1);
                0
            },
            || {
                floor_calls.set(floor_calls.get() + 1);
                4
            },
        )
        .unwrap();
        assert_eq!(unarmed, 4);
        assert_eq!((power_calls.get(), floor_calls.get()), (0, 1));
    }

    #[test]
    fn captured_player_stats_remain_immutable_after_canonical_values_change() {
        let captured = CapturedPlayerAttacker {
            level: 1,
            strength: 6,
            dexterity: 3,
            stat_attack: 12,
            equipped_item_id: 10,
            equipped_vnum: 10,
        };
        let later_canonical = CapturedPlayerAttacker {
            strength: 7,
            dexterity: 4,
            stat_attack: 14,
            ..captured
        };
        let accepted = player_attacker_with_power(captured, SWORD_10_POWER);
        let later = player_attacker_with_power(later_canonical, SWORD_10_POWER);
        assert_eq!((accepted.strength, accepted.dexterity), (6, 3));
        assert_eq!((later.strength, later.dexterity), (7, 4));
        assert_eq!(
            calculate_damage(accepted, wild_dog_victim(), 13, None)
                .unwrap()
                .damage,
            17
        );
        assert_eq!(
            calculate_damage(later, wild_dog_victim(), 13, None)
                .unwrap()
                .damage,
            18
        );
    }

    #[test]
    fn targetless_or_rejected_boundary_never_invokes_damage_draw() {
        let calls = Cell::new(0_u8);
        assert_eq!(
            capture_ordinary_damage(false, None::<u8>, |_| {
                calls.set(calls.get() + 1);
                Ok(99)
            })
            .unwrap(),
            0
        );
        assert_eq!(calls.get(), 0);
        assert_eq!(
            capture_ordinary_damage(true, None::<u8>, |_| {
                calls.set(calls.get() + 1);
                Ok(17)
            })
            .unwrap_err(),
            "The captured physical target is no longer valid."
        );
        assert_eq!(calls.get(), 0);
        assert_eq!(
            capture_ordinary_damage(true, Some(7_u8), |target| {
                assert_eq!(target, 7);
                calls.set(calls.get() + 1);
                Ok(17)
            })
            .unwrap(),
            17
        );
        assert_eq!(calls.get(), 1);
    }

    #[test]
    fn selected_rating_sources_and_binary32_bits_match_pin() {
        let (player_rating, player_source, dog_source) = attack_rating(3, 1, 6).unwrap();
        assert_eq!((player_source, dog_source), (2, 4));
        assert_eq!(player_rating.to_bits(), 0x3f2a_d262);

        let (dog_rating, dog_source, player_source) = attack_rating(6, 1, 3).unwrap();
        assert_eq!((dog_source, player_source), (4, 2));
        assert_eq!(dog_rating.to_bits(), 0x3f2f_7cd0);
    }

    #[test]
    fn selected_sword_and_wild_dog_rolls_exhaust_exact_damage_domains() {
        assert_eq!(
            damage_domain(initial_warrior(SWORD_10_POWER), wild_dog_victim()),
            [17, 18, 20]
        );
        assert_eq!(
            damage_domain(wild_dog_attacker(), warrior_victim(1, 4, 3)),
            [29, 30, 32, 33, 35]
        );
    }

    #[test]
    fn unarmed_zero_is_replaced_by_an_independent_inclusive_floor_roll() {
        let attacker = initial_warrior(UNARMED_POWER);
        let victim = wild_dog_victim();
        let calculation = calculate_pre_floor(attacker, victim, 0).unwrap();
        assert_eq!(calculation.outcome, DamageBeforeFloor::NeedsLowFloor);
        assert_eq!(calculation.diagnostics.pre_floor_damage, 0);
        assert_eq!(
            (1..=5)
                .map(|roll| finish_damage(calculation, Some(roll)).unwrap().damage)
                .collect::<Vec<_>>(),
            [1, 2, 3, 4, 5]
        );
        assert_eq!(
            finish_damage(calculation, None),
            Err(PhysicalDamageError::InvalidLowFloorRoll)
        );
        assert_eq!(
            finish_damage(calculation, Some(0)),
            Err(PhysicalDamageError::InvalidLowFloorRoll)
        );
    }

    #[test]
    fn retained_damage_rejects_an_unused_floor_roll() {
        let attacker = initial_warrior(SWORD_10_POWER);
        let victim = wild_dog_victim();
        let calculation = calculate_pre_floor(attacker, victim, 13).unwrap();
        assert_eq!(calculation.outcome, DamageBeforeFloor::Retained(17));
        assert_eq!(
            finish_damage(calculation, Some(1)),
            Err(PhysicalDamageError::UnexpectedLowFloorRoll)
        );
    }

    #[test]
    fn strength_vitality_and_dexterity_mutations_match_domains_and_plateau() {
        let st7 = warrior(1, 7, 3, SWORD_10_POWER);
        assert_eq!(damage_domain(st7, wild_dog_victim()), [18, 20, 21]);

        let ht5 = warrior_victim(1, 5, 3);
        assert_eq!(server_defense_grade(ht5).unwrap(), 5);
        assert_eq!(
            damage_domain(wild_dog_attacker(), ht5),
            [28, 29, 31, 32, 34]
        );

        let dx4 = warrior(1, 6, 4, SWORD_10_POWER);
        let (outgoing_rating, _, _) = attack_rating(4, 1, 6).unwrap();
        assert_eq!(outgoing_rating.to_bits(), 0x3f2b_acd6);
        assert_eq!(damage_domain(dx4, wild_dog_victim()), [17, 18, 20]);

        let dx4_victim = warrior_victim(1, 4, 4);
        let (incoming_rating, _, _) = attack_rating(6, 1, 4).unwrap();
        assert_eq!(incoming_rating.to_bits(), 0x3f2d_fe30);
        assert_eq!(
            damage_domain(wild_dog_attacker(), dx4_victim),
            [29, 30, 31, 33, 34]
        );
    }

    #[test]
    fn gameplay_earned_level_two_allocations_match_shared_cases() {
        let cases: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/physical-stat-cases.json"
        ))
        .unwrap();
        assert_eq!(cases["schema_version"], 1);
        assert_eq!(cases["formula_id"], "combat.physical.normal-melee.v1");
        let rows = cases["cases"].as_array().unwrap();
        assert_eq!(rows.len(), 4);
        for row in rows {
            let number = |field: &str| u8::try_from(row[field].as_u64().unwrap()).unwrap();
            let level = number("level");
            let strength = number("strength");
            let vitality = number("vitality");
            let dexterity = number("dexterity");
            assert_eq!(
                serde_json::json!(damage_domain(
                    warrior(level, strength, dexterity, SWORD_10_POWER),
                    wild_dog_victim(),
                )),
                row["sword_damage"]
            );
            assert_eq!(
                serde_json::json!(damage_domain(
                    wild_dog_attacker(),
                    warrior_victim(level, vitality, dexterity),
                )),
                row["dog_damage"]
            );
            let mut snapshot = display_snapshot(strength, vitality, dexterity, SWORD_10_POWER);
            snapshot.level = level;
            let display = warrior_display_values(snapshot).unwrap();
            assert_eq!(
                u64::from(display.attack_min),
                row["attack_min"].as_u64().unwrap()
            );
            assert_eq!(
                u64::from(display.attack_max),
                row["attack_max"].as_u64().unwrap()
            );
            assert_eq!(u64::from(display.defense), row["defense"].as_u64().unwrap());
            assert_eq!(
                u64::from(attack_rating(dexterity, level, 6).unwrap().0.to_bits()),
                row["rating_bits"].as_u64().unwrap(),
            );
        }
    }

    #[test]
    fn npc_multiplier_is_applied_before_defense_and_clamp() {
        let (multiplied, damage) = npc_multiply_then_defend(10, 2.0, 15).unwrap();
        assert_eq!((multiplied, damage), (20, 5));
    }

    #[test]
    fn fan_uses_its_own_resistance_and_shaman_stat_attack() {
        let mut attacker = initial_warrior(PhysicalPowerSource {
            class: PhysicalWeaponClass::Fan,
            power_min: 11,
            power_max: 15,
            refine_attack: 0,
        });
        attacker.strength = 3;
        attacker.stat_attack = crate::characters::stat_attack(3, 3, 3, 6).unwrap();
        let mut victim = wild_dog_victim();
        let full = calculate_damage(attacker, victim, 15, None).unwrap().damage;
        victim.sword_resistance_percent = 100;
        assert_eq!(
            calculate_damage(attacker, victim, 15, None).unwrap().damage,
            full
        );
        victim.fan_resistance_percent = 50;
        assert_eq!(
            calculate_damage(attacker, victim, 15, None).unwrap().damage,
            full / 2
        );
        victim.fan_resistance_percent = 101;
        assert_eq!(
            calculate_damage(attacker, victim, 15, None),
            Err(PhysicalDamageError::InvalidResistance)
        );
    }

    #[test]
    fn sword_resistance_precedes_nearest_nonnegative_final_multiplier() {
        let mut attacker = initial_warrior(SWORD_10_POWER);
        attacker.final_multiplier = 1.5;
        let mut victim = wild_dog_victim();
        victim.sword_resistance_percent = 50;
        let calculation = calculate_pre_floor(attacker, victim, 15).unwrap();
        let final_damage = finish_damage(calculation, None).unwrap();
        // 20 * 50 / 100 = 10, then trunc(1.5 * 10 + 0.5) = 15.
        assert_eq!(final_damage.damage, 15);
    }

    #[test]
    fn private_display_values_match_selected_status_rows() {
        assert_eq!(
            warrior_display_values(display_snapshot(6, 4, 3, SWORD_10_POWER)).unwrap(),
            DisplayBattleValues {
                attack_min: 28,
                attack_max: 31,
                defense: 5,
            }
        );
        assert_eq!(
            warrior_display_values(display_snapshot(6, 4, 3, UNARMED_POWER)).unwrap(),
            DisplayBattleValues {
                attack_min: 10,
                attack_max: 10,
                defense: 5,
            }
        );
        assert_eq!(
            warrior_display_values(display_snapshot(7, 4, 3, SWORD_10_POWER)).unwrap(),
            DisplayBattleValues {
                attack_min: 30,
                attack_max: 32,
                defense: 5,
            }
        );
    }

    #[test]
    fn selected_grade_diagnostics_keep_server_and_display_defense_distinct() {
        let calculation =
            calculate_pre_floor(initial_warrior(SWORD_10_POWER), wild_dog_victim(), 13).unwrap();
        assert_eq!(calculation.diagnostics.attack_grade, 14);
        assert_eq!(calculation.diagnostics.defense_grade, 10);
        assert_eq!(server_defense_grade(warrior_victim(1, 4, 3)).unwrap(), 4);
        assert_eq!(
            warrior_display_values(display_snapshot(6, 4, 3, SWORD_10_POWER))
                .unwrap()
                .defense,
            5
        );
    }

    #[test]
    fn authored_resistances_flow_through_runtime_validation_and_damage() {
        let attacker = initial_warrior(SWORD_10_POWER);
        let mut victim = wild_dog_victim();
        let unresisted = calculate_with_rolls(attacker, victim, |lo, _| lo, || 3).unwrap();
        victim.sword_resistance_percent = 50;
        let resisted = calculate_with_rolls(attacker, victim, |lo, _| lo, || 3).unwrap();
        assert!(resisted < unresisted);
        assert_eq!(resisted, unresisted / 2);
        victim.sword_resistance_percent = 101;
        assert!(calculate_with_rolls(attacker, victim, |lo, _| lo, || 3).is_err());
    }

    #[test]
    fn selected_policy_rejects_nonzero_or_broadened_stages() {
        let attacker = initial_warrior(SWORD_10_POWER);
        let victim = wild_dog_victim();
        assert_eq!(
            validate_selected_policy(attacker, victim, SelectedZeroStages::default()),
            Ok(())
        );

        let mut synthetic_multiplier = attacker;
        synthetic_multiplier.final_multiplier = 1.5;
        assert_eq!(
            validate_selected_policy(synthetic_multiplier, victim, SelectedZeroStages::default()),
            Err(PhysicalDamageError::UnsupportedSelectedPolicy)
        );

        let stages = SelectedZeroStages {
            calc_att_bonus_percent: 1,
            ..SelectedZeroStages::default()
        };
        assert_eq!(
            validate_selected_policy(attacker, victim, stages),
            Err(PhysicalDamageError::UnsupportedSelectedPolicy)
        );
    }

    #[test]
    fn binary32_to_i32_conversion_keeps_upper_bound_exclusive() {
        let below_upper = f32::from_bits(2_147_483_648.0_f32.to_bits() - 1);
        assert_eq!(trunc_f32_i32(below_upper), Ok(2_147_483_520));
        assert_eq!(trunc_f32_i32(-2_147_483_648.0_f32), Ok(i32::MIN));
        assert_eq!(
            trunc_f32_i32(2_147_483_648.0_f32),
            Err(PhysicalDamageError::ArithmeticOverflow)
        );
    }

    #[test]
    fn invalid_domains_fail_before_arithmetic() {
        let victim = wild_dog_victim();
        assert_eq!(
            calculate_pre_floor(initial_warrior(SWORD_10_POWER), victim, 12),
            Err(PhysicalDamageError::InvalidPowerRoll)
        );
        let mut invalid = initial_warrior(SWORD_10_POWER);
        invalid.level = 0;
        assert_eq!(
            calculate_pre_floor(invalid, victim, 13),
            Err(PhysicalDamageError::InvalidLevel)
        );
        invalid = initial_warrior(SWORD_10_POWER);
        invalid.final_multiplier = f32::NAN;
        assert_eq!(
            calculate_pre_floor(invalid, victim, 13),
            Err(PhysicalDamageError::InvalidMultiplier)
        );
        let mut invalid_victim = victim;
        invalid_victim.sword_resistance_percent = 101;
        assert_eq!(
            calculate_pre_floor(initial_warrior(SWORD_10_POWER), invalid_victim, 13),
            Err(PhysicalDamageError::InvalidResistance)
        );
    }
}
