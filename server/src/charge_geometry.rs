//! Original target-centred integer-centimetre splash admission.

fn centimetres(value: f32) -> Result<i64, String> {
    let scaled = value * 100.0;
    if !scaled.is_finite() || f64::from(scaled).abs() > f64::from(i32::MAX) {
        return Err("Charge position exceeds supported source coordinates".into());
    }
    Ok(scaled.trunc() as i64)
}

fn approximate_cm(dx: i64, dz: i64) -> i64 {
    // utils.h::DISTANCE_APPROX, retaining its final integer shift.
    (246 * dx.max(dz) + 102 * dx.min(dz)) >> 8
}

pub fn contains(center: [f32; 2], victim: [f32; 2], radius_m: f32) -> Result<bool, String> {
    let radius = f64::from(radius_m) * 100.0;
    if !radius.is_finite()
        || !(1.0..=1000.0).contains(&radius.round())
        || (radius - radius.round()).abs() > 0.001
    {
        return Err("Charge splash radius must use bounded whole centimetres".into());
    }
    let dx = (centimetres(center[0])? - centimetres(victim[0])?).abs();
    let dz = (centimetres(center[1])? - centimetres(victim[1])?).abs();
    Ok(approximate_cm(dx, dz) <= radius.round() as i64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_metric_differs_from_a_euclidean_circle() {
        // 209 cm along an axis truncates to approximate distance 200 cm.
        assert!(contains([0.0; 2], [2.09, 0.0], 2.0).unwrap());
        assert!(!contains([0.0; 2], [2.11, 0.0], 2.0).unwrap());
        assert!(contains([0.0; 2], [1.47, 1.47], 2.0).unwrap());
        assert!(!contains([0.0; 2], [1.48, 1.48], 2.0).unwrap());
    }

    #[test]
    fn integer_boundary_and_float_coordinate_projection_are_explicit() {
        assert_eq!(approximate_cm(209, 0), 200);
        assert_eq!(approximate_cm(210, 0), 201);
        assert_eq!(approximate_cm(147, 147), 199);
        assert_eq!(approximate_cm(148, 148), 201);
        // Coordinates truncate after f32 metre-to-centimetre conversion. A
        // decimal literal is not necessarily the exact integer boundary.
        assert_eq!(centimetres(2.10).unwrap(), 209);
        assert_eq!(centimetres(-2.10).unwrap(), -209);
        assert!(contains([0.0; 2], [2.10, 0.0], 2.0).unwrap());
    }

    #[test]
    fn target_center_and_signed_coordinates_are_preserved() {
        assert!(contains([10.0, -10.0], [10.0, -10.0], 2.0).unwrap());
        assert!(contains([10.0, -10.0], [12.09, -10.0], 2.0).unwrap());
        assert!(!contains([0.0; 2], [12.09, -10.0], 2.0).unwrap());
        for [x, z] in [[2.09, 0.0], [2.10, 0.0], [1.47, 1.47], [1.48, 1.48]] {
            let expected = contains([0.0; 2], [x, z], 2.0).unwrap();
            for signs in [[1.0, 1.0], [-1.0, 1.0], [1.0, -1.0], [-1.0, -1.0]] {
                assert_eq!(
                    contains([0.0; 2], [x * signs[0], z * signs[1]], 2.0).unwrap(),
                    expected
                );
            }
        }
    }

    #[test]
    fn invalid_geometry_rejects_without_integer_overflow() {
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, f32::MAX] {
            assert!(contains([value, 0.0], [0.0; 2], 2.0).is_err());
            assert!(contains([0.0; 2], [0.0, value], 2.0).is_err());
        }
        for radius in [0.0, -1.0, 10.01, 0.295, f32::NAN, f32::INFINITY] {
            assert!(contains([0.0; 2], [0.0; 2], radius).is_err());
        }
        assert!(!contains([-20_000_000.0; 2], [20_000_000.0; 2], 2.0).unwrap());
        assert!(contains([0.0; 2], [0.29, 0.0], 0.29).unwrap());
        assert!(contains([0.0; 2], [0.01, 0.0], 0.01).unwrap());
    }
}
