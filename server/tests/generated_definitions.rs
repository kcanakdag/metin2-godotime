#[allow(dead_code)]
mod definitions {
    include!(concat!(env!("OUT_DIR"), "/trusted_definitions.rs"));
}

#[test]
fn generated_combo_constants_match_the_selected_source_prefix() {
    assert_eq!(
        definitions::DEFINITION_HASH,
        "2f096ae82998eeecb839df391a7350f8309e477a7004ef4c2e333167bc4ada8d"
    );
    assert_eq!(definitions::PLAYER_ONEHAND_COMBO.len(), 3);
    assert_eq!(
        definitions::PLAYER_ONEHAND_COMBO[0].id,
        "actor.player.warrior-male.onehand.combo_1"
    );
    assert_eq!(
        definitions::PLAYER_ONEHAND_COMBO[1].id,
        "actor.player.warrior-male.onehand.combo_2"
    );
    assert_eq!(
        definitions::PLAYER_ONEHAND_COMBO[2].id,
        "actor.player.warrior-male.onehand.combo_3"
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
    let third = definitions::PLAYER_ONEHAND_COMBO[2]
        .combo_input
        .expect("combo 3 timing");
    assert_eq!(
        (
            third.pre_input_us,
            third.direct_input_us,
            third.input_limit_us,
            third.link_us,
        ),
        (84_786, 418_462, 664_615, 60_171)
    );
    let expected_roots = [
        (0.0, -1.317569580078125, 1_000_000),
        (0.0, -0.852515640258789, 933_333),
        (0.0, -1.4301394653320312, 1_066_667),
    ];
    for (definition, expected) in definitions::PLAYER_ONEHAND_COMBO.iter().zip(expected_roots) {
        let root = definition.root_motion.expect("selected root motion");
        assert_eq!(
            (root.endpoint_x_m, root.endpoint_z_m, root.duration_us),
            expected
        );
        assert_eq!(root.duration_us, definition.duration_us);
    }
    assert_eq!(
        definitions::PLAYER_ONEHAND_ATTACK.id,
        definitions::PLAYER_ONEHAND_COMBO[0].id
    );
    assert!(definitions::PLAYER_GENERAL_ATTACK.combo_input.is_none());
    assert!(definitions::PLAYER_GENERAL_ATTACK.root_motion.is_none());
    assert!(definitions::MOB_ATTACK.combo_input.is_none());
    assert!(definitions::MOB_ATTACK.root_motion.is_none());
}
