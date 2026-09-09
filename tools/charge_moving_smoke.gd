extends "res://tests/crush_smoke.gd"
## An unprivileged peer provokes and retreats from a live bear; the caster chases.
var _intents: Array[String] = []


func _completed(name: String, succeeded: bool, _timestamp: int) -> void:
	if name in ["begin_charge", "cast_skill"]:
		_intents.append(name + (":ok" if succeeded else ":rejected"))


func _go(client: GameConnection, observer: GameConnection, point: Vector2) -> bool:
	client.move_to(point.x, point.y)
	var arrived := await _wait_until(_arrived.bind(client, observer, point), 12.0)
	client.stop_moving()
	return arrived


func _bear_moved(client: GameConnection, origin: Vector2) -> bool:
	return _xz(_dog(client, 1)).distance_to(origin) > 0.3


func _damaged(first: GameConnection, second: GameConnection, health: int) -> bool:
	return int(_dog(first, 1).health) < health and _dog(first, 1).health == _dog(second, 1).health


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_charge(first):
		return
	var bear := _dog(second, 1).duplicate(true)
	if not _check("moving_original_bear", int(bear.get("definition_vnum", 0)) == 113):
		return
	var origin := _xz(bear)
	if not _check("moving_caster_position", await _go(first, second, origin + Vector2(-7, 0))):
		return
	# Approach from the right so the peer's normal unarmed attack faces the bear.
	if not _check("moving_peer_outer_position", await _go(second, first, origin + Vector2(3, 0))):
		return
	if not _check("moving_peer_attack_position", await _go(second, first, origin + Vector2(1, 0))):
		return
	await _provoke_and_charge(first, second, bear)


func _provoke_and_charge(first: GameConnection, second: GameConnection, bear: Dictionary) -> void:
	var origin := _xz(bear)
	second.perform_attack()
	if not _check(
		"moving_peer_provokes", await _wait_until(_damaged.bind(first, second, int(bear.health)))
	):
		return
	second.move_to(origin.x + 10, origin.y)
	if not _check("moving_live_chase", await _wait_until(_bear_moved.bind(second, origin), 6.0)):
		return
	bear = _dog(second, 1).duplicate(true)
	if not _check(
		"moving_select_exact_life",
		await _raw_success(first, "select_combat_target", [1, bear.life_sequence], [&"U32", &"U32"])
	):
		return
	var driver := ChargeSkillInput.new()
	root.add_child(driver)
	driver.configure(first)
	first.reducer_completed.connect(_completed)
	var sp := int(first.selected_progression().current_sp)
	_check("moving_charge_handled", driver.request(5))
	var max_travel := 0.0
	var deadline := Time.get_ticks_msec() + 6000
	while int(_dog(second, 1).health) == int(bear.health) and Time.get_ticks_msec() < deadline:
		max_travel = maxf(max_travel, _xz(_dog(second, 1)).distance_to(_xz(bear)))
		await create_timer(0.025).timeout
	_check("moving_target_travels_during_approach", max_travel > 0.3)
	_check(
		"moving_damage_shared", await _wait_until(_damaged.bind(first, second, int(bear.health)))
	)
	_check("moving_stun_shared", await _wait_until(_stun_shared.bind(first, second)))
	_check("moving_same_target_life", _dog(second, 1).life_sequence == bear.life_sequence)
	_check("moving_single_payment", int(first.selected_progression().current_sp) == sp - 66)
	await create_timer(0.2).timeout
	_check("moving_one_begin_one_finish", _intents == ["begin_charge:ok", "cast_skill:ok"])
	var health := int(_dog(second, 1).health)
	await create_timer(1.0).timeout
	_check("moving_no_delayed_damage", int(_dog(second, 1).health) == health)
	_check("moving_reservation_cleared", driver._approach.phase == "idle")
	second.stop_moving()
	driver.queue_free()
