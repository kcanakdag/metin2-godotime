//! Exact-life hit admission shared by single- and multi-event skill casts.
//! Event zero retains the existing persisted `monster:life` representation.

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
