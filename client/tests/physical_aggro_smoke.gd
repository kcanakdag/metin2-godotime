extends "res://tests/physical_combat_smoke.gd"
## Two real accounts, ordinary unarmed hits, and a training-only passive fixture.


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_physical_world(actor, observer, actor_id, observer_id)
	if ready:
		ready = _check(
			"passive_fixture_is_explicit",
			str(actor.world_info.content_hash) == "training-v4-passive-wild-dog-v1"
		)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _approach_dog(actor, observer, actor_id)
	if ready:
		ready = await _passive_then_retaliate(actor, observer, actor_id, observer_id)
	if not ready:
		_check("aggro_scenario_completed", false)
	_tokens.clear()
	_finish()


func _passive_then_retaliate(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	var before := _monster(observer).duplicate(true)
	var health := int(_player(observer, actor_id).health)
	await create_timer(4.0).timeout
	if not _check(
		"passive_ignores_nearby_unprovoking_player",
		(
			int(_monster(observer).attack_sequence) == int(before.attack_sequence)
			and int(_player(observer, actor_id).health) == health
			and _position(_monster(observer)).distance_to(_position(before)) < 0.01
		)
	):
		return false
	var mob_health := int(before.health)
	if not await _physical_hit(actor, observer, actor_id, false, "passive_first_hit"):
		return false
	var first_damage := mob_health - int(_monster(observer).health)
	if not _check(
		"passive_retaliates_against_actual_attacker",
		await _wait_until(
			func():
				return (
					str(_monster(observer).attack_target) == actor_id
					and str(_monster(actor).attack_target) == actor_id
					and int(_player(observer, actor_id).health) < health
				),
			6.0
		)
	):
		return false
	await create_timer(3.1).timeout
	mob_health = int(_monster(observer).health)
	if not await _physical_hit(actor, observer, actor_id, false, "passive_second_hit"):
		return false
	var second_damage := mob_health - int(_monster(observer).health)
	var incumbent_threat := int(first_damage * 1.2) + int(second_damage * 1.2)
	return await _challenge(actor, observer, actor_id, observer_id, incumbent_threat)


func _challenge(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	observer_id: String,
	incumbent_threat: int
) -> bool:
	var mob_health := 0
	var health := 0
	var challenger_damage := 0
	for index in range(16):
		mob_health = int(_monster(actor).health)
		if not await _physical_hit(observer, actor, observer_id, false, "challenger_%d" % index):
			return false
		challenger_damage += mob_health - int(_monster(actor).health)
		if challenger_damage > incumbent_threat:
			break
	if not _check(
		"higher_threat_switches_live_victim_in_both_subscriptions",
		(
			challenger_damage > incumbent_threat
			and await _wait_until(
				func():
					return (
						str(_monster(observer).attack_target) == observer_id
						and str(_monster(actor).attack_target) == observer_id
						and int(_player(observer, actor_id).health) > 0
						and int(_monster(observer).health) > 0
					),
				5.0
			)
		)
	):
		return false
	observer.disconnect_game()
	if not _check(
		"passive_victim_disconnect_removes_presence",
		await _wait_until(func(): return _player(actor, observer_id).is_empty(), 6.0)
	):
		return false
	var sequence := int(_monster(actor).attack_sequence)
	health = int(_player(actor, actor_id).health)
	await create_timer(4.0).timeout
	return _check(
		"passive_drops_departed_victim_without_attacking_bystander",
		(
			int(_monster(actor).attack_sequence) == sequence
			and int(_player(actor, actor_id).health) == health
		)
	)
