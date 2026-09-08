//! Original damage-to-threat arithmetic, separate from XP damage attribution.
//! char_battle.cpp UpdateAggrPointEx applies two separately truncated f32 stages.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DamageKind {
    Normal,
    NormalRange,
    MeleeSkill,
    RangeSkill,
    Magic,
    Special,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Change {
    pub increment: i32,
    pub total: i32,
    pub party_increment: Option<i32>,
}

pub fn accumulate(
    previous: i32,
    damage: i32,
    kind: DamageKind,
    current_victim: bool,
    party_leader: Option<bool>,
) -> Result<Change, &'static str> {
    if previous < 0 {
        return Err("Threat total cannot be negative");
    }
    let multiplier = match kind {
        DamageKind::NormalRange | DamageKind::Magic => 1.2,
        DamageKind::RangeSkill => 1.5,
        _ => 1.0,
    };
    let mut increment = if multiplier == 1.0 {
        damage
    } else {
        multiply(damage, multiplier)?
    };
    if current_victim {
        increment = multiply(increment, 1.2)?;
    }
    let total = previous
        .checked_add(increment)
        .ok_or("Threat total overflow")?
        .max(0);
    let party_increment = party_leader
        .filter(|_| increment > 0 && kind != DamageKind::Special)
        .map(|leader| increment / if leader { 2 } else { 3 });
    Ok(Change {
        increment,
        total,
        party_increment,
    })
}

fn multiply(value: i32, multiplier: f32) -> Result<i32, &'static str> {
    let scaled = value as f32 * multiplier;
    if !scaled.is_finite() || !(-2_147_483_648.0..2_147_483_648.0).contains(&scaled) {
        return Err("Threat multiplier overflow");
    }
    Ok(scaled.trunc() as i32)
}

/// Called on threat updates, not as a timer-driven closest-player retarget.
/// The exact 3-second boundary is allowed. Reject reversed/overflowing clocks.
pub fn can_reconsider(last_victim_set_us: i64, now_us: i64) -> bool {
    now_us
        .checked_sub(last_victim_set_us)
        .is_some_and(|elapsed| elapsed >= 3_000_000)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_stages_truncate_separately_before_party_distribution() {
        // 4 * 1.2 -> 4; then 4 * 1.2 -> 4 (a combined 1.44 would give 5).
        assert_eq!(
            accumulate(10, 4, DamageKind::Magic, true, Some(true)).unwrap(),
            Change {
                increment: 4,
                total: 14,
                party_increment: Some(2)
            }
        );
        assert_eq!(
            accumulate(0, 7, DamageKind::RangeSkill, true, Some(false)).unwrap(),
            Change {
                increment: 12,
                total: 12,
                party_increment: Some(4)
            }
        );
        for kind in [
            DamageKind::Normal,
            DamageKind::MeleeSkill,
            DamageKind::Special,
        ] {
            let result = accumulate(0, 7, kind, false, Some(true)).unwrap();
            assert_eq!(result.increment, 7);
            assert_eq!(
                result.party_increment,
                if kind == DamageKind::Special {
                    None
                } else {
                    Some(3)
                }
            );
        }
        assert_eq!(
            accumulate(0, 7, DamageKind::NormalRange, false, None)
                .unwrap()
                .total,
            8
        );
    }

    #[test]
    fn negative_threat_clamps_total_but_is_not_sent_to_party() {
        assert_eq!(
            accumulate(3, -7, DamageKind::Magic, true, Some(true)).unwrap(),
            Change {
                increment: -9,
                total: 0,
                party_increment: None
            }
        );
        assert_eq!(
            accumulate(0, 0, DamageKind::Normal, false, Some(false))
                .unwrap()
                .party_increment,
            None
        );
    }

    #[test]
    fn invalid_totals_and_arithmetic_overflow_reject() {
        assert!(accumulate(-1, 1, DamageKind::Normal, false, None).is_err());
        assert!(accumulate(i32::MAX, 1, DamageKind::Normal, false, None).is_err());
        assert!(accumulate(0, i32::MAX, DamageKind::NormalRange, false, None).is_err());
        assert!(accumulate(0, i32::MIN, DamageKind::Magic, false, None).is_err());
        assert_eq!(
            accumulate(0, i32::MAX, DamageKind::Normal, false, None)
                .unwrap()
                .total,
            i32::MAX
        );
    }

    #[test]
    fn target_switch_requires_three_seconds_and_a_valid_clock() {
        assert!(!can_reconsider(10_000_000, 12_999_999));
        assert!(can_reconsider(10_000_000, 13_000_000));
        assert!(!can_reconsider(10_000_000, 9_999_999));
        assert!(!can_reconsider(i64::MIN, i64::MAX));
    }
}
