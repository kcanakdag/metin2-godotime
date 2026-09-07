#[allow(dead_code)]
mod definitions {
    include!(concat!(env!("OUT_DIR"), "/trusted_definitions.rs"));
}

#[test]
fn generated_combo_constants_match_the_selected_source_prefix() {
    assert_eq!(
        definitions::DEFINITION_HASH,
        "958671d126376e06f827d90066dec6f78b343a90b52f3fe0dd91e4a1985c34b7"
    );
    assert_eq!(definitions::PLAYER_ONEHAND_COMBO.len(), 2);
    assert_eq!(
        definitions::PLAYER_ONEHAND_COMBO[0].id,
        "actor.player.warrior-male.onehand.combo_1"
    );
    assert_eq!(
        definitions::PLAYER_ONEHAND_COMBO[1].id,
        "actor.player.warrior-male.onehand.combo_2"
    );
    let first = definitions::PLAYER_ONEHAND_COMBO[0]
        .combo_input
        .expect("combo 1 timing");
    assert_eq!(
        (
            first.pre_input_us,
            first.direct_input_us,
            first.input_limit_us,
            first.link_us
        ),
        (167_094, 533_333, 602_564, 58_889)
    );
    let second = definitions::PLAYER_ONEHAND_COMBO[1]
        .combo_input
        .expect("combo 2 timing");
    assert_eq!(
        (
            second.pre_input_us,
            second.direct_input_us,
            second.input_limit_us,
            second.link_us,
        ),
        (100_513, 543_248, 636_581, 19_658)
    );
    assert_eq!(
        definitions::PLAYER_ONEHAND_ATTACK.id,
        definitions::PLAYER_ONEHAND_COMBO[0].id
    );
    assert!(definitions::PLAYER_GENERAL_ATTACK.combo_input.is_none());
    assert!(definitions::MOB_ATTACK.combo_input.is_none());
}
