extends "res://tests/physical_combat_smoke.gd"
## Two ordinary accounts verify item-definition effects on an isolated recovery fixture.

var _recovery_samples: Array = []
var _capture_recovery := false


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
			"recovery_test_fixture", actor.world_info.content_hash == "training-item-recovery-v1"
		)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _move_far_from_dog(actor, observer, actor_id)
	if ready:
		ready = await _prove_two_way_movement(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _reject_invalid_uses(actor, observer, actor_id)
	if ready:
		observer.players_changed.connect(func(_rows: Array): _record_recovery(observer, actor_id))
		ready = await _receive_ordinary_damage(actor, observer, actor_id, 300)
	if ready:
		ready = await _verify_recovery(actor, observer, actor_id, 27001, 300)
	if ready:
		ready = await _verify_recovery(actor, observer, actor_id, 27002, 800)
	if ready:
		ready = await _receive_ordinary_damage(actor, observer, actor_id, 650)
	if ready:
		ready = await _verify_recovery_disconnect(actor, observer, actor_id)
	if not ready:
		_check("recovery_scenario_completed", false)
	_tokens.clear()
	_finish()


func _potion(client: GameConnection, vnum: int) -> Dictionary:
	for row: Dictionary in client.inventory:
		if int(row.vnum) == vnum and str(row.owner) == client.local_identity:
			return row
	return {}


func _health(client: GameConnection, identity: String) -> int:
	return int(_player(client, identity).get("health", -1))


func _reject_invalid_uses(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var potion := _potion(actor, 27001)
	var observer_id := str(observer.local_identity)
	if _health(observer, observer_id) < int(_player(observer, observer_id).max_health):
		if not await _raw_success(
			observer,
			"use_item",
			[int(_potion(observer, 27002).id)],
			[&"U64"],
			"prepare_observer_health"
		):
			return false
		if not _check(
			"observer_reaches_full_health",
			await _wait_until(
				func():
					return (
						_health(observer, observer_id)
						== int(_player(observer, observer_id).max_health)
					),
				18.0
			)
		):
			return false
		await create_timer(1.3).timeout
	var full_potion := _potion(observer, 27001)
	if not _check(
		"both_recovery_definitions_available",
		not potion.is_empty() and not _potion(actor, 27002).is_empty()
	):
		return false
	await _raw_rejection(
		observer, "use_item", [int(full_potion.id)], [&"U64"], "full_health_rejects_potion", "full"
	)
	await _raw_rejection(
		observer, "use_item", [int(potion.id)], [&"U64"], "foreign_potion_rejected", "another"
	)
	await _raw_rejection(
		actor,
		"use_item",
		[int(_owned_sword(actor, actor_id).id)],
		[&"U64"],
		"weapon_not_consumable",
		"consumed"
	)
	await _raw_rejection(actor, "use_item", [0], [&"U64"], "missing_item_rejected", "exist")
	return _check(
		"rejected_use_preserves_private_stack",
		(
			int(_potion(actor, 27001).count) == int(potion.count)
			and int(_potion(observer, 27001).count) == int(full_potion.count)
			and _private_inventory(actor)
			and _private_inventory(observer)
		)
	)


func _receive_ordinary_damage(
	actor: GameConnection, observer: GameConnection, actor_id: String, maximum: int
) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	if not _check(
		"ordinary_damage_creates_recovery_deficit",
		await _wait_until(
			func():
				return _health(observer, actor_id) <= maximum and _health(observer, actor_id) > 0,
			50.0
		)
	):
		return false
	return await _move_far_from_dog(actor, observer, actor_id)


func _record_recovery(client: GameConnection, actor_id: String) -> void:
	if not _capture_recovery:
		return
	var health := _health(client, actor_id)
	if (
		health < 0
		or (not _recovery_samples.is_empty() and int(_recovery_samples.back().health) == health)
	):
		return
	_recovery_samples.append({"health": health, "server_time_us": client.server_time_us})


func _verify_recovery(
	actor: GameConnection, observer: GameConnection, actor_id: String, vnum: int, amount: int
) -> bool:
	var before := _health(observer, actor_id)
	var maximum := int(_player(observer, actor_id).max_health)
	var potion := _potion(actor, vnum)
	var count := int(potion.count)
	_recovery_samples.clear()
	_capture_recovery = true
	var accepted := await _raw_result(actor, "use_item", [int(potion.id)], [&"U64"])
	_record_raw_result("recovery_%d" % vnum, "use_item", accepted)
	if not _check("recovery_%d_accepted" % vnum, bool(accepted.accepted)):
		return false
	await create_timer(0.25).timeout
	if not _check(
		"recovery_%d_not_instant" % vnum,
		_health(actor, actor_id) == before and _health(observer, actor_id) == before
	):
		return false
	if amount > maximum - before:
		await _raw_rejection(
			actor,
			"use_item",
			[int(potion.id)],
			[&"U64"],
			"full_pending_pool_rejects_repeat",
			"recovering"
		)
	var expected := mini(maximum, before + amount)
	var reached := await _wait_until(
		func():
			return _health(actor, actor_id) == expected and _health(observer, actor_id) == expected,
		18.0
	)
	_capture_recovery = false
	_timing_evidence.append(
		{
			"phase": "item_recovery",
			"vnum": vnum,
			"amount": amount,
			"before": before,
			"expected": expected,
			"accepted_at_us": int(accepted.timestamp),
			"samples": _recovery_samples.duplicate(true)
		}
	)
	if not _check("recovery_%d_total_on_both_clients" % vnum, reached):
		return false
	var previous := before
	var step := int(floor(maximum * 7.0 / 100.0))
	var previous_time := int(accepted.timestamp)
	var samples_valid := not _recovery_samples.is_empty()
	for sample: Dictionary in _recovery_samples:
		samples_valid = samples_valid and int(sample.health) == mini(expected, previous + step)
		samples_valid = samples_valid and int(sample.server_time_us) >= previous_time + 900_000
		previous = int(sample.health)
		previous_time = int(sample.server_time_us)
	if not _check("recovery_%d_source_tick_amount_and_cadence" % vnum, samples_valid):
		return false
	if not _check(
		"recovery_%d_consumed_exactly_once" % vnum, int(_potion(actor, vnum).count) == count - 1
	):
		return false
	await create_timer(1.3).timeout
	return _check(
		"recovery_%d_has_no_extra_healing" % vnum,
		_health(observer, actor_id) == expected and _health(actor, actor_id) == expected
	)


func _verify_recovery_disconnect(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var before := _health(observer, actor_id)
	var potion := _potion(actor, 27001)
	if not await _raw_success(
		actor, "use_item", [int(potion.id)], [&"U64"], "pending_recovery_before_disconnect"
	):
		return false
	actor.disconnect_game()
	if not _check(
		"recovery_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty(), 5.0)
	):
		return false
	await create_timer(1.3).timeout
	actor.connect_account(_server, _database, str(_tokens[0]), "recovery-reconnect")
	if not _check(
		"recovery_reconnect_lobby", await _wait_until(func(): return actor.state == "lobby", 20.0)
	):
		return false
	actor.enter_selected()
	if not _check(
		"recovery_reconnect_presence",
		await _wait_until(
			func():
				return actor.state == "connected" and not _player(observer, actor_id).is_empty(),
			20.0
		)
	):
		return false
	await create_timer(1.5).timeout
	return _check(
		"recovery_disconnect_does_not_replay_or_refund",
		(
			_health(actor, actor_id) == before
			and _health(observer, actor_id) == before
			and int(_potion(actor, 27001).count) == int(potion.count) - 1
		)
	)
