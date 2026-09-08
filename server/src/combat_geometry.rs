//! Shared server geometry for fixed attack areas and authored skill spheres.

pub fn rotate(local_x: f64, local_z: f64, heading: f32) -> Option<(f32, f32)> {
    if !local_x.is_finite() || !local_z.is_finite() || !heading.is_finite() {
        return None;
    }
    let (sin, cos) = f64::from(heading).sin_cos();
    let x = cos * local_x + sin * local_z;
    let z = -sin * local_x + cos * local_z;
    let result = (x as f32, z as f32);
    (result.0.is_finite() && result.1.is_finite()).then_some(result)
}

pub(crate) fn squared_distance_to_segment(point: [f64; 3], start: [f64; 3], end: [f64; 3]) -> f64 {
    let segment = [end[0] - start[0], end[1] - start[1], end[2] - start[2]];
    let relative = [
        point[0] - start[0],
        point[1] - start[1],
        point[2] - start[2],
    ];
    let length_squared = segment
        .iter()
        .map(|component| component * component)
        .sum::<f64>();
    let t = if length_squared <= f64::EPSILON {
        0.0
    } else {
        relative
            .iter()
            .zip(segment)
            .map(|(left, right)| left * right)
            .sum::<f64>()
            / length_squared
    }
    .clamp(0.0, 1.0);
    (0..3)
        .map(|index| {
            let delta = start[index] + segment[index] * t - point[index];
            delta * delta
        })
        .sum()
}

/// Test a fixed attack sphere against a victim's previous-to-current center sweep.
/// `combined_radius` is the sum of attack and defending sphere radii.
pub fn swept_sphere_intersects(
    center: [f64; 3],
    previous: [f64; 3],
    current: [f64; 3],
    combined_radius: f64,
) -> bool {
    if !center
        .into_iter()
        .chain(previous)
        .chain(current)
        .all(f64::is_finite)
        || !combined_radius.is_finite()
        || combined_radius < 0.0
    {
        return false;
    }
    let radius_squared = combined_radius * combined_radius;
    let distance = squared_distance_to_segment(center, previous, current);
    radius_squared.is_finite() && distance.is_finite() && distance <= radius_squared
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn boundary_crossing_and_height_are_three_dimensional() {
        assert!(swept_sphere_intersects(
            [0.0; 3],
            [-2.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            0.5
        ));
        assert!(swept_sphere_intersects(
            [0.0; 3],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            1.0
        ));
        assert!(!swept_sphere_intersects(
            [0.0; 3],
            [-2.0, 2.0, 0.0],
            [2.0, 2.0, 0.0],
            1.0
        ));
    }

    #[test]
    fn nonfinite_and_overflowing_geometry_cannot_hit() {
        for radius in [-1.0, f64::NAN, f64::INFINITY, f64::MAX] {
            assert!(!swept_sphere_intersects(
                [0.0; 3], [0.0; 3], [0.0; 3], radius
            ));
        }
        for invalid in [f64::NAN, f64::INFINITY] {
            for index in 0..3 {
                let mut position = [0.0; 3];
                position[index] = invalid;
                assert!(!swept_sphere_intersects(position, [0.0; 3], [0.0; 3], 1.0));
                assert!(!swept_sphere_intersects([0.0; 3], position, [0.0; 3], 1.0));
                assert!(!swept_sphere_intersects([0.0; 3], [0.0; 3], position, 1.0));
            }
        }
    }
}
