//! Validated server positions determine skill facing; zero authored range is unlimited.
pub fn heading(owner: [f32; 2], target: [f32; 2], range: f32, current: f32) -> Result<f32, String> {
    if !owner
        .into_iter()
        .chain(target)
        .chain([range, current])
        .all(f32::is_finite)
        || !(0.0..=100.0).contains(&range)
    {
        return Err("Invalid skill target geometry".into());
    }
    let x = f64::from(owner[0]) - f64::from(target[0]);
    let z = f64::from(owner[1]) - f64::from(target[1]);
    if range > 0.0 && x.hypot(z) >= f64::from(range) {
        return Err("Move closer to use this skill".into());
    }
    Ok(if x == 0.0 && z == 0.0 {
        current
    } else {
        x.atan2(z) as f32
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn target_facing_and_source_range_boundaries() {
        assert_eq!(heading([0.0; 2], [0.0, -2.0], 0.0, 1.0).unwrap(), 0.0);
        assert_eq!(
            heading([0.0; 2], [2.0, 0.0], 0.0, 1.0).unwrap(),
            -std::f32::consts::FRAC_PI_2
        );
        assert_eq!(heading([0.0; 2], [0.0; 2], 0.0, 1.0).unwrap(), 1.0);
        assert!(heading([0.0; 2], [0.0, -1000.0], 0.0, 1.0).is_ok());
        assert!(heading([0.0; 2], [0.0, -2.0], 2.0, 1.0).is_err());
        assert!(heading([0.0; 2], [0.0, -1.99], 2.0, 1.0).is_ok());
        assert!(heading([0.0; 2], [f32::NAN, 0.0], 0.0, 1.0).is_err());
        assert!(heading([0.0; 2], [0.0; 2], -1.0, 1.0).is_err());
    }
}
