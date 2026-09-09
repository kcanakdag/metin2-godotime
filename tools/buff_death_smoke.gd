extends "res://tests/buff_smoke.gd"
## A normal monster defeats the buffed player; no health or damage mutation bypass.


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not _check("death_fixture_rank_one", int(_buff_skill(first).get("rank", 0)) == 1):
		return
	var identity := first.local_identity
	var dog := _dog(second, 1)
	if not _check("death_fixture_living_dog", not dog.is_empty() and int(dog.health) > 0):
		return
	var destination := _xz(dog) + Vector2(-1.0, 0.0)
	first.move_to(destination.x, destination.y)
	if not _check(
		"death_fixture_approach", await _wait_until(_near.bind(second, identity, destination), 10.0)
	):
		return
	first.stop_moving()
	first.select_combat_target(1, int(dog.life_sequence))
	await create_timer(0.2).timeout
	_check("provoke_normal_retaliation", await _raw_success(first, "perform_attack", [], []))
	if not _check(
		"normal_combat_lowers_health", await _wait_until(_low_health.bind(second, identity), 75.0)
	):
		print("BUFF_DEATH health=", _player_row(second, identity).get("health"))
		return
	var life := int(_player_row(second, identity).life_sequence)
	var base := first.selected_progression().duplicate(true)
	var vnum := _buff_vnum()
	if not _check(
		"low_health_buff_cast",
		await _raw_success(
			first, "cast_skill", [vnum, first.skill_revision(vnum)], [&"U16", &"U32"]
		)
	):
		return
	_check("low_health_buff_projection", await _wait_until(_buff_projection.bind(first, base)))
	var cast_at := Time.get_ticks_msec()
	if not _check(
		"buff_owner_defeated", await _wait_until(_dead.bind(first, second, identity), 25.0)
	):
		return
	_check(
		"death_before_buff_expiry",
		Time.get_ticks_msec() - cast_at < int(_buff_config().get("duration_ticks", 0)) * 1000
	)
	_check("death_removes_buff_projection", await _wait_until(_base_projection.bind(first, base)))
	_check("respawn_new_life", await _wait_until(_respawned.bind(second, identity, life), 12.0))
	_check("respawn_does_not_restore_buff", _base_projection(first, base))


func _near(client: GameConnection, identity: String, position: Vector2) -> bool:
	return _xz(_player_row(client, identity)).distance_to(position) < 0.15


func _low_health(client: GameConnection, identity: String) -> bool:
	var hp := int(_player_row(client, identity).get("health", 0))
	return hp > 0 and hp <= 60


func _dead(first: GameConnection, second: GameConnection, identity: String) -> bool:
	return (
		int(_player_row(first, identity).get("health", -1)) == 0
		and int(_player_row(second, identity).get("health", -1)) == 0
	)


func _respawned(client: GameConnection, identity: String, old_life: int) -> bool:
	var row := _player_row(client, identity)
	return int(row.get("life_sequence", old_life)) > old_life and int(row.get("health", 0)) > 0
