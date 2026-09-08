extends "res://tests/progression_admin_smoke.gd"
## Batch acceptance of selected skills through two real authenticated clients.


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_three_way_cut(first):
		return
	# Respect the shared one-second operator mutation rate after level-five setup.
	await create_timer(1.1).timeout
	first.admin_raise_progression_level(_request_id(), "8")
	if not _check(
		"batch_level_eight",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 8)
	):
		return
	for vnum in [2, 16, 17]:
		_check(
			"batch_learn_%d" % vnum,
			await _raw_success(first, "learn_skill", [vnum, 0], [&"U16", &"U32"])
		)
		_check(
			"batch_rank_%d" % vnum, await _wait_until(func(): return first.skill_revision(vnum) > 0)
		)
	if not _check(
		"batch_dummy_subscribed",
		await _wait_until(func(): return not _dog(second, 900001).is_empty())
	):
		return
	for specification in [[1, 3], [2, 1], [16, 1], [17, 1]]:
		await _cast_one(first, second, int(specification[0]), int(specification[1]))


func _cast_one(first: GameConnection, second: GameConnection, vnum: int, hits: int) -> void:
	var before := _dog(second, 900001).duplicate(true)
	for offset in [-2.7, -2.0]:
		var destination := _xz(before) + Vector2(offset, 0.0)
		first.move_to(destination.x, destination.y)
		if not _check(
			"batch_%d_approach_%s" % [vnum, offset],
			await _wait_until(
				func():
					return (
						_xz(_player_row(second, first.local_identity)).distance_to(destination)
						< 0.1
					),
				15.0
			)
		):
			return
	first.stop_moving()
	_check(
		"batch_%d_target" % vnum,
		await _raw_success(
			first, "select_combat_target", [900001, before.life_sequence], [&"U32", &"U32"]
		)
	)
	if not _check(
		"batch_%d_cast" % vnum,
		await _raw_success(
			first, "cast_skill", [vnum, first.skill_revision(vnum)], [&"U16", &"U32"]
		)
	):
		return
	var histories: Array = [[int(before.health)], [int(before.health)]]
	for _tick in 120:
		for index in 2:
			var connection := first if index == 0 else second
			var health := int(_dog(connection, 900001).health)
			if health != int(histories[index][-1]):
				histories[index].append(health)
		await create_timer(0.02).timeout
	_check(
		"batch_%d_hit_count" % vnum,
		histories[0].size() == hits + 1 and histories[1].size() == hits + 1
	)
	_check("batch_%d_same_history" % vnum, histories[0] == histories[1])
	_check(
		"batch_%d_life_preserved" % vnum, _dog(second, 900001).life_sequence == before.life_sequence
	)
	_check(
		"batch_%d_cooldown" % vnum,
		not await _raw_success(
			first, "cast_skill", [vnum, first.skill_revision(vnum)], [&"U16", &"U32"]
		)
	)
	print("SKILL_BATCH_EVIDENCE ", JSON.stringify({"vnum": vnum, "health": histories}))
