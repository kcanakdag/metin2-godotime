extends "res://tests/charge_smoke.gd"
## Live imported Brown Bear CRUSH fixture; never substitute the stationary dummy.


func _stun(client: GameConnection) -> Dictionary:
	for row: Dictionary in client.monster_stuns:
		if int(row.monster_id) == 1:
			return row
	return {}


func _stun_shared(first: GameConnection, second: GameConnection) -> bool:
	return not _stun(first).is_empty() and _stun(first) == _stun(second)


func _stun_gone(first: GameConnection, second: GameConnection) -> bool:
	return _stun(first).is_empty() and _stun(second).is_empty()


func _arrived(first: GameConnection, second: GameConnection, destination: Vector2) -> bool:
	return _xz(_player_row(second, first.local_identity)).distance_to(destination) < 0.1


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_charge(first):
		return
	var before := _dog(second, 1).duplicate(true)
	if not _check(
		"crush_original_brown_bear",
		int(before.get("definition_vnum", 0)) == 113 and int(before.get("health", 0)) == 845
	):
		return
	var destination := _xz(before) + Vector2(-1.0, 0.0)
	first.move_to(destination.x, destination.y)
	if not _check(
		"crush_approach", await _wait_until(_arrived.bind(first, second, destination), 15.0)
	):
		return
	first.stop_moving()
	if not _check(
		"crush_target",
		await _raw_success(
			first, "select_combat_target", [1, before.life_sequence], [&"U32", &"U32"]
		)
	):
		return
	if not _check(
		"crush_cast",
		await _raw_success(first, "cast_skill", [5, first.skill_revision(5)], [&"U16", &"U32"])
	):
		return
	if not _check("crush_stun_shared", await _wait_until(_stun_shared.bind(first, second))):
		return
	await _observe(first, second, before)


func _observe(first: GameConnection, second: GameConnection, before: Dictionary) -> void:
	var after := _dog(second, 1).duplicate(true)
	var status := _stun(second).duplicate(true)
	_check(
		"crush_target_survives_damage",
		int(after.health) > 0 and int(after.health) < int(before.health)
	)
	_check(
		"crush_exact_life",
		after.life_sequence == before.life_sequence and status.life_sequence == before.life_sequence
	)
	_check("crush_four_seconds", int(status.expires_at_us) - int(status.starts_at_us) == 4000000)
	_check("crush_two_metre_push", absf(_xz(after).distance_to(_xz(before)) - 2.0) < 0.03)
	_check("crush_position_shared", _xz(_dog(first, 1)).distance_to(_xz(after)) < 0.01)
	var health := int(_player_row(second, first.local_identity).health)
	var sequence := int(after.attack_sequence)
	await create_timer(2.0).timeout
	_check("crush_stun_holds_position", _xz(_dog(second, 1)).distance_to(_xz(after)) < 0.01)
	_check(
		"crush_stun_stops_attack",
		int(_dog(second, 1).attack_sequence) == sequence and int(_dog(second, 1).activity) == 0
	)
	_check(
		"crush_stun_no_player_damage",
		int(_player_row(second, first.local_identity).health) == health
	)
	_check("crush_expiry_shared", await _wait_until(_stun_gone.bind(first, second), 4.0))
	_check("crush_ai_resumes", await _wait_until(_resumed.bind(second, _xz(after), sequence), 5.0))


func _resumed(client: GameConnection, pushed: Vector2, sequence: int) -> bool:
	return (
		_xz(_dog(client, 1)).distance_to(pushed) > 0.2
		or int(_dog(client, 1).attack_sequence) > sequence
	)
