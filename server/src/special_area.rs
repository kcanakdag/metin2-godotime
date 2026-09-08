//! Trusted combo4 fixed-area damage and activation lifecycle.

use crate::combat::{monster, monster_clock};
#[cfg(test)]
use crate::combat_geometry::squared_distance_to_segment;
use crate::combat_geometry::{rotate, swept_sphere_intersects};
use crate::definitions::{self, AttackDefinition, ScreenWaveDefinition, SpecialAreaDefinition};
use crate::knockback::{force_direction, is_front_hit};
use crate::{Controller, accounts, controller, player};
use spacetimedb::{Identity, ReducerContext, Table};

const AREA_HIT_TYPE_GREAT: u8 = 1;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum AreaPhase {
    Waiting,
    Activate,
    ActivatedThisTick,
    Scan,
    Expired,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum VictimScanDecision {
    StopAtLimit,
    SkipAlreadyHit,
    TrackOnly,
    ApplyHit,
}

fn victim_scan_decision(
    hit_count: u8,
    max_targets: u8,
    already_hit: bool,
    intersects: bool,
    cooldown_allows: bool,
) -> VictimScanDecision {
    if hit_count >= max_targets {
        VictimScanDecision::StopAtLimit
    } else if already_hit {
        VictimScanDecision::SkipAlreadyHit
    } else if !intersects || !cooldown_allows {
        VictimScanDecision::TrackOnly
    } else {
        VictimScanDecision::ApplyHit
    }
}

fn apply_scan_decision(
    decision: VictimScanDecision,
    mut apply: impl FnMut() -> Result<bool, String>,
) -> Result<bool, String> {
    if decision == VictimScanDecision::ApplyHit {
        apply()
    } else {
        Ok(false)
    }
}

fn area_phase(
    now: i64,
    activation_at_us: i64,
    expires_at_us: i64,
    activated_at_tick_us: i64,
) -> AreaPhase {
    if now >= expires_at_us {
        AreaPhase::Expired
    } else if activated_at_tick_us == 0 {
        if now < activation_at_us {
            AreaPhase::Waiting
        } else {
            AreaPhase::Activate
        }
    } else if now <= activated_at_tick_us {
        AreaPhase::ActivatedThisTick
    } else {
        AreaPhase::Scan
    }
}

#[spacetimedb::table(accessor = special_area)]
pub struct SpecialArea {
    #[primary_key]
    pub character_id: Identity,
    pub owner_life_sequence: u32,
    pub action_revision: u64,
    pub action_started_at_us: i64,
    pub activation_at_us: i64,
    pub expires_at_us: i64,
    pub activated_at_tick_us: i64,
    pub center_x: f32,
    pub center_y: f32,
    pub center_z: f32,
    pub heading: f32,
    pub attacker_level: u8,
    pub attacker_strength: u8,
    pub attacker_stat_attack: i32,
    pub attacker_dexterity: u8,
    pub equipped_item_id: u64,
    pub equipped_vnum: u32,
    pub hit_count: u8,
}

#[spacetimedb::table(accessor = special_area_victim)]
pub struct SpecialAreaVictim {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub character_id: Identity,
    pub action_revision: u64,
    pub monster_id: u32,
    pub monster_life_sequence: u32,
    pub previous_center_x: f32,
    pub previous_center_y: f32,
    pub previous_center_z: f32,
    pub hit: bool,
}

fn valid_definition(area: SpecialAreaDefinition) -> bool {
    matches!(
        (
            area.authored_start_us,
            area.legacy_dispatch_frame,
            area.activation_offset_us
        ),
        (659_316, 39, 666_667) | (434_359, 26, 450_000)
    ) && area.duration_us == 200_000
        && area.local_center_x_m.is_finite()
        && area.local_center_x_m == 0.0
        && area.local_center_z_m.is_finite()
        && area.local_center_z_m == -1.2
        && area.radius_m.is_finite()
        && area.radius_m == 1.0
        && area.max_targets == 16
        && area.hit_once_per_life
        && area.hit_type == AREA_HIT_TYPE_GREAT
        && area.invulnerability_us == 300_000
        && area.knockback.source_external_force == 17.0
        && area.knockback.unobstructed_distance_m == 4.732
        && area.knockback.duration_us == 1_000_000
}

fn valid_screen_wave(wave: ScreenWaveDefinition) -> bool {
    wave.authored_start_us == 630_086
        && wave.legacy_dispatch_frame == 37
        && wave.activation_offset_us == 633_334
        && wave.duration_us == 200_000
        && wave.viewer_range_m.is_finite()
        && wave.viewer_range_m == 2.0
        && wave.source_power == 300
        && wave.source_component_step_m.is_finite()
        && wave.source_component_step_m == 0.001
        && wave.source_component_exclusive_max_m.is_finite()
        && wave.source_component_exclusive_max_m == 0.3
}

/// Validate the generated action/event pairing at the gameplay boundary. The
/// wave is presentation-only, but reading and checking it here prevents a
/// malformed trusted definition from starting the authoritative area action.
pub fn validate_action_definition(definition: &AttackDefinition) -> Result<(), String> {
    if let (Some(area), None) = (definition.special_area, definition.screen_wave)
        && valid_definition(area)
        && area
            .activation_offset_us
            .checked_add(area.duration_us)
            .is_some_and(|end| end <= definition.duration_us)
        && definitions::CHARACTER_BASIC_ATTACKS
            .iter()
            .any(|(_, weapon, action)| {
                *weapon == 10 && action.id == definition.id && action.special_area.is_some()
            })
    {
        // These selected Warrior/Ninja finishers share the exact validated
        // geometry, force and victim policy; activation times are captured.
        return Ok(());
    }
    match (definition.special_area, definition.screen_wave) {
        (None, None) => Ok(()),
        (Some(area), Some(wave))
            if definition.id == definitions::PLAYER_ONEHAND_COMBO[3].id
                && valid_definition(area)
                && valid_screen_wave(wave)
                && area
                    .activation_offset_us
                    .checked_add(area.duration_us)
                    .is_some_and(|end| end <= definition.duration_us)
                && wave
                    .activation_offset_us
                    .checked_add(wave.duration_us)
                    .is_some_and(|end| end <= definition.duration_us) =>
        {
            Ok(())
        }
        _ => Err("The trusted special action definition is invalid.".into()),
    }
}

fn clear_victims(ctx: &ReducerContext, character: Identity) {
    let ids: Vec<u64> = ctx
        .db
        .special_area_victim()
        .character_id()
        .filter(character)
        .map(|row| row.id)
        .collect();
    for id in ids {
        ctx.db.special_area_victim().id().delete(id);
    }
}

fn seed_victims(ctx: &ReducerContext, area: &SpecialArea) {
    let mut victims: Vec<_> = ctx
        .db
        .monster()
        .iter()
        .filter(|monster| trusted_victim(ctx, monster))
        .collect();
    victims.sort_by_key(|row| (row.id, row.life_sequence));
    for monster in victims {
        let Some(center) = victim_center(ctx, &monster) else {
            continue;
        };
        ctx.db.special_area_victim().insert(SpecialAreaVictim {
            id: 0,
            character_id: area.character_id,
            action_revision: area.action_revision,
            monster_id: monster.id,
            monster_life_sequence: monster.life_sequence,
            previous_center_x: center[0] as f32,
            previous_center_y: center[1] as f32,
            previous_center_z: center[2] as f32,
            hit: false,
        });
    }
}

pub fn clear(ctx: &ReducerContext, character: Identity) {
    ctx.db.special_area().character_id().delete(character);
    clear_victims(ctx, character);
}

pub fn start(
    ctx: &ReducerContext,
    controller: &Controller,
    definition: &'static AttackDefinition,
    owner_life_sequence: u32,
    now: i64,
    heading: f32,
    captured_attacker: Option<crate::physical_damage::CapturedPlayerAttacker>,
) -> Result<(), String> {
    clear(ctx, controller.identity);
    let Some(area) = definition.special_area else {
        return Ok(());
    };
    let captured_attacker =
        captured_attacker.ok_or("The trusted special-area attacker snapshot is missing.")?;
    if validate_action_definition(definition).is_err()
        || controller.action_revision == 0
        || !heading.is_finite()
    {
        return Err("The trusted special-area action is invalid.".into());
    }
    let activation_at_us = now
        .checked_add(crate::attack_timing::scaled_us(
            area.activation_offset_us,
            controller.attack_speed_percent,
        )?)
        .ok_or("Special-area timestamp is outside the supported range.")?;
    let expires_at_us = activation_at_us
        .checked_add(area.duration_us)
        .ok_or("Special-area timestamp is outside the supported range.")?;
    ctx.db.special_area().insert(SpecialArea {
        character_id: controller.identity,
        owner_life_sequence,
        action_revision: controller.action_revision,
        action_started_at_us: now,
        activation_at_us,
        expires_at_us,
        activated_at_tick_us: 0,
        center_x: 0.0,
        center_y: 0.0,
        center_z: 0.0,
        heading,
        attacker_level: captured_attacker.level,
        attacker_strength: captured_attacker.strength,
        attacker_stat_attack: captured_attacker.stat_attack,
        attacker_dexterity: captured_attacker.dexterity,
        equipped_item_id: captured_attacker.equipped_item_id,
        equipped_vnum: captured_attacker.equipped_vnum,
        hit_count: 0,
    });
    Ok(())
}

fn owner_is_valid(ctx: &ReducerContext, area: &SpecialArea) -> bool {
    let Some(control) = ctx.db.controller().identity().find(area.character_id) else {
        return false;
    };
    let Some(owner) = ctx.db.player().identity().find(area.character_id) else {
        return false;
    };
    owner.online
        && owner.health > 0
        && owner_life_matches(area.owner_life_sequence, owner.life_sequence)
        && control.action_revision == area.action_revision
        && accounts::controller_has_active_lease(ctx, &control)
}

fn owner_life_matches(captured: u32, current: u32) -> bool {
    captured == current
}

/// Inject each activation at its exact canonical action-relative boundary
/// before the normal root pass can advance the owner beyond the captured point.
pub fn activate_due(ctx: &ReducerContext, now: i64) -> Result<(), String> {
    let mut characters: Vec<Identity> = ctx
        .db
        .special_area()
        .iter()
        .map(|row| row.character_id)
        .collect();
    characters.sort_by_key(|identity| identity.to_string());
    for character in characters {
        let Some(mut area) = ctx.db.special_area().character_id().find(character) else {
            continue;
        };
        if !owner_is_valid(ctx, &area)
            || area_phase(
                now,
                area.activation_at_us,
                area.expires_at_us,
                area.activated_at_tick_us,
            ) == AreaPhase::Expired
        {
            clear(ctx, character);
            continue;
        }
        if area_phase(
            now,
            area.activation_at_us,
            area.expires_at_us,
            area.activated_at_tick_us,
        ) != AreaPhase::Activate
        {
            continue;
        }
        let Some(mut control) = ctx.db.controller().identity().find(character) else {
            clear(ctx, character);
            continue;
        };
        crate::root_motion::advance_for_event(ctx, &mut control, area.activation_at_us)?;
        ctx.db.controller().identity().update(control);
        let Some(owner) = ctx.db.player().identity().find(character) else {
            clear(ctx, character);
            continue;
        };
        let definition = definitions::PLAYER_ONEHAND_COMBO[3]
            .special_area
            .ok_or("The trusted special-area definition is missing.")?;
        let offset = rotate(
            definition.local_center_x_m,
            definition.local_center_z_m,
            area.heading,
        )
        .ok_or("Special-area placement is invalid.")?;
        area.center_x = owner.x + offset.0;
        area.center_y = owner.y;
        area.center_z = owner.z + offset.1;
        area.activated_at_tick_us = now;
        seed_victims(ctx, &area);
        ctx.db.special_area().character_id().update(area);
    }
    Ok(())
}

fn trusted_victim(ctx: &ReducerContext, monster: &crate::combat::Monster) -> bool {
    monster.health > 0 && crate::combat::validate_monster(ctx, monster).is_ok()
}

fn victim_center(ctx: &ReducerContext, monster: &crate::combat::Monster) -> Option<[f64; 3]> {
    let sphere = crate::combat::defending_sphere(ctx, monster);
    if !sphere.local_center_y_m.is_finite()
        || !sphere.radius_m.is_finite()
        || sphere.radius_m <= 0.0
    {
        return None;
    }
    let offset = rotate(
        sphere.local_center_x_m,
        sphere.local_center_z_m,
        monster.heading,
    )?;
    Some([
        f64::from(monster.x + offset.0),
        f64::from(monster.y) + sphere.local_center_y_m,
        f64::from(monster.z + offset.1),
    ])
}

fn matching_victim_row(
    ctx: &ReducerContext,
    area: &SpecialArea,
    monster_id: u32,
    life_sequence: u32,
) -> Option<SpecialAreaVictim> {
    ctx.db
        .special_area_victim()
        .character_id()
        .filter(area.character_id)
        .find(|row| {
            row.action_revision == area.action_revision
                && row.monster_id == monster_id
                && row.monster_life_sequence == life_sequence
        })
}

fn area_hits(
    area: &SpecialArea,
    previous: [f64; 3],
    current: [f64; 3],
    victim_radius: f64,
) -> bool {
    let definition = definitions::PLAYER_ONEHAND_COMBO[3]
        .special_area
        .expect("selected combo4 has a validated special area");
    let radius = definition.radius_m + victim_radius;
    swept_sphere_intersects(
        [
            f64::from(area.center_x),
            f64::from(area.center_y),
            f64::from(area.center_z),
        ],
        previous,
        current,
        radius,
    )
}

fn apply_hit(
    ctx: &ReducerContext,
    area: &SpecialArea,
    monster: &mut crate::combat::Monster,
    now: i64,
) -> Result<bool, String> {
    let definition = definitions::PLAYER_ONEHAND_COMBO[3]
        .special_area
        .ok_or("The trusted special-area definition is missing.")?;
    let mut clock = ctx
        .db
        .monster_clock()
        .id()
        .find(monster.id)
        .ok_or("The trusted monster clock is missing.")?;
    if !crate::combat::monster_hit_cooldown_allows(ctx, monster.id, now) {
        return Ok(false);
    }
    crate::combat::cancel_monster_hit(&mut clock);
    clock.attack_until_us = 0;
    ctx.db.monster_clock().id().update(clock);
    crate::combat::mark_monster_hit_cooldown(ctx, monster.id, now, definition.invulnerability_us)?;

    let controller = ctx
        .db
        .controller()
        .identity()
        .find(area.character_id)
        .ok_or("The special-area owner is no longer controlled.")?;
    let owner = ctx
        .db
        .player()
        .identity()
        .find(area.character_id)
        .ok_or("The special-area owner is no longer present.")?;
    let damage = crate::physical_damage::roll_player_hit(
        ctx,
        crate::physical_damage::CapturedPlayerAttacker {
            level: area.attacker_level,
            strength: area.attacker_strength,
            stat_attack: area.attacker_stat_attack,
            dexterity: area.attacker_dexterity,
            equipped_item_id: area.equipped_item_id,
            equipped_vnum: area.equipped_vnum,
        },
        monster,
    )?;
    crate::combat::record_damage(
        ctx,
        monster.id,
        monster.life_sequence,
        area.character_id,
        controller.connection_id,
        u32::from(damage),
        crate::mob_threat::DamageKind::Normal,
    )?;
    if crate::combat::apply_damage(&mut monster.health, damage) {
        crate::combat::kill_monster(ctx, monster, area.character_id);
        return Ok(true);
    }

    let direction = force_direction((owner.x, owner.z), monster);
    crate::knockback::start(
        ctx,
        monster,
        crate::knockback::ForceStart {
            source_character: area.character_id,
            source_action_revision: area.action_revision,
            now,
            front: is_front_hit(area.heading, monster.heading),
            direction,
            distance_m: definition.knockback.unobstructed_distance_m,
            duration_us: definition.knockback.duration_us,
        },
    )?;
    Ok(true)
}

pub fn scan(ctx: &ReducerContext, now: i64) -> Result<(), String> {
    let mut characters: Vec<Identity> = ctx
        .db
        .special_area()
        .iter()
        .map(|row| row.character_id)
        .collect();
    characters.sort_by_key(|identity| identity.to_string());
    for character in characters {
        let Some(mut area) = ctx.db.special_area().character_id().find(character) else {
            continue;
        };
        let phase = area_phase(
            now,
            area.activation_at_us,
            area.expires_at_us,
            area.activated_at_tick_us,
        );
        if !owner_is_valid(ctx, &area) || phase == AreaPhase::Expired {
            clear(ctx, character);
            continue;
        }
        if phase != AreaPhase::Scan {
            continue;
        }
        let definition = definitions::PLAYER_ONEHAND_COMBO[3]
            .special_area
            .ok_or("The trusted special-area definition is missing.")?;
        let mut victims: Vec<_> = ctx
            .db
            .monster()
            .iter()
            .filter(|monster| trusted_victim(ctx, monster))
            .collect();
        victims.sort_by_key(|row| (row.id, row.life_sequence));
        for mut monster in victims {
            let Some(current) = victim_center(ctx, &monster) else {
                continue;
            };
            let previous_row = matching_victim_row(ctx, &area, monster.id, monster.life_sequence);
            let previous = previous_row.as_ref().map_or(current, |row| {
                [
                    f64::from(row.previous_center_x),
                    f64::from(row.previous_center_y),
                    f64::from(row.previous_center_z),
                ]
            });
            let intersects = area_hits(
                &area,
                previous,
                current,
                crate::combat::defending_sphere(ctx, &monster).radius_m,
            );
            let decision = victim_scan_decision(
                area.hit_count,
                definition.max_targets,
                previous_row.as_ref().is_some_and(|row| row.hit),
                intersects,
                crate::combat::monster_hit_cooldown_allows(ctx, monster.id, now),
            );
            if decision == VictimScanDecision::StopAtLimit {
                break;
            }
            if decision == VictimScanDecision::SkipAlreadyHit {
                continue;
            }
            let before_health = monster.health;
            let hit = apply_scan_decision(decision, || apply_hit(ctx, &area, &mut monster, now))?;
            if let Some(mut row) = previous_row {
                row.previous_center_x = current[0] as f32;
                row.previous_center_y = current[1] as f32;
                row.previous_center_z = current[2] as f32;
                row.hit = hit;
                ctx.db.special_area_victim().id().update(row);
            } else {
                ctx.db.special_area_victim().insert(SpecialAreaVictim {
                    id: 0,
                    character_id: character,
                    action_revision: area.action_revision,
                    monster_id: monster.id,
                    monster_life_sequence: monster.life_sequence,
                    previous_center_x: current[0] as f32,
                    previous_center_y: current[1] as f32,
                    previous_center_z: current[2] as f32,
                    hit,
                });
            }
            if !hit {
                continue;
            }
            if monster.health != before_health {
                area.hit_count = area
                    .hit_count
                    .checked_add(1)
                    .ok_or("Special-area victim limit overflowed.")?;
                ctx.db.monster().id().update(monster);
            }
        }
        ctx.db.special_area().character_id().update(area);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn full_three_dimensional_first_scan_sweep_includes_crossing_and_boundary() {
        let radius = 1.9_f64;
        assert!(
            squared_distance_to_segment([0.0, 0.0, 0.0], [-2.0, radius, 0.0], [2.0, radius, 0.0])
                <= radius * radius
        );
        assert!(
            squared_distance_to_segment([0.0, 0.0, 0.0], [-2.0, 0.0, 0.0], [2.0, 0.0, 0.0])
                <= radius * radius
        );
        assert!(
            squared_distance_to_segment(
                [0.0, 0.0, 0.0],
                [2.0, radius + 0.001, 0.0],
                [3.0, radius + 0.001, 0.0]
            ) > radius * radius
        );
    }

    #[test]
    fn runtime_scan_policy_caps_sixteen_and_retries_after_global_cooldown() {
        let mut hit_count = 0_u8;
        let decisions: Vec<_> = (0..17)
            .map(|_| {
                let decision = victim_scan_decision(hit_count, 16, false, true, true);
                if decision == VictimScanDecision::ApplyHit {
                    hit_count += 1;
                }
                decision
            })
            .collect();
        assert!(
            decisions[..16]
                .iter()
                .all(|decision| *decision == VictimScanDecision::ApplyHit)
        );
        assert_eq!(decisions[16], VictimScanDecision::StopAtLimit);
        assert_eq!(hit_count, 16);

        let rejected = victim_scan_decision(0, 16, false, true, false);
        assert_eq!(rejected, VictimScanDecision::TrackOnly);
        let eligible_later = victim_scan_decision(0, 16, false, true, true);
        assert_eq!(eligible_later, VictimScanDecision::ApplyHit);
    }

    #[test]
    fn area_damage_draw_runs_once_only_after_intersection_and_cooldown_allow_it() {
        let calls = Cell::new(0_u8);
        for decision in [
            VictimScanDecision::TrackOnly,
            VictimScanDecision::SkipAlreadyHit,
            VictimScanDecision::StopAtLimit,
        ] {
            assert!(
                !apply_scan_decision(decision, || {
                    calls.set(calls.get() + 1);
                    Ok(true)
                })
                .unwrap()
            );
        }
        assert_eq!(calls.get(), 0);

        let eligible = victim_scan_decision(0, 16, false, true, true);
        assert!(
            apply_scan_decision(eligible, || {
                calls.set(calls.get() + 1);
                Ok(true)
            })
            .unwrap()
        );
        assert_eq!(calls.get(), 1);

        let same_life = victim_scan_decision(1, 16, true, true, true);
        assert!(
            !apply_scan_decision(same_life, || {
                calls.set(calls.get() + 1);
                Ok(true)
            })
            .unwrap()
        );
        assert_eq!(calls.get(), 1);

        let cooldown_rejected = victim_scan_decision(1, 16, false, true, false);
        assert!(
            !apply_scan_decision(cooldown_rejected, || {
                calls.set(calls.get() + 1);
                Ok(true)
            })
            .unwrap()
        );
        assert_eq!(calls.get(), 1);
        let eligible_later = victim_scan_decision(1, 16, false, true, true);
        assert!(
            apply_scan_decision(eligible_later, || {
                calls.set(calls.get() + 1);
                Ok(true)
            })
            .unwrap()
        );
        assert_eq!(calls.get(), 2);
    }

    #[test]
    fn activation_seed_is_the_previous_sample_for_first_scan_crossing() {
        let radius = 1.9_f64;
        let seeded_at_activation = [-2.0, 0.0, 0.0];
        let first_scan = [2.0, 0.0, 0.0];
        assert!(
            squared_distance_to_segment([0.0, 0.0, 0.0], seeded_at_activation, first_scan)
                <= radius * radius
        );
        assert!(
            squared_distance_to_segment([0.0, 0.0, 0.0], first_scan, first_scan) > radius * radius
        );
    }

    #[test]
    fn local_offsets_rotate_once_at_activation() {
        let zero = rotate(0.0, -1.2, 0.0).unwrap();
        assert!((zero.0 - 0.0).abs() < 0.000_001);
        assert!((zero.1 + 1.2).abs() < 0.000_001);
        let east = rotate(0.0, -1.2, -std::f32::consts::FRAC_PI_2).unwrap();
        assert!((east.0 - 1.2).abs() < 0.000_001);
        assert!(east.1.abs() < 0.000_001);
        assert!(rotate(0.0, -1.2, f32::NAN).is_none());
    }

    #[test]
    fn source_facing_classifies_front_and_back() {
        assert!(is_front_hit(0.0, std::f32::consts::PI));
        assert!(!is_front_hit(0.0, 0.0));
    }

    #[test]
    fn activation_is_exact_late_safe_and_never_scans_its_creation_tick() {
        let activation = 1_666_667;
        let expiry = 1_866_667;
        assert_eq!(
            area_phase(activation - 1, activation, expiry, 0),
            AreaPhase::Waiting
        );
        assert_eq!(
            area_phase(activation, activation, expiry, 0),
            AreaPhase::Activate
        );
        assert_eq!(
            area_phase(activation + 40_000, activation, expiry, 0),
            AreaPhase::Activate
        );
        assert_eq!(
            area_phase(activation + 40_000, activation, expiry, activation + 40_000),
            AreaPhase::ActivatedThisTick
        );
        assert_eq!(
            area_phase(activation + 40_001, activation, expiry, activation + 40_000),
            AreaPhase::Scan
        );
        assert_eq!(
            area_phase(expiry, activation, expiry, 0),
            AreaPhase::Expired
        );
        assert_eq!(
            area_phase(expiry + 1_000_000, activation, expiry, 0),
            AreaPhase::Expired
        );
    }

    #[test]
    fn initial_zero_owner_life_is_valid_but_stale_generations_reject() {
        assert!(owner_life_matches(0, 0));
        assert!(owner_life_matches(7, 7));
        assert!(!owner_life_matches(0, 1));
        assert!(!owner_life_matches(7, 8));
    }
}
