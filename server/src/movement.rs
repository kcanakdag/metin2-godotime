//! Pure movement and collision rules; positions use meters on the X/Z plane.

pub const SPEED: f32 = 5.0;
pub const HALF_SIZE: f32 = 32.0;
pub const PLAYER_RADIUS: f32 = 0.45;

pub struct Bounds {
    pub min_x: f32,
    pub max_x: f32,
    pub min_z: f32,
    pub max_z: f32,
}

impl Bounds {
    pub fn contains(&self, x: f32, z: f32) -> bool {
        x > self.min_x && x < self.max_x && z > self.min_z && z < self.max_z
    }
}

pub fn valid_direction(x: f32, z: f32) -> Result<(), String> {
    if !x.is_finite() || !z.is_finite() || x.abs() > 1.0 || z.abs() > 1.0 {
        return Err("Direction components must be finite and between -1 and 1.".into());
    }
    Ok(())
}

pub fn valid_target(x: f32, z: f32) -> Result<(), String> {
    let limit = HALF_SIZE - PLAYER_RADIUS;
    if !x.is_finite() || !z.is_finite() || x.abs() > limit || z.abs() > limit {
        return Err("Destination must be finite and inside the map boundary.".into());
    }
    Ok(())
}

fn distance(elapsed: f32) -> f32 {
    if elapsed.is_finite() {
        SPEED * elapsed.clamp(0.0, 0.1)
    } else {
        0.0
    }
}

pub fn step(x: f32, z: f32, elapsed: f32) -> Result<(f32, f32), String> {
    valid_direction(x, z)?;
    let magnitude = x.hypot(z).max(1.0);
    Ok((
        x / magnitude * distance(elapsed),
        z / magnitude * distance(elapsed),
    ))
}

pub fn target_step(x: f32, z: f32, target_x: f32, target_z: f32, elapsed: f32) -> (f32, f32) {
    let dx = target_x - x;
    let dz = target_z - z;
    let length = dx.hypot(dz);
    if length < 0.02 {
        return (0.0, 0.0);
    }
    let travel = distance(elapsed).min(length);
    (dx / length * travel, dz / length * travel)
}

/// Resolve each axis against the entire swept segment, then slide on the other axis.
pub fn slide(x: f32, z: f32, dx: f32, dz: f32, obstacles: &[Bounds]) -> (f32, f32) {
    let limit = HALF_SIZE - PLAYER_RADIUS;
    let mut new_x = (x + dx).clamp(-limit, limit);
    for bounds in obstacles {
        if z <= bounds.min_z || z >= bounds.max_z {
            continue;
        }
        if dx > 0.0 && x <= bounds.min_x && new_x > bounds.min_x {
            new_x = bounds.min_x;
        } else if dx < 0.0 && x >= bounds.max_x && new_x < bounds.max_x {
            new_x = bounds.max_x;
        }
    }
    let mut new_z = (z + dz).clamp(-limit, limit);
    for bounds in obstacles {
        if new_x <= bounds.min_x || new_x >= bounds.max_x {
            continue;
        }
        if dz > 0.0 && z <= bounds.min_z && new_z > bounds.min_z {
            new_z = bounds.min_z;
        } else if dz < 0.0 && z >= bounds.max_z && new_z < bounds.max_z {
            new_z = bounds.max_z;
        }
    }
    (new_x, new_z)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn wall() -> [Bounds; 1] {
        [Bounds {
            min_x: 1.0,
            max_x: 2.0,
            min_z: -3.0,
            max_z: 3.0,
        }]
    }
    #[test]
    fn diagonal_movement_has_no_speed_bonus() {
        let (x, z) = step(1.0, 1.0, 0.1).unwrap();
        assert!((x.hypot(z) - 0.5).abs() < 0.00001);
        assert_eq!(step(0.5, 0.0, 0.1).unwrap(), (0.25, 0.0));
    }
    #[test]
    fn stalled_tick_cannot_bank_elapsed_time() {
        assert_eq!(step(1.0, 0.0, 3600.0).unwrap(), (0.5, 0.0));
        assert_eq!(step(1.0, 0.0, -1.0).unwrap(), (0.0, 0.0));
        assert_eq!(step(1.0, 0.0, f32::NAN).unwrap(), (0.0, 0.0));
    }
    #[test]
    fn rejects_nonfinite_and_out_of_range_input() {
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, 2.0, -2.0] {
            assert!(step(value, 0.0, 0.1).is_err());
            assert!(step(0.0, value, 0.1).is_err());
        }
        for value in [f32::NAN, f32::INFINITY, 32.0, -32.0] {
            assert!(valid_target(value, 0.0).is_err());
            assert!(valid_target(0.0, value).is_err());
        }
    }
    #[test]
    fn map_boundary_accounts_for_player_radius() {
        let limit = HALF_SIZE - PLAYER_RADIUS;
        assert_eq!(slide(31.5, -31.5, 0.5, -0.5, &[]), (limit, -limit));
    }
    #[test]
    fn swept_collision_prevents_tunneling_and_preserves_slide() {
        assert_eq!(slide(0.0, 0.0, 5.0, 0.0, &wall()), (1.0, 0.0));
        assert_eq!(slide(3.0, 0.0, -5.0, 0.0, &wall()), (2.0, 0.0));
        assert_eq!(slide(0.9, 0.0, 0.3, 0.3, &wall()), (1.0, 0.3));
        assert_eq!(slide(1.5, -4.0, 0.0, 5.0, &wall()), (1.5, -3.0));
        assert_eq!(slide(1.5, 4.0, 0.0, -5.0, &wall()), (1.5, 3.0));
    }
    #[test]
    fn click_target_stops_without_overshooting() {
        let (dx, dz) = target_step(0.0, 0.0, 0.1, 0.1, 0.1);
        assert!((dx - 0.1).abs() < 0.00001);
        assert!((dz - 0.1).abs() < 0.00001);
        assert_eq!(target_step(0.0, 0.0, 0.0, 0.0, 0.1), (0.0, 0.0));
    }
}
