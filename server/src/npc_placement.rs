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

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct GroupPlacement {
    pub slot: usize,
    pub vnum: u32,
    pub placement: Placement,
}

/// Plan original overworld group positions. Callers validate terrain per species
/// and transact the resulting entities with the regeneration owner allocation.
pub fn sample_group(
    members: &[u32],
    bounds_cm: [i32; 4],
    mut random: impl FnMut(i32, i32) -> i32,
    mut height: impl FnMut(u32, f32, f32) -> Option<f32>,
) -> Result<Vec<GroupPlacement>, String> {
    if members.is_empty() || members.len() > 256 || members.contains(&0) {
        return Err("Group requires 1..=256 valid member definitions".into());
    }
    let mut area = Area::new(bounds_cm)?;
    let mut result = Vec::new();
    for (slot, &vnum) in members.iter().enumerate() {
        let Some(placement) = area.sample(&mut random, |x, z| height(vnum, x, z))? else {
            if slot == 0 {
                break; // Original leader placement failure aborts the whole group.
            }
            continue;
        };
        result.push(GroupPlacement {
            slot,
            vnum,
            placement,
        });
        let mut offsets = [0; 4];
        for offset in &mut offsets {
            *offset = random(300, 500);
            if !(300..=500).contains(offset) {
                return Err("Group placement RNG returned an invalid offset".into());
            }
        }
        // Unlike the initial source rectangle, these derived rectangles can
        // cross a map edge. Keep them intact; terrain rejects individual samples.
        let [left, top, right, bottom] = offsets;
        area = Area {
            bounds_cm: [
                placement
                    .x_cm
                    .checked_sub(left)
                    .ok_or("Group rectangle overflow")?,
                placement
                    .z_cm
                    .checked_sub(top)
                    .ok_or("Group rectangle overflow")?,
                placement
                    .x_cm
                    .checked_add(right)
                    .ok_or("Group rectangle overflow")?,
                placement
                    .z_cm
                    .checked_add(bottom)
                    .ok_or("Group rectangle overflow")?,
            ],
        };
    }
    Ok(result)
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
    fn groups_chain_from_successes_and_keep_last_bounds_after_follower_failure() {
        let mut rejected = 0;
        let rows = sample_group(
            &[101, 102, 103, 104],
            [1000, 1000, 1100, 1100],
            |lo, _| lo,
            |vnum, _, _| {
                if vnum == 102 {
                    rejected += 1;
                    None
                } else {
                    Some(0.0)
                }
            },
        )
        .unwrap();
        assert_eq!(rejected, 16);
        assert_eq!(
            rows.iter()
                .map(|r| (r.slot, r.vnum, r.placement.x_cm, r.placement.z_cm))
                .collect::<Vec<_>>(),
            vec![(0, 101, 1000, 1000), (2, 103, 700, 700), (3, 104, 400, 400)]
        );
    }

    #[test]
    fn failed_leader_aborts_and_invalid_offset_rejects_the_plan() {
        let mut attempts = 0;
        assert!(
            sample_group(
                &[101, 102],
                [1000, 1000, 1100, 1100],
                |lo, _| lo,
                |vnum, _, _| {
                    assert_eq!(vnum, 101);
                    attempts += 1;
                    None
                }
            )
            .unwrap()
            .is_empty()
        );
        assert_eq!(attempts, 16);
        assert!(
            sample_group(
                &[101],
                [1000, 1000, 1100, 1100],
                |lo, _| if lo == 300 { 299 } else { lo },
                |_, _, _| Some(0.0)
            )
            .is_err()
        );
    }

    #[test]
    fn derived_group_rectangle_can_cross_map_edge_without_rejecting_valid_samples() {
        let rows = sample_group(
            &[101, 102],
            [100, 100, 200, 200],
            |lo, hi| if lo < 0 { hi } else { lo },
            |_, x, z| (x >= 0.0 && z >= 0.0).then_some(0.0),
        )
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!((rows[1].placement.x_cm, rows[1].placement.z_cm), (400, 400));
    }

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
