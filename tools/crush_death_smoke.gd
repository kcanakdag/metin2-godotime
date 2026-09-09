extends "res://tests/crush_smoke.gd"
## Kill through normal skill damage during stun, then observe the new monster life.


func _prepare_charge(first: GameConnection) -> bool:
	if not await super._prepare_charge(first):
		return false
	await create_timer(1.1).timeout
	first.admin_raise_progression_level(_request_id(), "99")
	if not _check("stun_death_level_setup", await _wait_until(_level_ready.bind(first))):
		return false
	await create_timer(1.1).timeout
	first.admin_set_skill(_request_id(), "2 20")
	return _check("stun_death_finisher_setup", await _wait_until(_finisher_ready.bind(first)))


func _level_ready(first: GameConnection) -> bool:
	return int(first.selected_progression().get("level", 0)) == 99


func _finisher_ready(first: GameConnection) -> bool:
	for row: Dictionary in first.selected_skills():
		if int(row.skill_vnum) == 2 and int(row.rank) == 20:
			return true
	return false


func _dead(first: GameConnection, second: GameConnection) -> bool:
	return int(_dog(first, 1).health) == 0 and int(_dog(second, 1).health) == 0


func _new_life(first: GameConnection, second: GameConnection, old_life: int) -> bool:
	return int(_dog(first, 1).life_sequence) != old_life and _dog(first, 1) == _dog(second, 1)


func _observe(first: GameConnection, second: GameConnection, before: Dictionary) -> void:
	var status := _stun(second).duplicate(true)
	print("STUN_DEATH after_dash_health=", _dog(second, 1).health)
	_check("stun_death_target_survived_dash", int(_dog(second, 1).health) > 0)
	await create_timer(0.85).timeout
	for offset in [-2.7, -2.0]:
		var destination := _xz(_dog(second, 1)) + Vector2(offset, 0.0)
		first.move_to(destination.x, destination.y)
		if not _check(
			"stun_death_approach_%s" % offset,
			await _wait_until(_arrived.bind(first, second, destination), 2.0)
		):
			return
	first.stop_moving()
	print("STUN_DEATH pre_cast=", _geometry(first, second))
	if not _check(
		"stun_death_finisher_cast",
		await _raw_success(first, "cast_skill", [2, first.skill_revision(2)], [&"U16", &"U32"])
	):
		return
	for _frame in 20:
		await create_timer(0.1).timeout
		print("STUN_DEATH frame=", _geometry(first, second))
	var killed := _dead(first, second)
	print("STUN_DEATH after_finisher_health=", _dog(second, 1).health)
	if not _check("stun_death_both_clients", killed):
		return
	var dead := _dog(second, 1).duplicate(true)
	_check("stun_death_before_expiry", int(dead.action_started_at_us) < int(status.expires_at_us))
	_check("stun_death_clears_both", await _wait_until(_stun_gone.bind(first, second)))
	_check(
		"stun_death_respawns_new_life",
		await _wait_until(_new_life.bind(first, second, int(before.life_sequence)), 14.0)
	)
	_check("stun_death_no_restored_stun", _stun_gone(first, second))
	_check("stun_death_respawn_full_health", int(_dog(second, 1).health) == 845)


func _geometry(first: GameConnection, second: GameConnection) -> Dictionary:
	var actor := _player_row(second, first.local_identity)
	var bear := _dog(second, 1)
	return {
		"actor": _xz(actor),
		"heading": actor.heading,
		"activity": actor.activity,
		"bear": _xz(bear),
		"health": bear.health
	}
