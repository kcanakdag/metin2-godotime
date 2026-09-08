//! Shared fixed-area activation lifecycle; placement freezes on activation.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AreaPhase {
    Waiting,
    Activate,
    ActivatedThisTick,
    Scan,
    Expired,
}

pub fn area_phase(
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

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Placement {
    pub origin: [f64; 3],
    pub heading: f32,
    pub activated_at_us: i64,
}

impl Placement {
    pub fn capture(origin: [f64; 3], heading: f32, now: i64) -> Result<Self, &'static str> {
        if !origin.into_iter().all(f64::is_finite) || !heading.is_finite() || now <= 0 {
            return Err("Invalid fixed-area activation placement");
        }
        Ok(Self {
            origin,
            heading,
            activated_at_us: now,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn captured_placement_and_late_activation_do_not_follow_later_motion() {
        let mut origin = [10.0, 2.0, 20.0];
        let saved = Placement::capture(origin, 0.5, 150).unwrap();
        origin[0] = 99.0;
        assert_ne!(saved.origin, origin);
        assert_eq!(saved.origin, [10.0, 2.0, 20.0]);
        assert_eq!(
            area_phase(150, 100, 200, saved.activated_at_us),
            AreaPhase::ActivatedThisTick
        );
        assert_eq!(
            area_phase(151, 100, 200, saved.activated_at_us),
            AreaPhase::Scan
        );
        assert_eq!(area_phase(200, 100, 200, 0), AreaPhase::Expired);
        assert!(Placement::capture([f64::NAN, 0.0, 0.0], 0.0, 100).is_err());
        assert!(Placement::capture([0.0; 3], f32::INFINITY, 100).is_err());
    }
}
