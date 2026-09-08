extends "res://tests/progression_admin_smoke.gd"
## Real original mob stats, authoritative damage, flinches, force and recovery.


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	var skill := int(_config.get("reaction_skill", 1))
	var expected: Dictionary = {
		1: {"hits": 3, "good": true, "push": 0.392},
		16: {"hits": 1, "good": false, "push": 3.675},
		17: {"hits": 1, "good": false, "push": 0.0},
	}[skill]
	if not await _prepare_three_way_cut(first):
		return
	if skill != 1:
		await create_timer(1.1).timeout
		first.admin_raise_progression_level(_request_id(), "6")
		if not _check(
			"reaction_level_six",
			await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 6)
		):
			return
		if not _check(
			"reaction_learn_skill",
			await _raw_success(first, "learn_skill", [skill, 0], [&"U16", &"U32"])
		):
			return
		_check(
			"reaction_skill_rank", await _wait_until(func(): return first.skill_revision(skill) > 0)
		)
	if not _check(
		"reaction_mob_subscribed",
		await _wait_until(func(): return not second.monsters_for_definition(106).is_empty())
	):
		return
	var mob_id := int(second.monsters_for_definition(106)[0].id)
	var before := _dog(second, mob_id).duplicate(true)
	_check("original_mob_health", int(before.max_health) == 412)
	for offset in [-2.7, -2.0]:
		var destination := _xz(before) + Vector2(offset, 0.0)
		first.move_to(destination.x, destination.y)
		if not _check(
			"reaction_approach_%s_replicates" % offset,
			await _wait_until(
				func():
					return (
						_xz(_player_row(second, first.local_identity)).distance_to(destination)
						< 0.15
					),
				15.0
			)
		):
			return
	first.stop_moving()
	_check(
		"reaction_target_selected",
		await _raw_success(
			first, "select_combat_target", [mob_id, before.life_sequence], [&"U32", &"U32"]
		)
	)
	if not _check(
		"reaction_cast_accepted",
		await _raw_success(
			first, "cast_skill", [skill, first.skill_revision(skill)], [&"U16", &"U32"]
		)
	):
		return
	var histories: Array = [[int(before.health)], [int(before.health)]]
	var actions: Array = [[], []]
	var displacement := [0.0, 0.0]
	var recovered := [false, false]
	var deadline := Time.get_ticks_msec() + 8000
	while Time.get_ticks_msec() < deadline:
		for index in 2:
			var connection := first if index == 0 else second
			var row := _dog(connection, mob_id)
			var health := int(row.health)
			if health != int(histories[index][-1]):
				histories[index].append(health)
			var action := str(row.attack_action_id)
			if not actions[index].has(action):
				actions[index].append(action)
			displacement[index] = maxf(displacement[index], _xz(row).x - _xz(before).x)
			if (
				actions[index].any(func(value): return "knockdown" in value)
				and int(row.activity) == 0
			):
				recovered[index] = true
		if recovered[0] and recovered[1]:
			break
		await create_timer(0.02).timeout
	_check(
		"reaction_expected_hits_both_clients",
		(
			histories[0].size() == int(expected.hits) + 1
			and histories[1].size() == int(expected.hits) + 1
		)
	)
	_check("reaction_matching_damage_history", histories[0] == histories[1])
	for index in 2:
		if expected.good:
			_check(
				"reaction_good_clip_%d" % index,
				actions[index].any(func(value): return "damage" in value)
			)
		_check(
			"reaction_great_clip_%d" % index,
			actions[index].any(func(value): return "knockdown" in value)
		)
		_check(
			"reaction_force_endpoint_%d" % index,
			absf(displacement[index] - float(expected.push)) < 0.05
		)
		_check("reaction_recovers_%d" % index, recovered[index])
	_check(
		"reaction_mob_survives_same_life",
		(
			int(_dog(second, mob_id).health) > 0
			and _dog(second, mob_id).life_sequence == before.life_sequence
		)
	)
	print(
		"REACTION_EVIDENCE ",
		JSON.stringify(
			{
				"skill_vnum": skill,
				"health": histories,
				"actions": actions,
				"peak_push_m": displacement,
				"recovered": recovered
			}
		)
	)
