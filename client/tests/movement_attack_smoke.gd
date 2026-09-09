extends RefCounted
## Focused protocol replay; this does not assert damage or rendered animation.


static func run(
	suite: Variant,
	actor: GameConnection,
	observer: GameConnection,
	identity: String,
	direction: float,
	label: String
) -> void:
	actor.set_move_input(direction, 0.0)
	var moving: bool = await suite._wait_until(
		func(): return int(suite._player(observer, identity).get("activity", 0)) == 1
	)
	if not suite._check(label + "_moving_before_attack", moving):
		actor.stop_moving()
		return
	var sequence := int(suite._player(observer, identity).get("attack_sequence", 0))
	actor.perform_attack()
	var attacked: bool = await suite._wait_until(
		func():
			return (
				int(suite._player(observer, identity).get("attack_sequence", 0)) == sequence + 1
				and int(suite._player(actor, identity).get("attack_sequence", 0)) == sequence + 1
			)
	)
	if not suite._check(label + "_attack_from_movement_replicates", attacked):
		actor.stop_moving()
		return
	var local: Dictionary = suite._player(actor, identity)
	var remote: Dictionary = suite._player(observer, identity)
	suite._check(
		label + "_attack_clock_matches",
		(
			int(local.action_started_at_us) > 0
			and int(local.action_ends_at_us) > int(local.action_started_at_us)
			and local.action_started_at_us == remote.action_started_at_us
			and local.action_ends_at_us == remote.action_ends_at_us
			and local.attack_action_id == remote.attack_action_id
		)
	)
	var recovered: bool = await suite._wait_until(
		func():
			return (
				int(suite._player(observer, identity).get("activity", -1)) == 0
				and int(suite._player(actor, identity).get("activity", -1)) == 0
			),
		4.0
	)
	if not suite._check(label + "_attack_recovers", recovered):
		return
	await suite._movement(actor, observer, identity, direction, label + "_after_attack")
