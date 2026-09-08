//! Exact-life hit admission shared by single- and multi-event skill casts.
//! Event zero retains the existing persisted `monster:life` representation.

/// Capture all authored offsets on the accepted cast's clock in one validated step.
/// No caller can observe a partially captured list when a later event is invalid.
pub fn capture_events(windows: &[[i64; 2]], started_at_us: i64) -> Result<Vec<[i64; 2]>, String> {
    if started_at_us < 0 {
        return Err("Invalid skill cast clock".into());
    }
    active_events(windows, -1)?;
    windows
        .iter()
        .map(|&[start, end]| {
            if start > 3_200_000 || end > 13_200_000 {
                return Err("Skill event exceeds supported motion lifetime".into());
            }
            Ok([
                started_at_us
                    .checked_add(start)
                    .ok_or("Skill event clock overflow")?,
                started_at_us
                    .checked_add(end)
                    .ok_or("Skill event clock overflow")?,
            ])
        })
        .collect()
}

/// Select active motion events without merging gaps or replaying expired windows.
/// Times share one clock (absolute for saved casts, relative for authored motions).
/// Inclusive endpoints preserve the current live skill-window contract.
pub fn active_events(windows: &[[i64; 2]], now: i64) -> Result<u32, String> {
    if windows.len() > 32 {
        return Err("Too many skill hit events".into());
    }
    let mut active = 0;
    for (index, &[start, end]) in windows.iter().enumerate() {
        if start < 0 || end < start || end.checked_sub(start).is_none_or(|span| span > 13_200_000) {
            return Err("Invalid skill hit interval".into());
        }
        if now >= start && now <= end {
            active |= 1 << index;
        }
    }
    Ok(active)
}

fn decode(value: &str) -> Result<(u32, u32, u8), String> {
    let mut parts = value.split(':');
    let monster = parts
        .next()
        .and_then(|v| v.parse().ok())
        .ok_or("Invalid skill hit monster")?;
    let life = parts
        .next()
        .and_then(|v| v.parse().ok())
        .ok_or("Invalid skill hit life")?;
    let event = match parts.next() {
        Some(value) => value.parse().map_err(|_| "Invalid skill hit event")?,
        None => 0,
    };
    if parts.next().is_some() {
        return Err("Invalid skill hit receipt".into());
    }
    Ok((monster, life, event))
}

pub fn receipt(monster: u32, life: u32, event: u8) -> String {
    if event == 0 {
        format!("{monster}:{life}")
    } else {
        format!("{monster}:{life}:{event}")
    }
}

/// Returns admission only; append the receipt after damage calculation succeeds.
/// Budgets count successful hits, not candidate targets or simulation ticks.
pub fn admits(
    receipts: &[String],
    monster: u32,
    life: u32,
    event: u8,
    per_life_limit: u8,
    total_limit: u16,
) -> Result<bool, String> {
    if per_life_limit == 0 || total_limit == 0 || total_limit > 1024 {
        return Err("Invalid skill hit limits".into());
    }
    if receipts.len() >= usize::from(total_limit) {
        return Ok(false);
    }
    let mut hits = 0;
    for saved in receipts {
        let (saved_monster, saved_life, saved_event) = decode(saved)?;
        if (saved_monster, saved_life) == (monster, life) {
            if saved_event == event {
                return Ok(false);
            }
            hits += 1;
        }
    }
    Ok(hits < usize::from(per_life_limit))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_preserves_offsets_and_rejects_partial_or_overflowed_casts() {
        assert_eq!(
            capture_events(&[[10, 20], [30, 50]], 1_000).unwrap(),
            vec![[1_010, 1_020], [1_030, 1_050]]
        );
        assert!(capture_events(&[[0, 1]], -1).is_err());
        assert!(capture_events(&[[0, 1], [10, 20]], i64::MAX - 10).is_err());
        assert!(capture_events(&[[0, 1], [20, 10]], 0).is_err());
        assert!(capture_events(&[[3_200_001, 3_200_002]], 0).is_err());
        assert!(capture_events(&[[3_200_000, 13_200_001]], 0).is_err());
        assert_eq!(
            capture_events(&[[3_200_000, 13_200_000]], 0).unwrap(),
            vec![[3_200_000, 13_200_000]]
        );
    }

    #[test]
    fn separate_windows_preserve_gaps_overlap_and_expiration() {
        let windows = [[10, 20], [30, 40], [35, 50]];
        for (now, expected) in [
            (9, 0),
            (10, 1),
            (20, 1),
            (21, 0),
            (30, 2),
            (35, 6),
            (41, 4),
            (51, 0),
        ] {
            assert_eq!(active_events(&windows, now).unwrap(), expected);
        }
        assert_eq!(active_events(&[], 0).unwrap(), 0);
        assert_eq!(active_events(&[[0, 0]], 0).unwrap(), 1);
        assert!(active_events(&[[2, 1]], 0).is_err());
        assert!(active_events(&[[-1, 1]], 0).is_err());
        assert!(active_events(&[[0, i64::MAX]], 0).is_err());
        assert!(active_events(&[[0, 1]; 33], 0).is_err());
        assert_eq!(active_events(&[[0, 1]; 32], 1).unwrap(), u32::MAX);
    }

    #[test]
    fn legacy_single_hit_and_respawn_identity_are_preserved() {
        let hits = vec!["10:1".into()];
        assert!(!admits(&hits, 10, 1, 0, 1, 12).unwrap());
        assert!(!admits(&hits, 10, 1, 1, 1, 12).unwrap());
        assert!(admits(&hits, 10, 2, 0, 1, 12).unwrap());
        assert!(admits(&hits, 100, 1, 0, 1, 12).unwrap());
        assert_eq!(receipt(10, 1, 0), "10:1");
    }

    #[test]
    fn three_events_allow_three_hits_without_replaying_any_event() {
        let mut hits = Vec::new();
        for event in 0..3 {
            assert!(admits(&hits, 10, 1, event, 3, 12).unwrap());
            hits.push(receipt(10, 1, event));
            assert!(!admits(&hits, 10, 1, event, 3, 12).unwrap());
        }
        assert!(!admits(&hits, 10, 1, 3, 3, 12).unwrap());
        assert!(admits(&hits, 11, 1, 0, 3, 12).unwrap());
        assert!(!admits(&hits, 11, 1, 0, 3, 3).unwrap());
    }

    #[test]
    fn malformed_receipts_and_invalid_limits_reject() {
        for bad in ["", "10", "10:no", "10:1:256", "10:1:1:2"] {
            assert!(admits(&[bad.into()], 11, 1, 0, 1, 12).is_err());
        }
        for (per_life, total) in [(0, 12), (1, 0), (1, 1025)] {
            assert!(admits(&[], 10, 1, 0, per_life, total).is_err());
        }
    }
}
