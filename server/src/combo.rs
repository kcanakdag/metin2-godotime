//! Server-owned common one-hand combo prefix and private queued transition state.

use crate::combat::monster;
#[cfg(test)]
use crate::definitions;
use crate::definitions::ComboInputDefinition;
use crate::{Controller, accounts, combat, controller, inventory, player};
use spacetimedb::{Identity, ReducerContext, Table};
use std::cmp::Ordering;

const COMBO_NONE: u8 = 0;
const COMBO_STEP_ONE: u8 = 1;
const COMBO_STEP_TWO: u8 = 2;
const COMBO_STEP_THREE: u8 = 3;
const COMBO_STEP_FOUR: u8 = 4;

const EARLY_ERROR: &str = "Combo follow-up input is too early.";
const DUPLICATE_ERROR: &str = "A combo follow-up is already queued.";
const LATE_ERROR: &str = "Combo follow-up input is too late.";
const BOUNDED_ERROR: &str = "This combo is complete.";
const TARGET_ERROR: &str = "The combo target is no longer available.";
const EQUIPMENT_ERROR: &str = "The combo weapon has changed.";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum FollowUp {
    Queue { boundary_us: i64 },
    Transition,
    Expired,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct DueTransition {
    boundary_us: i64,
    character: Identity,
    chain_revision: u64,
    combo_step: u8,
}

pub struct ChainStart {
    pub action_started_at_us: i64,
    pub action_ends_at_us: i64,
    pub target_id: u32,
    pub target_life_sequence: u32,
    pub target_can_be_selected: bool,
    pub equipped_item_id: u64,
    pub equipped_vnum: u32,
}

fn checked_add(left: i64, right: i64) -> Result<i64, String> {
    left.checked_add(right)
        .ok_or("Combo timestamp is outside the supported range.".into())
}

fn classify_follow_up(
    now: i64,
    action_started_at_us: i64,
    action_ends_at_us: i64,
    queued: bool,
    input: ComboInputDefinition,
) -> Result<FollowUp, String> {
    // `link_us` is retained as normalized source evidence. The server schedules
    // only from the reviewed direct-input boundary.
    let _source_link_evidence_us = input.link_us;
    if now >= action_ends_at_us {
        return Ok(FollowUp::Expired);
    }
    let elapsed = now
        .checked_sub(action_started_at_us)
        .ok_or("Combo timestamp is outside the supported range.")?;
    if elapsed < 0 {
        return Err("Combo action has not started.".into());
    }
    if queued {
        return Err(DUPLICATE_ERROR.into());
    }
    if elapsed <= input.pre_input_us {
        return Err(EARLY_ERROR.into());
    }
    if elapsed <= input.direct_input_us {
        return Ok(FollowUp::Queue {
            boundary_us: checked_add(action_started_at_us, input.direct_input_us)?,
        });
    }
    if elapsed <= input.input_limit_us {
        return Ok(FollowUp::Transition);
    }
    Err(LATE_ERROR.into())
}

fn transition_is_due(now: i64, boundary_us: i64) -> bool {
    now > boundary_us
}

fn compare_due_transitions(left: &DueTransition, right: &DueTransition) -> Ordering {
    left.boundary_us
        .cmp(&right.boundary_us)
        .then_with(|| left.character.to_string().cmp(&right.character.to_string()))
}

pub fn clear_chain(control: &mut Controller) {
    control.combo_step = COMBO_NONE;
    control.combo_action_started_at_us = 0;
    control.combo_action_ends_at_us = 0;
    control.combo_target_id = 0;
    control.combo_target_life_sequence = 0;
    control.combo_target_can_be_selected = false;
    control.combo_equipped_item_id = 0;
    control.combo_equipped_vnum = 0;
    cancel_queued_link(control);
}

pub fn cancel_queued_link(control: &mut Controller) {
    control.combo_link_queued = false;
    control.combo_transition_boundary_us = 0;
}

fn store_queued_link(control: &mut Controller, boundary_us: i64) {
    control.combo_link_queued = true;
    control.combo_transition_boundary_us = boundary_us;
}

pub fn cancel_queued_link_for_character(ctx: &ReducerContext, character: Identity) {
    let Some(mut control) = ctx.db.controller().identity().find(character) else {
        return;
    };
    if !control.combo_link_queued {
        return;
    }
    cancel_queued_link(&mut control);
    ctx.db.controller().identity().update(control);
}

pub fn clear_chains_targeting(ctx: &ReducerContext, target_id: u32, target_life_sequence: u32) {
    let characters: Vec<_> = ctx
        .db
        .controller()
        .iter()
        .filter(|control| {
            control.combo_step != COMBO_NONE
                && control.combo_target_id == target_id
                && control.combo_target_life_sequence == target_life_sequence
        })
        .map(|control| control.identity)
        .collect();
    for character in characters {
        let Some(mut control) = ctx.db.controller().identity().find(character) else {
            continue;
        };
        clear_chain(&mut control);
        ctx.db.controller().identity().update(control);
    }
}

pub fn begin_chain(control: &mut Controller, start: ChainStart) -> Result<(), String> {
    let revision = control
        .combo_chain_revision
        .checked_add(1)
        .ok_or("Combo chain revision limit reached.")?;
    clear_chain(control);
    control.combo_chain_revision = revision;
    control.combo_step = COMBO_STEP_ONE;
    control.combo_action_started_at_us = start.action_started_at_us;
    control.combo_action_ends_at_us = start.action_ends_at_us;
    control.combo_target_id = start.target_id;
    control.combo_target_life_sequence = start.target_life_sequence;
    control.combo_target_can_be_selected = start.target_can_be_selected;
    control.combo_equipped_item_id = start.equipped_item_id;
    control.combo_equipped_vnum = start.equipped_vnum;
    Ok(())
}

fn live_chain_target(ctx: &ReducerContext, control: &Controller) -> bool {
    control.combo_target_id != 0
        && ctx
            .db
            .monster()
            .id()
            .find(control.combo_target_id)
            .is_some_and(|target| {
                target.life_sequence == control.combo_target_life_sequence && target.health > 0
            })
}

fn equipment_matches(ctx: &ReducerContext, control: &Controller) -> bool {
    inventory::equipped_weapon_item(ctx, control.identity)
        == Some((control.combo_equipped_item_id, control.combo_equipped_vnum))
}

fn chain_target_relationship_is_valid(control: &Controller, target_is_live: bool) -> bool {
    if control.combo_target_id == 0 {
        return control.combat_target_id == 0 && control.combat_target_life_sequence == 0;
    }
    if !target_is_live {
        return false;
    }
    if control.combat_target_id == control.combo_target_id
        && control.combat_target_life_sequence == control.combo_target_life_sequence
    {
        return true;
    }
    control.combo_target_can_be_selected
        && control.combat_target_id == 0
        && control.combat_target_life_sequence == 0
}

fn chain_target_is_valid(ctx: &ReducerContext, control: &Controller) -> bool {
    chain_target_relationship_is_valid(control, live_chain_target(ctx, control))
}

fn transition_is_valid(ctx: &ReducerContext, control: &Controller) -> Result<(), String> {
    let player_is_active = ctx
        .db
        .player()
        .identity()
        .find(control.identity)
        .is_some_and(|row| row.online && row.health > 0);
    if !player_is_active
        || !accounts::controller_has_active_lease(ctx, control)
        || !chain_target_is_valid(ctx, control)
    {
        return Err(TARGET_ERROR.into());
    }
    if !equipment_matches(ctx, control) {
        return Err(EQUIPMENT_ERROR.into());
    }
    Ok(())
}

fn transition_to_next_step(
    ctx: &ReducerContext,
    control: &mut Controller,
    now: i64,
) -> Result<(), String> {
    let next_step = control
        .combo_step
        .checked_add(1)
        .ok_or("Combo step is outside the supported range.")?;
    if next_step > COMBO_STEP_FOUR {
        return Err(BOUNDED_ERROR.into());
    }
    let definition = crate::characters::combo_step(
        ctx,
        control.identity,
        control.combo_equipped_vnum,
        next_step,
    )?;
    transition_is_valid(ctx, control)?;
    combat::discard_expired_player_hit(control, now);
    if control.pending_attack_hit_at_us != 0 {
        return Err("The current captured hit must resolve before the combo advances.".into());
    }
    let target = if control.combo_target_id == 0 {
        None
    } else {
        Some(
            ctx.db
                .monster()
                .id()
                .find(control.combo_target_id)
                .ok_or(TARGET_ERROR)?,
        )
    };
    combat::validate_player_action_start(ctx, control, definition, target.is_some(), now)?;
    // All state-dependent scheduled-transition rejection paths are resolved
    // before this physical sample. The remaining start checks repeat trusted
    // definition and checked timestamp/revision invariants atomically.
    crate::root_motion::advance_for_replacement(ctx, control, now)?;
    let player = ctx
        .db
        .player()
        .identity()
        .find(control.identity)
        .ok_or("Enter the world first.")?;
    let can_select_target = control.combo_target_can_be_selected
        && control.combat_target_id == 0
        && control.combat_target_life_sequence == 0
        && target.is_some();
    let plan = combat::PlayerAttackPlan {
        definition,
        target_id: control.combo_target_id,
        target_generation: control.combo_target_life_sequence,
        heading: target.map(|target| (player.x - target.x).atan2(player.z - target.z)),
        can_select_target,
    };
    combat::start_player_action(ctx, control, plan, now)?;
    control.combo_step = next_step;
    control.combo_action_started_at_us = now;
    control.combo_action_ends_at_us = control.attack_until_us;
    cancel_queued_link(control);
    Ok(())
}

/// Handle an active combo intent. `Ok(false)` means the expired/idle chain may
/// proceed through the ordinary fresh-attack path.
pub fn handle_follow_up(
    ctx: &ReducerContext,
    control: &mut Controller,
    now: i64,
) -> Result<bool, String> {
    match control.combo_step {
        COMBO_NONE => return Ok(false),
        COMBO_STEP_FOUR => {
            if now >= control.combo_action_ends_at_us {
                clear_chain(control);
                return Ok(false);
            }
            return Err(BOUNDED_ERROR.into());
        }
        COMBO_STEP_ONE | COMBO_STEP_TWO | COMBO_STEP_THREE => {}
        _ => return Err("Combo chain state is invalid.".into()),
    }
    let input = crate::characters::combo_step(
        ctx,
        control.identity,
        control.combo_equipped_vnum,
        control.combo_step,
    )?
    .combo_input
    .ok_or("The trusted combo step has no input timing.")?;
    let input = crate::attack_timing::combo_input(input, control.attack_speed_percent)?;
    match classify_follow_up(
        now,
        control.combo_action_started_at_us,
        control.combo_action_ends_at_us,
        control.combo_link_queued,
        input,
    )? {
        FollowUp::Expired => {
            clear_chain(control);
            Ok(false)
        }
        FollowUp::Queue { boundary_us } => {
            if !equipment_matches(ctx, control) {
                return Err(EQUIPMENT_ERROR.into());
            }
            if !chain_target_is_valid(ctx, control) {
                return Err(TARGET_ERROR.into());
            }
            store_queued_link(control, boundary_us);
            Ok(true)
        }
        FollowUp::Transition => {
            transition_to_next_step(ctx, control, now)?;
            Ok(true)
        }
    }
}

pub fn resolve_due_transitions(ctx: &ReducerContext, now: i64) {
    let mut events = Vec::new();
    for mut control in ctx.db.controller().iter() {
        if control.combo_step != COMBO_NONE && now >= control.combo_action_ends_at_us {
            clear_chain(&mut control);
            ctx.db.controller().identity().update(control);
            continue;
        }
        if matches!(
            control.combo_step,
            COMBO_STEP_ONE | COMBO_STEP_TWO | COMBO_STEP_THREE
        ) && control.combo_link_queued
            && transition_is_due(now, control.combo_transition_boundary_us)
        {
            events.push(DueTransition {
                boundary_us: control.combo_transition_boundary_us,
                character: control.identity,
                chain_revision: control.combo_chain_revision,
                combo_step: control.combo_step,
            });
        }
    }
    events.sort_by(compare_due_transitions);
    for event in events {
        let Some(mut control) = ctx.db.controller().identity().find(event.character) else {
            continue;
        };
        if control.combo_step != event.combo_step
            || !control.combo_link_queued
            || control.combo_transition_boundary_us != event.boundary_us
            || control.combo_chain_revision != event.chain_revision
            || !transition_is_due(now, event.boundary_us)
        {
            continue;
        }
        if now >= control.combo_action_ends_at_us {
            clear_chain(&mut control);
        } else if transition_to_next_step(ctx, &mut control, now).is_err() {
            cancel_queued_link(&mut control);
        }
        ctx.db.controller().identity().update(control);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use spacetimedb::ConnectionId;

    fn first_input() -> ComboInputDefinition {
        definitions::PLAYER_ONEHAND_COMBO[0]
            .combo_input
            .expect("generated first combo input")
    }

    #[test]
    fn sped_up_windows_keep_early_queue_direct_and_late_rejections() {
        for action in crate::characters::root_actions() {
            let Some(original) = action.combo_input else {
                continue;
            };
            for speed in [100, 122, 126, 170] {
                let input = crate::attack_timing::combo_input(original, speed).unwrap();
                let start = 1_000_000;
                let end =
                    start + crate::attack_timing::scaled_us(action.duration_us, speed).unwrap();
                assert_eq!(
                    classify_follow_up(start + input.pre_input_us, start, end, false, input)
                        .unwrap_err(),
                    EARLY_ERROR
                );
                assert_eq!(
                    classify_follow_up(start + input.pre_input_us + 1, start, end, false, input)
                        .unwrap(),
                    FollowUp::Queue {
                        boundary_us: start + input.direct_input_us
                    }
                );
                assert_eq!(
                    classify_follow_up(start + input.direct_input_us + 1, start, end, false, input)
                        .unwrap(),
                    FollowUp::Transition
                );
                let after_limit = start + input.input_limit_us + 1;
                let late = classify_follow_up(after_limit, start, end, false, input);
                if after_limit >= end {
                    assert_eq!(late.unwrap(), FollowUp::Expired);
                } else {
                    assert_eq!(late.unwrap_err(), LATE_ERROR);
                }
            }
        }
    }

    #[test]
    fn exact_follow_up_boundaries_are_source_generated() {
        let expected = [
            (167_094, 533_333, 602_564, 58_889),
            (100_513, 543_248, 636_581, 19_658),
            (84_786, 418_462, 664_615, 60_171),
        ];
        for (index, expected_input) in expected.into_iter().enumerate() {
            let input = definitions::PLAYER_ONEHAND_COMBO[index]
                .combo_input
                .expect("generated combo input");
            assert_eq!(
                (
                    input.pre_input_us,
                    input.direct_input_us,
                    input.input_limit_us,
                    input.link_us,
                ),
                expected_input
            );
            let start = 1_000_000;
            let end = start + definitions::PLAYER_ONEHAND_COMBO[index].duration_us;
            assert_eq!(
                classify_follow_up(start + input.pre_input_us, start, end, false, input)
                    .unwrap_err(),
                EARLY_ERROR
            );
            assert_eq!(
                classify_follow_up(start + input.pre_input_us + 1, start, end, false, input)
                    .unwrap(),
                FollowUp::Queue {
                    boundary_us: start + input.direct_input_us
                }
            );
            assert!(matches!(
                classify_follow_up(start + input.direct_input_us, start, end, false, input)
                    .unwrap(),
                FollowUp::Queue { .. }
            ));
            assert_eq!(
                classify_follow_up(start + input.direct_input_us + 1, start, end, false, input,)
                    .unwrap(),
                FollowUp::Transition
            );
            assert_eq!(
                classify_follow_up(start + input.input_limit_us, start, end, false, input,)
                    .unwrap(),
                FollowUp::Transition
            );
            assert_eq!(
                classify_follow_up(start + input.input_limit_us + 1, start, end, false, input,)
                    .unwrap_err(),
                LATE_ERROR
            );
            assert_eq!(
                classify_follow_up(end, start, end, false, input).unwrap(),
                FollowUp::Expired
            );
        }
    }

    #[test]
    fn duplicate_preserves_the_original_queue_through_direct_time() {
        let input = first_input();
        let start = 1_000_000;
        let end = start + definitions::PLAYER_ONEHAND_COMBO[0].duration_us;
        for elapsed in [
            input.pre_input_us + 1,
            input.direct_input_us,
            input.direct_input_us + 1,
        ] {
            assert_eq!(
                classify_follow_up(start + elapsed, start, end, true, input).unwrap_err(),
                DUPLICATE_ERROR
            );
        }
    }

    #[test]
    fn queued_transition_uses_strict_tick_boundary() {
        let input = first_input();
        let boundary = 1_000_000 + input.direct_input_us;
        assert!(!transition_is_due(boundary - 1, boundary));
        assert!(!transition_is_due(boundary, boundary));
        assert!(transition_is_due(boundary + 1, boundary));
    }

    #[test]
    fn checked_timestamp_rejects_overflow() {
        assert_eq!(checked_add(4, 7).unwrap(), 11);
        assert!(checked_add(i64::MAX, 1).is_err());
    }

    fn active_combo_controller() -> Controller {
        Controller {
            identity: Identity::from_claims("combo-test", "character"),
            connection_id: ConnectionId::from_u128(7),
            direction_x: 0.25,
            direction_z: -0.5,
            target_x: 12.0,
            target_z: 34.0,
            mode: 2,
            last_input_us: 900,
            attack_until_us: 2_000,
            attack_speed_percent: 100,
            next_attack_us: 1_850,
            action_revision: 9,
            pending_attack_target_id: 3,
            pending_attack_target_generation: 4,
            pending_attack_source_generation: 2,
            pending_attack_hit_at_us: 1_192,
            pending_attack_hit_until_us: 1_384,
            pending_attack_damage: 35,
            pending_attack_range: 4.0,
            pending_attack_invulnerability_us: 100_000,
            pending_attack_target_revision: 8,
            pending_attack_can_select_target: false,
            pending_attack_action_revision: 9,
            combat_target_id: 3,
            combat_target_life_sequence: 4,
            combat_target_change_not_before_us: 1_100,
            combat_target_revision: 8,
            combo_step: COMBO_STEP_ONE,
            combo_chain_revision: 5,
            combo_action_started_at_us: 1_000,
            combo_action_ends_at_us: 2_000,
            combo_target_id: 3,
            combo_target_life_sequence: 4,
            combo_target_can_be_selected: false,
            combo_equipped_item_id: 11,
            combo_equipped_vnum: 19,
            combo_link_queued: true,
            combo_transition_boundary_us: 1_533,
            root_motion_step: COMBO_STEP_ONE,
            root_motion_action_revision: 9,
            root_motion_started_at_us: 1_000,
            root_motion_consumed_elapsed_us: 150,
            root_motion_heading: 0.75,
            next_chat_us: 0,
        }
    }

    #[test]
    fn cancelling_link_preserves_captured_hit_chain_and_locomotion_intent() {
        let mut control = active_combo_controller();
        let pending = (
            control.action_revision,
            control.pending_attack_target_id,
            control.pending_attack_target_generation,
            control.pending_attack_source_generation,
            control.pending_attack_hit_at_us,
            control.pending_attack_hit_until_us,
            control.pending_attack_damage,
            control.pending_attack_range,
            control.pending_attack_invulnerability_us,
            control.pending_attack_target_revision,
            control.pending_attack_can_select_target,
            control.pending_attack_action_revision,
        );
        let locomotion = (
            control.mode,
            control.direction_x,
            control.direction_z,
            control.target_x,
            control.target_z,
            control.attack_until_us,
        );
        let chain = (
            control.combo_step,
            control.combo_chain_revision,
            control.combo_action_started_at_us,
            control.combo_action_ends_at_us,
            control.combo_target_id,
            control.combo_target_life_sequence,
            control.combo_equipped_item_id,
            control.combo_equipped_vnum,
        );
        let root = (
            control.root_motion_step,
            control.root_motion_action_revision,
            control.root_motion_started_at_us,
            control.root_motion_consumed_elapsed_us,
            control.root_motion_heading,
        );

        cancel_queued_link(&mut control);

        assert!(!control.combo_link_queued);
        assert_eq!(control.combo_transition_boundary_us, 0);
        assert_eq!(
            pending,
            (
                control.action_revision,
                control.pending_attack_target_id,
                control.pending_attack_target_generation,
                control.pending_attack_source_generation,
                control.pending_attack_hit_at_us,
                control.pending_attack_hit_until_us,
                control.pending_attack_damage,
                control.pending_attack_range,
                control.pending_attack_invulnerability_us,
                control.pending_attack_target_revision,
                control.pending_attack_can_select_target,
                control.pending_attack_action_revision,
            )
        );
        assert_eq!(
            locomotion,
            (
                control.mode,
                control.direction_x,
                control.direction_z,
                control.target_x,
                control.target_z,
                control.attack_until_us,
            )
        );
        assert_eq!(
            chain,
            (
                control.combo_step,
                control.combo_chain_revision,
                control.combo_action_started_at_us,
                control.combo_action_ends_at_us,
                control.combo_target_id,
                control.combo_target_life_sequence,
                control.combo_equipped_item_id,
                control.combo_equipped_vnum,
            )
        );
        assert_eq!(
            root,
            (
                control.root_motion_step,
                control.root_motion_action_revision,
                control.root_motion_started_at_us,
                control.root_motion_consumed_elapsed_us,
                control.root_motion_heading,
            )
        );
    }

    #[test]
    fn queue_receipt_only_records_boundary_and_preserves_captured_formula_outcome() {
        let mut control = active_combo_controller();
        control.combo_link_queued = false;
        control.combo_transition_boundary_us = 0;
        let captured = (
            control.pending_attack_source_generation,
            control.pending_attack_target_id,
            control.pending_attack_target_generation,
            control.pending_attack_damage,
            control.pending_attack_action_revision,
        );
        store_queued_link(&mut control, 9_999);
        assert!(control.combo_link_queued);
        assert_eq!(control.combo_transition_boundary_us, 9_999);
        assert_eq!(
            captured,
            (
                control.pending_attack_source_generation,
                control.pending_attack_target_id,
                control.pending_attack_target_generation,
                control.pending_attack_damage,
                control.pending_attack_action_revision,
            )
        );
    }

    #[test]
    fn clearing_chain_preserves_current_pending_hit_and_movement_window() {
        let mut control = active_combo_controller();
        clear_chain(&mut control);
        assert_eq!(control.combo_step, COMBO_NONE);
        assert_eq!(control.combo_chain_revision, 5);
        assert!(!control.combo_link_queued);
        assert_eq!(control.pending_attack_action_revision, 9);
        assert_eq!(control.pending_attack_hit_at_us, 1_192);
        assert_eq!(control.pending_attack_damage, 35);
        assert_eq!(control.attack_until_us, 2_000);
        assert_eq!(control.mode, 2);
        assert_eq!((control.target_x, control.target_z), (12.0, 34.0));
        assert_eq!(control.root_motion_step, COMBO_STEP_ONE);
        assert_eq!(control.root_motion_action_revision, 9);
        assert_eq!(control.root_motion_started_at_us, 1_000);
        assert_eq!(control.root_motion_consumed_elapsed_us, 150);
        assert_eq!(control.root_motion_heading, 0.75);
    }

    #[test]
    fn chain_revision_is_checked_without_rewriting_current_hit() {
        let mut control = active_combo_controller();
        control.combo_chain_revision = u64::MAX;
        let before_hit = (
            control.pending_attack_action_revision,
            control.pending_attack_hit_at_us,
            control.pending_attack_damage,
        );
        assert!(
            begin_chain(
                &mut control,
                ChainStart {
                    action_started_at_us: 5,
                    action_ends_at_us: 9,
                    target_id: 3,
                    target_life_sequence: 4,
                    target_can_be_selected: false,
                    equipped_item_id: 11,
                    equipped_vnum: 19,
                },
            )
            .is_err()
        );
        assert_eq!(
            before_hit,
            (
                control.pending_attack_action_revision,
                control.pending_attack_hit_at_us,
                control.pending_attack_damage,
            )
        );
    }

    #[test]
    fn targetless_and_fallback_chains_never_replan_to_a_new_selection() {
        let mut control = active_combo_controller();
        control.combo_target_id = 0;
        control.combo_target_life_sequence = 0;
        control.combat_target_id = 0;
        control.combat_target_life_sequence = 0;
        assert!(chain_target_relationship_is_valid(&control, false));
        control.combat_target_id = 3;
        control.combat_target_life_sequence = 4;
        assert!(!chain_target_relationship_is_valid(&control, true));

        control.combo_target_id = 3;
        control.combo_target_life_sequence = 4;
        control.combat_target_id = 0;
        control.combat_target_life_sequence = 0;
        control.combo_target_can_be_selected = true;
        assert!(chain_target_relationship_is_valid(&control, true));
        assert!(!chain_target_relationship_is_valid(&control, false));

        control.combat_target_id = 8;
        control.combat_target_life_sequence = 9;
        assert!(!chain_target_relationship_is_valid(&control, true));
        control.combat_target_id = 3;
        control.combat_target_life_sequence = 5;
        assert!(!chain_target_relationship_is_valid(&control, true));
        control.combat_target_life_sequence = 4;
        assert!(chain_target_relationship_is_valid(&control, true));
    }

    #[test]
    fn targetless_terminal_area_is_the_only_step_without_an_ordinary_trace_hit() {
        let terminal = &definitions::PLAYER_ONEHAND_COMBO[3];
        assert!(terminal.special_area.is_some());
        assert!(terminal.ordinary_hit_invulnerability_us == 0);
        assert!(
            definitions::PLAYER_ONEHAND_COMBO[..3]
                .iter()
                .all(|definition| definition.special_area.is_none()
                    && definition.ordinary_hit_invulnerability_us > 0)
        );
    }
}
