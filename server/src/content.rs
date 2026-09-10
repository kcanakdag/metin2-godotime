//! Trusted offline map data. Client coordinates never determine terrain heights or collision.
use crate::movement::{Bounds, PLAYER_RADIUS};

#[cfg(feature = "yongan")]
const DATA: &[u8] = include_bytes!("../content/yongan.bin");
#[cfg(not(feature = "yongan"))]
const DATA: &[u8] = &[];
pub const YONGAN: bool = cfg!(feature = "yongan");
#[cfg(feature = "yongan")]
pub const HASH: &str = include_str!("../content/yongan.sha256");
#[cfg(not(feature = "yongan"))]
pub const HASH: &str = "training-v2";
pub const SPAWN: (f32, f32) = if YONGAN { (660.0, 575.0) } else { (-4.0, 3.0) };
#[cfg(test)]
pub const MONSTER_HOME: (f32, f32) = if YONGAN { (675.0, 575.0) } else { (3.0, 3.0) };

fn integer(offset: usize) -> usize {
    u32::from_le_bytes(DATA[offset..offset + 4].try_into().unwrap()) as usize
}
fn number(offset: usize) -> f32 {
    f32::from_le_bytes(DATA[offset..offset + 4].try_into().unwrap())
}
fn terrain(x: usize, z: usize) -> f32 {
    let offset = 32 + 2 * (z * integer(8) + x);
    u16::from_le_bytes(DATA[offset..offset + 2].try_into().unwrap()) as f32 * 0.005
}
fn attr_offset() -> usize {
    32 + integer(8) * integer(12) * 2
}
fn shapes_offset() -> usize {
    attr_offset() + integer(16) * integer(20)
}
fn floors_offset() -> usize {
    shapes_offset() + integer(24) * 52
}

pub fn in_bounds(x: f32, z: f32) -> bool {
    if !x.is_finite() || !z.is_finite() {
        return false;
    }
    if YONGAN {
        x >= PLAYER_RADIUS
            && z >= PLAYER_RADIUS
            && x < integer(16) as f32 - PLAYER_RADIUS
            && z < integer(20) as f32 - PLAYER_RADIUS
    } else {
        crate::movement::valid_target(x, z).is_ok()
    }
}

/// Same triangle diagonal as the Blender terrain mesh, plus authored bridge/platform surfaces.
pub fn height(x: f32, z: f32) -> f32 {
    if !YONGAN || !in_bounds(x, z) {
        return 0.0;
    }
    let gx = x * 0.5;
    let gz = z * 0.5;
    let ix = gx.floor() as usize;
    let iz = gz.floor() as usize;
    let u = gx.fract();
    let v = gz.fract();
    let mut y = if u + v <= 1.0 {
        terrain(ix, iz) * (1.0 - u - v) + terrain(ix + 1, iz) * u + terrain(ix, iz + 1) * v
    } else {
        terrain(ix + 1, iz + 1) * (u + v - 1.0)
            + terrain(ix, iz + 1) * (1.0 - u)
            + terrain(ix + 1, iz) * (1.0 - v)
    };
    for index in 0..integer(28) {
        let o = floors_offset() + index * 52;
        if x < number(o) || x > number(o + 4) || z < number(o + 8) || z > number(o + 12) {
            continue;
        }
        let a = (number(o + 16), number(o + 20), number(o + 24));
        let b = (number(o + 28), number(o + 32), number(o + 36));
        let c = (number(o + 40), number(o + 44), number(o + 48));
        let det = (b.2 - c.2) * (a.0 - c.0) + (c.0 - b.0) * (a.2 - c.2);
        if det.abs() < 0.0001 {
            continue;
        }
        let u = ((b.2 - c.2) * (x - c.0) + (c.0 - b.0) * (z - c.2)) / det;
        let v = ((c.2 - a.2) * (x - c.0) + (a.0 - c.0) * (z - c.2)) / det;
        if u >= -0.0001 && v >= -0.0001 && u + v <= 1.0001 {
            y = y.max(u * a.1 + v * b.1 + (1.0 - u - v) * c.1);
        }
    }
    y
}

fn segment_distance(x: f32, z: f32, a: (f32, f32), b: (f32, f32)) -> f32 {
    let dx = b.0 - a.0;
    let dz = b.1 - a.1;
    let t = (((x - a.0) * dx + (z - a.1) * dz) / (dx * dx + dz * dz).max(0.000001)).clamp(0.0, 1.0);
    (x - a.0 - t * dx).hypot(z - a.1 - t * dz)
}

pub fn blocked(x: f32, z: f32, y: f32) -> bool {
    if !YONGAN {
        return false;
    }
    if !in_bounds(x, z) {
        return true;
    }
    // Check the whole footprint, including diagonal cell corners between the cardinal points.
    for az in (z - PLAYER_RADIUS) as usize..=(z + PLAYER_RADIUS) as usize {
        for ax in (x - PLAYER_RADIUS) as usize..=(x + PLAYER_RADIUS) as usize {
            let near_x = x.clamp(ax as f32, ax as f32 + 1.0);
            let near_z = z.clamp(az as f32, az as f32 + 1.0);
            if (x - near_x).hypot(z - near_z) >= PLAYER_RADIUS {
                continue;
            }
            let flags = DATA[attr_offset() + az * integer(16) + ax];
            if flags & 1 != 0 {
                return true;
            }
            // Water is impassable unless an authored elevated surface carries the player.
            if flags & 2 != 0 && y <= terrain(ax / 2, az / 2) + 0.4 {
                return true;
            }
        }
    }
    for index in 0..integer(24) {
        let o = shapes_offset() + index * 52;
        if y + 1.6 <= number(o + 4) || y + 0.3 >= number(o + 8) {
            continue;
        }
        if number(o) > 0.5 {
            if (x - number(o + 12)).hypot(z - number(o + 16)) < number(o + 44) + PLAYER_RADIUS {
                return true;
            }
            continue;
        }
        let mut positive = false;
        let mut negative = false;
        for i in 0..4 {
            let j = (i + 1) % 4;
            let a = (number(o + 12 + i * 8), number(o + 16 + i * 8));
            let b = (number(o + 12 + j * 8), number(o + 16 + j * 8));
            if segment_distance(x, z, a, b) < PLAYER_RADIUS {
                return true;
            }
            let cross = (b.0 - a.0) * (z - a.1) - (b.1 - a.1) * (x - a.0);
            positive |= cross > 0.001;
            negative |= cross < -0.001;
        }
        if positive != negative {
            return true;
        }
    }
    false
}

pub fn valid_target(x: f32, z: f32) -> Result<(), String> {
    if !in_bounds(x, z) {
        return Err("Destination must be finite and inside the map boundary.".into());
    }
    if blocked(x, z, height(x, z)) {
        return Err("Destination is blocked by terrain or a building.".into());
    }
    Ok(())
}

/// Authoring and live initialization use the same ground and obstacle rules.
pub fn valid_spawn(x: f32, z: f32) -> Result<(), String> {
    valid_target(x, z)?;
    if !YONGAN
        && crate::movement::TRAINING_OBSTACLES
            .iter()
            .any(|&(ox, oz, hx, hz, _, _)| {
                (x - ox).abs() < hx + PLAYER_RADIUS && (z - oz).abs() < hz + PLAYER_RADIUS
            })
    {
        return Err("Spawn overlaps a training obstacle.".into());
    }
    Ok(())
}

/// Original stationary NPCs may stand on blocked terrain; players and mobs may not.
pub fn valid_npc_position(x: f32, z: f32) -> Result<(), String> {
    if !in_bounds(x, z) || !height(x, z).is_finite() {
        return Err("NPC position is outside the finite map bounds.".into());
    }
    Ok(())
}

pub fn slide(x: f32, z: f32, dx: f32, dz: f32, bounds: &[Bounds]) -> (f32, f32) {
    if !YONGAN {
        return crate::movement::slide(x, z, dx, dz, bounds);
    }
    let count = (dx.hypot(dz) / 0.15).ceil().max(1.0) as u32;
    let (mut nx, mut nz) = (x, z);
    for _ in 0..count {
        for (sx, sz) in [(dx / count as f32, 0.0), (0.0, dz / count as f32)] {
            let (tx, tz) = (nx + sx, nz + sz);
            let y = height(tx, tz);
            if in_bounds(tx, tz)
                && (y - height(nx, nz)).abs() <= 0.25 + sx.hypot(sz) * 0.9
                && !blocked(tx, tz, y)
            {
                nx = tx;
                nz = tz;
            }
        }
    }
    (nx, nz)
}

pub fn clear_path(x: f32, z: f32, tx: f32, tz: f32, bounds: &[Bounds]) -> bool {
    if !in_bounds(x, z) || !in_bounds(tx, tz) {
        return false;
    }
    let count = ((tx - x).hypot(tz - z) / 0.25).ceil().max(1.0) as u32;
    (0..=count).all(|i| {
        let t = i as f32 / count as f32;
        let (px, pz) = (x + (tx - x) * t, z + (tz - z) * t);
        !blocked(px, pz, height(px, pz)) && !bounds.iter().any(|b| b.contains(px, pz))
    })
}

#[cfg(all(test, feature = "yongan"))]
mod tests {
    use super::*;
    #[test]
    fn baked_world_and_spawn_are_consistent() {
        assert_eq!(&DATA[..8], b"MT2YON02");
        assert_eq!(DATA.len(), floors_offset() + integer(28) * 52);
        assert!(height(SPAWN.0, SPAWN.1) > 100.0);
        for slot in 0..4 {
            assert!(valid_target(SPAWN.0 + slot as f32 * 1.2, SPAWN.1).is_ok());
        }
        assert!(valid_target(MONSTER_HOME.0, MONSTER_HOME.1).is_ok());
        assert!(valid_target(f32::NAN, 575.0).is_err());
        assert!(valid_target(1024.0, 575.0).is_err());
    }
    #[test]
    fn town_movement_has_height_and_obstruction() {
        let (x, z) = slide(SPAWN.0, SPAWN.1, 0.5, 0.0, &[]);
        assert!((x - SPAWN.0 - 0.5).abs() < 0.001);
        assert!((height(x, z) - height(SPAWN.0, SPAWN.1)).abs() < 0.5);
        assert!((640..720).any(|x| (540..600).any(|z| blocked(
            x as f32,
            z as f32,
            height(x as f32, z as f32)
        ))));
    }

    #[test]
    fn authored_building_wall_stops_swept_motion_without_terrain_flags() {
        // Pinned town building: all cells under this point are clear; its .mdatr wall blocks it.
        let (x, z) = (641.75, 549.5);
        for ax in 641..=642 {
            assert_eq!(DATA[attr_offset() + 549 * integer(16) + ax], 0);
        }
        assert!(valid_target(x, z).is_err());
        assert!(valid_target(x - 1.0, z).is_ok());
        let (stop_x, stop_z) = slide(x - 1.0, z, 2.0, 0.0, &[]);
        assert!(stop_x > x - 1.0 && stop_x < x);
        assert_eq!(stop_z, z);
        assert!(valid_target(stop_x, stop_z).is_ok());
        assert!(!clear_path(x - 1.0, z, x + 1.0, z, &[]));
    }

    #[test]
    fn player_footprint_cannot_clip_a_diagonal_blocked_cell() {
        // The old center/cardinal probes miss cell (671, 541), only 0.354 m from this center.
        let (x, z) = (670.75, 540.75);
        for (ax, az) in [(670, 540), (671, 540), (670, 541)] {
            assert_eq!(DATA[attr_offset() + az * integer(16) + ax], 0);
        }
        assert_ne!(DATA[attr_offset() + 541 * integer(16) + 671] & 1, 0);
        // Above all authored walls, the cell alone must still block the footprint.
        assert!(blocked(x, z, 10000.0));
    }

    #[test]
    fn bridge_surface_carries_movement_above_the_river_across_chunk_seam() {
        let y = height(256.0, 700.0);
        assert!((y - 131.39287).abs() < 0.001);
        assert!(y - terrain(128, 350) > 18.0);
        assert!(valid_target(256.0, 700.0).is_ok());
        let (x, z) = slide(255.0, 700.0, 2.0, 0.0, &[]);
        assert!((x - 257.0).abs() < 0.001);
        assert_eq!(z, 700.0);
        assert!((height(255.999, z) - height(256.001, z)).abs() < 0.001);
        // The adjacent river cannot be entered at terrain height.
        assert!(blocked(256.0, 700.0, terrain(128, 350)));
    }

    #[test]
    fn invalid_path_endpoints_fail_before_sampling() {
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -1.0, 2000.0] {
            assert!(!clear_path(SPAWN.0, SPAWN.1, bad, SPAWN.1, &[]));
            assert!(!clear_path(bad, SPAWN.1, SPAWN.0, SPAWN.1, &[]));
        }
    }

    #[test]
    fn buried_water_planes_do_not_block_dry_farmland() {
        // The pinned water map contains a plane at 153.05 m under ground at 175.535 m.
        // The renderer omits this plane, so it must not create an invisible barrier.
        for (x, z) in [(535.0, 367.0), (549.41, 367.18), (503.0, 360.0)] {
            assert!(valid_target(x, z).is_ok());
            let (tx, tz) = slide(x, z, 0.5, 0.0, &[]);
            assert!((tx - x - 0.5).abs() < 0.001);
            assert_eq!(tz, z);
        }
        // The real river beneath the authored bridge remains impassable on the riverbed.
        assert!(blocked(256.0, 700.0, terrain(128, 350)));
    }
}

#[cfg(all(test, not(feature = "yongan")))]
mod training_tests {
    use super::*;

    #[test]
    fn combat_paths_respect_the_same_obstacles_as_movement() {
        let wall = [Bounds {
            min_x: 1.0,
            max_x: 2.0,
            min_z: -3.0,
            max_z: 3.0,
        }];
        assert!(!clear_path(0.5, 0.0, 2.5, 0.0, &wall));
        assert!(!clear_path(2.5, 0.0, 0.5, 0.0, &wall));
        assert!(clear_path(0.5, 4.0, 2.5, 4.0, &wall));
        assert_eq!(slide(0.5, 0.0, 2.0, 0.0, &wall), (1.0, 0.0));
    }
}

#[cfg(test)]
mod npc_position_tests {
    #[test]
    fn stationary_policy_preserves_numeric_bounds() {
        for (x, z) in [(f32::NAN, 1.0), (1.0, f32::INFINITY), (1.0e9, 1.0)] {
            assert!(super::valid_npc_position(x, z).is_err());
        }
        if super::YONGAN {
            assert!(super::valid_spawn(251.0, 874.0).is_err());
            assert!(super::valid_npc_position(251.0, 874.0).is_ok());
        }
    }
}

#[cfg(all(test, feature = "yongan"))]
mod guard_route_tests {
    use super::*;
    use crate::movement::{self, BASE_SPEED_POINTS, Travel};

    /// The Yongan square route the exported QA click walks: the city guard stands at
    /// (605, 663) and the click lands on (608, 668).
    ///
    /// `NpcApproach` only fires its interaction inside a 4.5 m radius, so the walked
    /// line has to stay clear *and* actually close the gap. The reservation also
    /// re-issues click-to-move onto the guard's own position, which therefore has to
    /// pass the `move_to` destination validation too.
    const GUARD: (f32, f32) = (605.0, 663.0);
    const APPROACH: (f32, f32) = (608.0, 668.0);
    const INTERACTION_DISTANCE: f32 = 4.5;

    fn distance(x: f32, z: f32) -> f32 {
        (x - GUARD.0).hypot(z - GUARD.1)
    }

    #[test]
    fn square_to_guard_route_closes_inside_the_interaction_radius() {
        assert!(valid_target(GUARD.0, GUARD.1).is_ok());
        assert!(distance(APPROACH.0, APPROACH.1) > INTERACTION_DISTANCE);
        assert!(
            clear_path(APPROACH.0, APPROACH.1, GUARD.0, GUARD.1, &[]),
            "baked world geometry blocks the guard route"
        );

        // Replay the authoritative walk. A reconnect now re-issues this same intent
        // instead of dropping it, so the route must reach interaction range rather
        // than stalling outside it (the exported r15 click stopped at 5.04 m).
        let (mut x, mut z) = APPROACH;
        let mut clock = 0i64;
        let mut ticks = 0;
        while distance(x, z) > INTERACTION_DISTANCE {
            let previous = clock;
            clock += i64::from(crate::TICK_MS) * 1000;
            let travel = Travel::with_effects(previous, clock, 0, BASE_SPEED_POINTS, &[]).unwrap();
            let (step_x, step_z) = movement::target_step(x, z, GUARD.0, GUARD.1, travel);
            let (next_x, next_z) = slide(x, z, step_x, step_z, &[]);
            assert!(
                (next_x - x).hypot(next_z - z) > 0.0,
                "the walk stalled at ({next_x}, {next_z})"
            );
            x = next_x;
            z = next_z;
            ticks += 1;
            assert!(ticks < 200, "the walk never reached the interaction radius");
        }
    }

    #[test]
    fn reconnect_reissue_from_every_surrounding_tile_stays_walkable() {
        // A re-issue that already sits inside the radius interacts without walking.
        assert!(distance(GUARD.0 + 3.0, GUARD.1) <= INTERACTION_DISTANCE);
        for (offset_x, offset_z) in [
            (0.0, 5.0),
            (5.0, 0.0),
            (0.0, -5.0),
            (-5.0, 0.0),
            (4.0, 4.0),
            (4.0, -4.0),
            (-4.0, 4.0),
            (-4.0, -4.0),
        ] {
            let (start_x, start_z) = (GUARD.0 + offset_x, GUARD.1 + offset_z);
            assert!(valid_target(start_x, start_z).is_ok());
            assert!(distance(start_x, start_z) > INTERACTION_DISTANCE);
            assert!(
                clear_path(start_x, start_z, GUARD.0, GUARD.1, &[]),
                "the reconnect re-issue from ({start_x}, {start_z}) is blocked"
            );
        }
    }
}
