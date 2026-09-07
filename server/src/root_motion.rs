//! Server-owned linear root-displacement approximation for selected combo actions.

use crate::definitions::{self, AttackDefinition, RootMotionDefinition};
use crate::{Controller, accounts, collision_bounds, content, controller, player};
use spacetimedb::{Identity, ReducerContext, Table};

const ROOT_SUBSTEP_US: i64 = 50_000;
const MAX_ROOT_SUBSTEPS: usize = 32;
const MAX_ROOT_DURATION_US: i64 = ROOT_SUBSTEP_US * MAX_ROOT_SUBSTEPS as i64;
const MAX_ROOT_ENDPOINT_M: f64 = 2.0;

fn valid_definition(root: RootMotionDefinition) -> bool {
    (1..=MAX_ROOT_DURATION_US).contains(&root.duration_us)
        && root.endpoint_x_m.is_finite()
        && root.endpoint_x_m.abs() <= MAX_ROOT_ENDPOINT_M
        && root.endpoint_z_m.is_finite()
        && root.endpoint_z_m.abs() <= MAX_ROOT_ENDPOINT_M
}

fn cumulative(root: RootMotionDefinition, elapsed_us: i64) -> Option<(f64, f64)> {
    if !valid_definition(root) {
        return None;
    }
    let elapsed = elapsed_us.clamp(0, root.duration_us) as f64;
    let fraction = elapsed / root.duration_us as f64;
    Some((root.endpoint_x_m * fraction, root.endpoint_z_m * fraction))
}

fn rotated_delta(local_x: f64, local_z: f64, heading: f32) -> Option<(f32, f32)> {
    if !local_x.is_finite() || !local_z.is_finite() || !heading.is_finite() {
        return None;
    }
    let heading = f64::from(heading);
    let (sin, cos) = heading.sin_cos();
    let world_x = cos * local_x + sin * local_z;
    let world_z = -sin * local_x + cos * local_z;
    if !world_x.is_finite() || !world_z.is_finite() {
        return None;
    }
    let delta = (world_x as f32, world_z as f32);
    (delta.0.is_finite() && delta.1.is_finite()).then_some(delta)
}

fn definition_for_step(step: u8) -> Option<&'static AttackDefinition> {
    let index = usize::from(step.checked_sub(1)?);
    definitions::PLAYER_ONEHAND_COMBO.get(index)
}

fn simulation_target_elapsed(raw_elapsed_us: i64, duration_us: i64) -> i64 {
    let clamped = raw_elapsed_us.clamp(0, duration_us);
    if clamped == duration_us {
        duration_us
    } else {
        clamped / ROOT_SUBSTEP_US * ROOT_SUBSTEP_US
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Advance {
    x: f32,
    z: f32,
    consumed_elapsed_us: i64,
    substeps: usize,
}

fn advance_position(
    root: RootMotionDefinition,
    heading: f32,
    x: f32,
    z: f32,
    consumed_elapsed_us: i64,
    target_elapsed_us: i64,
    bounds: &[crate::movement::Bounds],
) -> Result<Advance, String> {
    if !valid_definition(root)
        || !heading.is_finite()
        || !x.is_finite()
        || !z.is_finite()
        || consumed_elapsed_us < 0
        || consumed_elapsed_us > root.duration_us
        || target_elapsed_us < consumed_elapsed_us
        || target_elapsed_us > root.duration_us
    {
        return Err("Root-motion advancement state is invalid.".into());
    }

    let mut position = (x, z);
    let mut cursor = consumed_elapsed_us;
    let mut substeps = 0_usize;
    while cursor < target_elapsed_us {
        if substeps >= MAX_ROOT_SUBSTEPS {
            return Err("Root-motion advancement exceeds its bounded substep count.".into());
        }
        let next_boundary = cursor
            .checked_div(ROOT_SUBSTEP_US)
            .and_then(|bucket| bucket.checked_add(1))
            .and_then(|bucket| bucket.checked_mul(ROOT_SUBSTEP_US))
            .ok_or("Root-motion timestamp is outside the supported range.")?;
        let next = next_boundary.min(target_elapsed_us);
        let before =
            cumulative(root, cursor).ok_or("The trusted root-motion definition is invalid.")?;
        let after =
            cumulative(root, next).ok_or("The trusted root-motion definition is invalid.")?;
        let (dx, dz) = rotated_delta(after.0 - before.0, after.1 - before.1, heading)
            .ok_or("Root-motion displacement is invalid.")?;
        position = content::slide(position.0, position.1, dx, dz, bounds);
        cursor = next;
        substeps += 1;
    }
    Ok(Advance {
        x: position.0,
        z: position.1,
        consumed_elapsed_us: cursor,
        substeps,
    })
}

pub fn clear(control: &mut Controller) {
    control.root_motion_step = 0;
    control.root_motion_action_revision = 0;
    control.root_motion_started_at_us = 0;
    control.root_motion_consumed_elapsed_us = 0;
    control.root_motion_heading = 0.0;
}

/// Return the server-planned facing for the currently active root action.
/// Hit resolution uses this capture rather than turning the public actor while
/// its accepted trajectory is still advancing on the original heading.
fn active_action_heading_state(
    step: u8,
    root_revision: u64,
    action_revision: u64,
    started_at_us: i64,
    consumed_elapsed_us: i64,
    heading: f32,
) -> Option<f32> {
    let definition = definition_for_step(step)?;
    let root = definition.root_motion?;
    (valid_definition(root)
        && root.duration_us == definition.duration_us
        && root_revision != 0
        && root_revision == action_revision
        && started_at_us > 0
        && (0..root.duration_us).contains(&consumed_elapsed_us)
        && heading.is_finite())
    .then_some(heading)
}

pub(crate) fn active_action_heading(control: &Controller) -> Option<f32> {
    active_action_heading_state(
        control.root_motion_step,
        control.root_motion_action_revision,
        control.action_revision,
        control.root_motion_started_at_us,
        control.root_motion_consumed_elapsed_us,
        control.root_motion_heading,
    )
}

pub fn validate_action_definition(definition: &AttackDefinition) -> Result<(), String> {
    let Some(root) = definition.root_motion else {
        return Ok(());
    };
    if !valid_definition(root) || root.duration_us != definition.duration_us {
        return Err("The trusted root-motion definition is invalid.".into());
    }
    if !definitions::PLAYER_ONEHAND_COMBO
        .iter()
        .any(|candidate| candidate.id == definition.id)
    {
        return Err("Root motion is limited to the trusted combo prefix.".into());
    }
    Ok(())
}

pub fn start(
    control: &mut Controller,
    definition: &'static AttackDefinition,
    now: i64,
    heading: f32,
    action_revision: u64,
) -> Result<(), String> {
    validate_action_definition(definition)?;
    if !heading.is_finite() {
        return Err("The server action heading is invalid.".into());
    }
    clear(control);
    let Some(_root) = definition.root_motion else {
        return Ok(());
    };
    let index = definitions::PLAYER_ONEHAND_COMBO
        .iter()
        .position(|candidate| candidate.id == definition.id)
        .expect("the root-motion definition was validated against the trusted prefix");
    control.root_motion_step = u8::try_from(index + 1)
        .map_err(|_| "The trusted root-motion step is outside the supported range.")?;
    control.root_motion_action_revision = action_revision;
    control.root_motion_started_at_us = now;
    control.root_motion_consumed_elapsed_us = 0;
    control.root_motion_heading = heading;
    Ok(())
}

fn advance_character(
    ctx: &ReducerContext,
    control: &mut Controller,
    through_us: i64,
    flush_partial: bool,
) -> Result<(), String> {
    if control.root_motion_step == 0 {
        return Ok(());
    }
    let Some(definition) = definition_for_step(control.root_motion_step) else {
        clear(control);
        return Ok(());
    };
    let Some(root) = definition.root_motion else {
        clear(control);
        return Ok(());
    };
    if !valid_definition(root)
        || root.duration_us != definition.duration_us
        || control.root_motion_action_revision == 0
        || control.root_motion_action_revision != control.action_revision
        || !control.root_motion_heading.is_finite()
        || control.root_motion_started_at_us <= 0
        || control.root_motion_consumed_elapsed_us < 0
        || control.root_motion_consumed_elapsed_us > root.duration_us
    {
        clear(control);
        return Ok(());
    }
    let Some(mut player) = ctx.db.player().identity().find(control.identity) else {
        clear(control);
        return Ok(());
    };
    if !player.online || player.health == 0 {
        clear(control);
        return Ok(());
    }
    let Some(raw_elapsed) = through_us.checked_sub(control.root_motion_started_at_us) else {
        clear(control);
        return Ok(());
    };
    if raw_elapsed < 0 {
        clear(control);
        return Ok(());
    }
    let raw_target_elapsed = raw_elapsed.min(root.duration_us);
    let target_elapsed = if flush_partial {
        raw_target_elapsed
    } else {
        simulation_target_elapsed(raw_target_elapsed, root.duration_us)
    };
    if target_elapsed <= control.root_motion_consumed_elapsed_us {
        if target_elapsed == root.duration_us {
            clear(control);
        }
        return Ok(());
    }

    let advance = advance_position(
        root,
        control.root_motion_heading,
        player.x,
        player.z,
        control.root_motion_consumed_elapsed_us,
        target_elapsed,
        &collision_bounds(ctx),
    )?;
    player.x = advance.x;
    player.z = advance.z;
    player.y = content::height(advance.x, advance.z);
    control.root_motion_consumed_elapsed_us = advance.consumed_elapsed_us;
    ctx.db.player().identity().update(player);
    if target_elapsed == root.duration_us {
        clear(control);
    }
    Ok(())
}

/// Consume the outgoing action through an accepted replacement's actual server
/// time. Queue-only intents never call this path.
pub fn advance_for_replacement(
    ctx: &ReducerContext,
    control: &mut Controller,
    through_us: i64,
) -> Result<(), String> {
    advance_character(ctx, control, through_us, true)
}

pub fn advance_all(ctx: &ReducerContext, now: i64) -> Result<(), String> {
    let mut identities: Vec<Identity> = ctx
        .db
        .controller()
        .iter()
        .filter(|control| control.root_motion_step != 0)
        .map(|control| control.identity)
        .collect();
    identities.sort_by_key(|identity| identity.to_string());
    for identity in identities {
        let Some(mut control) = ctx.db.controller().identity().find(identity) else {
            continue;
        };
        if !accounts::controller_has_active_lease(ctx, &control) {
            clear(&mut control);
        } else {
            advance_character(ctx, &mut control, now, false)?;
        }
        ctx.db.controller().identity().update(control);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROOT: RootMotionDefinition = RootMotionDefinition {
        endpoint_x_m: 0.0,
        endpoint_z_m: -1.317_569_580_078_125,
        duration_us: 1_000_000,
    };

    #[test]
    fn cumulative_linear_fraction_clamps_and_repeats() {
        assert_eq!(cumulative(ROOT, -1), Some((0.0, 0.0)));
        assert_eq!(cumulative(ROOT, 0), Some((0.0, 0.0)));
        assert_eq!(
            cumulative(ROOT, 500_000),
            Some((0.0, ROOT.endpoint_z_m / 2.0))
        );
        assert_eq!(cumulative(ROOT, 1_000_000), Some((0.0, ROOT.endpoint_z_m)));
        assert_eq!(cumulative(ROOT, i64::MAX), Some((0.0, ROOT.endpoint_z_m)));
    }

    #[test]
    fn invalid_root_definitions_fail_closed() {
        for root in [
            RootMotionDefinition {
                duration_us: 0,
                ..ROOT
            },
            RootMotionDefinition {
                endpoint_x_m: f64::NAN,
                ..ROOT
            },
            RootMotionDefinition {
                endpoint_z_m: f64::INFINITY,
                ..ROOT
            },
            RootMotionDefinition {
                duration_us: MAX_ROOT_DURATION_US + 1,
                ..ROOT
            },
            RootMotionDefinition {
                endpoint_z_m: MAX_ROOT_ENDPOINT_M + 0.001,
                ..ROOT
            },
        ] {
            assert_eq!(cumulative(root, 1), None);
        }
    }

    #[test]
    fn active_action_heading_requires_current_finite_root_state() {
        assert_eq!(
            active_action_heading_state(1, 20, 20, 1_000_000, 150_000, 0.75),
            Some(0.75)
        );
        assert_eq!(
            active_action_heading_state(1, 19, 20, 1_000_000, 150_000, 0.75),
            None
        );
        assert_eq!(
            active_action_heading_state(1, 20, 20, 1_000_000, 150_000, f32::NAN),
            None
        );
        assert_eq!(
            active_action_heading_state(0, 20, 20, 1_000_000, 150_000, 0.75),
            None
        );
    }

    #[test]
    fn heading_rotation_uses_existing_player_convention() {
        let forward = (0.0, -1.0);
        let cases = [
            (0.0, (0.0, -1.0)),
            (-std::f32::consts::FRAC_PI_2, (1.0, 0.0)),
            (std::f32::consts::FRAC_PI_2, (-1.0, 0.0)),
            (std::f32::consts::PI, (0.0, 1.0)),
        ];
        for (heading, expected) in cases {
            let actual = rotated_delta(forward.0, forward.1, heading).unwrap();
            assert!((actual.0 - expected.0).abs() < 0.000_001);
            assert!((actual.1 - expected.1).abs() < 0.000_001);
        }
    }

    fn run_simulation_schedule(raw_elapsed_samples: &[i64]) -> Advance {
        let mut state = Advance {
            x: content::SPAWN.0,
            z: content::SPAWN.1,
            consumed_elapsed_us: 0,
            substeps: 0,
        };
        for raw_elapsed in raw_elapsed_samples {
            let target = simulation_target_elapsed(*raw_elapsed, ROOT.duration_us);
            let next = advance_position(
                ROOT,
                -std::f32::consts::FRAC_PI_2,
                state.x,
                state.z,
                state.consumed_elapsed_us,
                target,
                &[],
            )
            .unwrap();
            state = Advance {
                substeps: state.substeps + next.substeps,
                ..next
            };
        }
        state
    }

    #[test]
    fn simulation_samples_only_action_relative_quanta_and_terminal_remainder() {
        assert_eq!(simulation_target_elapsed(0, ROOT.duration_us), 0);
        assert_eq!(simulation_target_elapsed(1, ROOT.duration_us), 0);
        assert_eq!(simulation_target_elapsed(49_999, ROOT.duration_us), 0);
        assert_eq!(simulation_target_elapsed(50_000, ROOT.duration_us), 50_000);
        assert_eq!(
            simulation_target_elapsed(987_654, ROOT.duration_us),
            950_000
        );
        assert_eq!(
            simulation_target_elapsed(ROOT.duration_us, ROOT.duration_us),
            ROOT.duration_us
        );
        assert_eq!(
            simulation_target_elapsed(i64::MAX, ROOT.duration_us),
            ROOT.duration_us
        );
    }

    #[test]
    fn phase_shifted_polling_has_identical_canonical_sweep() {
        let canonical: Vec<_> = (1..=20).map(|tick| tick * ROOT_SUBSTEP_US).collect();
        let mut shifted: Vec<_> = (0..20).map(|tick| tick * ROOT_SUBSTEP_US + 1_000).collect();
        shifted.push(ROOT.duration_us);
        let canonical = run_simulation_schedule(&canonical);
        let shifted = run_simulation_schedule(&shifted);
        let stalled = run_simulation_schedule(&[ROOT.duration_us]);
        assert_eq!(canonical, shifted);
        assert_eq!(canonical, stalled);
        assert_eq!(canonical.consumed_elapsed_us, ROOT.duration_us);
        assert_eq!(canonical.substeps, 20);
    }

    #[test]
    fn replacement_flush_consumes_only_the_exact_partial_remainder() {
        let heading = -std::f32::consts::FRAC_PI_2;
        let first = advance_position(
            ROOT,
            heading,
            content::SPAWN.0,
            content::SPAWN.1,
            0,
            100_000,
            &[],
        )
        .unwrap();
        let flushed = advance_position(
            ROOT,
            heading,
            first.x,
            first.z,
            first.consumed_elapsed_us,
            167_095,
            &[],
        )
        .unwrap();
        let once = advance_position(
            ROOT,
            heading,
            content::SPAWN.0,
            content::SPAWN.1,
            0,
            167_095,
            &[],
        )
        .unwrap();
        assert_eq!((flushed.x, flushed.z), (once.x, once.z));
        assert_eq!(flushed.substeps, 2);
        assert_eq!(first.substeps + flushed.substeps, once.substeps);
        assert_eq!(flushed.consumed_elapsed_us, 167_095);
    }

    #[cfg(not(feature = "yongan"))]
    #[test]
    fn collision_clips_distance_and_consumes_the_blocked_remainder() {
        let wall = [crate::movement::Bounds {
            min_x: -1.0,
            max_x: 1.0,
            min_z: -0.6,
            max_z: -0.4,
        }];
        let blocked = advance_position(ROOT, 0.0, 0.0, 0.0, 0, 500_000, &wall).unwrap();
        assert_eq!((blocked.x, blocked.z), (0.0, -0.4));
        assert_eq!(blocked.consumed_elapsed_us, 500_000);

        let released = advance_position(
            ROOT,
            0.0,
            blocked.x,
            blocked.z,
            blocked.consumed_elapsed_us,
            ROOT.duration_us,
            &[],
        )
        .unwrap();
        assert!((released.z - (-0.4 + ROOT.endpoint_z_m as f32 / 2.0)).abs() < 0.000_001);
        assert!(released.z > ROOT.endpoint_z_m as f32);
        assert_eq!(released.consumed_elapsed_us, ROOT.duration_us);
    }

    #[cfg(not(feature = "yongan"))]
    #[test]
    fn endpoint_conversion_stays_within_f32_world_tolerance() {
        let end = advance_position(ROOT, 0.0, 0.0, 0.0, 0, ROOT.duration_us, &[]).unwrap();
        assert_eq!(end.x, 0.0);
        assert!((f64::from(end.z) - ROOT.endpoint_z_m).abs() < 0.000_001);
        assert_eq!(end.substeps, 20);
    }

    #[cfg(not(feature = "yongan"))]
    #[test]
    fn map_boundary_clips_and_consumes_root_remainder() {
        let start_x = crate::movement::HALF_SIZE - crate::movement::PLAYER_RADIUS - 0.1;
        let end = advance_position(
            ROOT,
            -std::f32::consts::FRAC_PI_2,
            start_x,
            0.0,
            0,
            ROOT.duration_us,
            &[],
        )
        .unwrap();
        assert_eq!(
            end.x,
            crate::movement::HALF_SIZE - crate::movement::PLAYER_RADIUS
        );
        assert!(end.z.abs() < 0.000_001);
        assert_eq!(end.consumed_elapsed_us, ROOT.duration_us);
    }

    #[cfg(feature = "yongan")]
    #[test]
    fn authored_town_wall_clips_root_and_consumes_the_action() {
        let start = (640.75, 549.5);
        let end = advance_position(
            ROOT,
            -std::f32::consts::FRAC_PI_2,
            start.0,
            start.1,
            0,
            ROOT.duration_us,
            &[],
        )
        .unwrap();
        assert!(end.x > 641.5 && end.x < 641.75, "wall stop x={}", end.x);
        assert_eq!(end.z, start.1);
        assert_eq!(end.consumed_elapsed_us, ROOT.duration_us);
        assert!(end.x < start.0 + ROOT.endpoint_z_m.abs() as f32);
    }

    #[cfg(feature = "yongan")]
    #[test]
    fn authored_bridge_accepts_root_at_terrain_height() {
        let start = (255.0, 700.0);
        let end = advance_position(
            ROOT,
            -std::f32::consts::FRAC_PI_2,
            start.0,
            start.1,
            0,
            ROOT.duration_us,
            &[],
        )
        .unwrap();
        let expected_x = start.0 + ROOT.endpoint_z_m.abs() as f32;
        assert!((end.x - expected_x).abs() < 0.001, "bridge end x={}", end.x);
        assert_eq!(end.z, start.1);
        assert!(content::height(start.0, start.1) > 130.0);
        assert!(content::height(end.x, end.z) > 130.0);
    }

    #[test]
    fn repeated_elapsed_consumes_no_displacement() {
        let unchanged = advance_position(ROOT, 0.0, 4.0, 5.0, 250_000, 250_000, &[]).unwrap();
        assert_eq!(unchanged.x, 4.0);
        assert_eq!(unchanged.z, 5.0);
        assert_eq!(unchanged.consumed_elapsed_us, 250_000);
        assert_eq!(unchanged.substeps, 0);
    }

    #[test]
    fn generated_prefix_has_bounded_linear_roots() {
        assert_eq!(definitions::PLAYER_ONEHAND_COMBO.len(), 3);
        for definition in definitions::PLAYER_ONEHAND_COMBO {
            let root = definition.root_motion.expect("selected root motion");
            assert!(valid_definition(root));
            assert_eq!(root.duration_us, definition.duration_us);
            assert!(definition.duration_us / ROOT_SUBSTEP_US < MAX_ROOT_SUBSTEPS as i64);
        }
        assert!(definitions::PLAYER_GENERAL_ATTACK.root_motion.is_none());
        assert!(definitions::MOB_ATTACK.root_motion.is_none());
    }
}
