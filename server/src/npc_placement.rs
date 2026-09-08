//! Original stationary NPC area sampling, shared by server integration and authoring tools.
//! Callers provide the server RNG and terrain validation; clients never choose samples.

#[derive(Clone, Copy, Debug)]
pub struct Area {
    bounds_cm: [i32; 4],
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Placement {
    pub x_cm: i32,
    pub z_cm: i32,
    pub height_m: f32,
    pub heading_degrees: u16,
}

impl Placement {
    pub fn yaw(self) -> f32 {
        // Original forward is (+sin, +cos); Godot actor forward is -Z.
        (std::f32::consts::PI + f32::from(self.heading_degrees % 360).to_radians())
            .rem_euclid(std::f32::consts::TAU)
    }
}

impl Area {
    pub fn new(bounds_cm: [i32; 4]) -> Result<Self, String> {
        let [min_x, min_z, max_x, max_z] = bounds_cm;
        if min_x < 0
            || min_z < 0
            || min_x > max_x
            || min_z > max_z
            || (min_x == max_x && min_z == max_z)
        {
            return Err("Invalid NPC area rectangle; point spawns use their own policy.".into());
        }
        Ok(Self { bounds_cm })
    }

    pub fn sample(
        self,
        mut random: impl FnMut(i32, i32) -> i32,
        mut height: impl FnMut(f32, f32) -> Option<f32>,
    ) -> Result<Option<Placement>, String> {
        let [min_x, min_z, max_x, max_z] = self.bounds_cm;
        // CHARACTER_MANAGER::SpawnMobRange tries sixteen inclusive integer samples.
        for _ in 0..16 {
            let x_cm = random(min_x, max_x);
            let z_cm = random(min_z, max_z);
            if !(min_x..=max_x).contains(&x_cm) || !(min_z..=max_z).contains(&z_cm) {
                return Err("NPC placement RNG returned an out-of-range coordinate.".into());
            }
            let Some(height_m) = height(x_cm as f32 / 100.0, z_cm as f32 / 100.0) else {
                continue;
            };
            if !height_m.is_finite() {
                return Err("NPC terrain returned a nonfinite height.".into());
            }
            // The range path ignores regen's direction and uses SpawnMob's default.
            let heading = random(0, 360);
            if !(0..=360).contains(&heading) {
                return Err("NPC placement RNG returned an invalid heading.".into());
            }
            return Ok(Some(Placement {
                x_cm,
                z_cm,
                height_m,
                heading_degrees: heading as u16,
            }));
        }
        Ok(None) // Retry through server regeneration; never substitute the center.
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inclusive_edges_preserve_centimetres_and_heading_equivalence() {
        let area = Area::new([68600, 47400, 68800, 47600]).unwrap();
        let low = area
            .sample(
                |lo, _| lo,
                |x, z| {
                    assert_eq!((x, z), (686.0, 474.0));
                    Some(198.5)
                },
            )
            .unwrap()
            .unwrap();
        let high = area
            .sample(|_, hi| hi, |_, _| Some(198.5))
            .unwrap()
            .unwrap();
        assert_eq!((low.x_cm, low.z_cm, low.heading_degrees), (68600, 47400, 0));
        assert_eq!(
            (high.x_cm, high.z_cm, high.heading_degrees),
            (68800, 47600, 360)
        );
        assert_eq!(low.yaw(), high.yaw());
        assert_eq!(low.yaw(), std::f32::consts::PI);
    }

    #[test]
    fn rejected_terrain_retries_exactly_sixteen_times_without_a_heading_or_fallback() {
        let mut draws = 0;
        let mut heights = 0;
        let result = Area::new([100, 200, 100, 300])
            .unwrap()
            .sample(
                |lo, _| {
                    draws += 1;
                    lo
                },
                |_, _| {
                    heights += 1;
                    None
                },
            )
            .unwrap();
        assert_eq!(result, None);
        assert_eq!((draws, heights), (32, 16));
    }

    #[test]
    fn first_valid_attempt_uses_its_height_and_only_then_draws_heading() {
        let mut draws = vec![101, 201, 102, 202, 90].into_iter();
        let mut checks = 0;
        let p = Area::new([100, 200, 110, 210])
            .unwrap()
            .sample(
                |_, _| draws.next().unwrap(),
                |_, _| {
                    checks += 1;
                    (checks == 2).then_some(7.5)
                },
            )
            .unwrap()
            .unwrap();
        assert_eq!(
            p,
            Placement {
                x_cm: 102,
                z_cm: 202,
                height_m: 7.5,
                heading_degrees: 90
            }
        );
        assert!(draws.next().is_none());
    }

    #[test]
    fn malformed_rectangles_rng_and_terrain_fail_closed() {
        for bounds in [[0, 0, 0, 0], [-1, 0, 1, 1], [2, 0, 1, 1], [0, 2, 1, 1]] {
            assert!(Area::new(bounds).is_err());
        }
        let area = Area::new([100, 200, 110, 210]).unwrap();
        assert!(area.sample(|lo, _| lo - 1, |_, _| Some(0.0)).is_err());
        assert!(area.sample(|lo, _| lo, |_, _| Some(f32::NAN)).is_err());
        assert!(
            area.sample(|lo, hi| if lo == 0 { hi + 1 } else { lo }, |_, _| Some(0.0))
                .is_err()
        );
    }
}
