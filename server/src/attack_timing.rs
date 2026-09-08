//! Captured player attack clocks. Source motion times remain immutable.
use spacetimedb::{Identity, ReducerContext};

pub const BASE_SPEED: u16 = 100;
pub const MAX_SPEED: u16 = 170;

pub fn speed_with_bonus(bonus: u16) -> u16 {
    BASE_SPEED.saturating_add(bonus).min(MAX_SPEED)
}

pub fn equipped_speed(ctx: &ReducerContext, character: Identity) -> Result<u16, String> {
    let vnum = crate::inventory::equipped_weapon(ctx, character);
    let bonus = if vnum == 0 {
        0
    } else {
        crate::item_catalog::definition(vnum)?.attack_speed_bonus
    };
    Ok(speed_with_bonus(bonus))
}

/// Ceil to a whole microsecond: never open a source boundary early.
/// The selected item registry supports bonuses, not slowing effects.
pub fn scaled_us(source_us: i64, speed: u16) -> Result<i64, String> {
    if source_us < 0 || !(BASE_SPEED..=MAX_SPEED).contains(&speed) {
        return Err("Attack clock is outside the supported range.".into());
    }
    i64::try_from((i128::from(source_us) * 100 + i128::from(speed) - 1) / i128::from(speed))
        .map_err(|_| "Attack clock overflow.".into())
}

pub fn combo_input(
    input: crate::definitions::ComboInputDefinition,
    speed: u16,
) -> Result<crate::definitions::ComboInputDefinition, String> {
    Ok(crate::definitions::ComboInputDefinition {
        pre_input_us: scaled_us(input.pre_input_us, speed)?,
        direct_input_us: scaled_us(input.direct_input_us, speed)?,
        input_limit_us: scaled_us(input.input_limit_us, speed)?,
        link_us: scaled_us(input.link_us, speed)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clocks_are_bounded_precise_and_never_early() {
        for speed in [100, 122, 126, 170] {
            for source in [0, 1, 30_000, 333_333, 633_334, 1_000_000, i64::MAX] {
                let scaled = scaled_us(source, speed).unwrap();
                assert!(i128::from(scaled) * i128::from(speed) >= i128::from(source) * 100);
                assert!(i128::from(scaled - 1) * i128::from(speed) < i128::from(source) * 100);
            }
        }
        assert_eq!(scaled_us(1_000_000, 122), Ok(819_673));
        assert_eq!(scaled_us(1_000_000, 126), Ok(793_651));
        assert!(scaled_us(-1, 100).is_err());
        for speed in [0, 99, 171, u16::MAX] {
            assert!(scaled_us(1, speed).is_err());
        }
    }

    #[test]
    fn selected_equipment_and_cap_follow_original_points() {
        assert_eq!(speed_with_bonus(0), 100);
        assert_eq!(
            speed_with_bonus(
                crate::item_catalog::definition(10)
                    .unwrap()
                    .attack_speed_bonus
            ),
            122
        );
        assert_eq!(
            speed_with_bonus(
                crate::item_catalog::definition(7000)
                    .unwrap()
                    .attack_speed_bonus
            ),
            126
        );
        assert_eq!(speed_with_bonus(u16::MAX), 170);
    }

    #[test]
    fn every_common_window_keeps_its_order_at_the_cap() {
        for action in crate::characters::root_actions() {
            if let Some(input) = action.combo_input {
                let scaled = combo_input(input, 170).unwrap();
                assert!(scaled.pre_input_us < scaled.direct_input_us);
                assert!(scaled.direct_input_us <= scaled.input_limit_us);
                assert!(scaled.link_us <= scaled_us(action.duration_us, 170).unwrap());
            }
        }
    }
}
