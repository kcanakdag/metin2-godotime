extends "res://tests/combo_smoke.gd"
## Authored populations exercise ordinary combat and lifecycle through real subscriptions.

var _population: Dictionary = {}


func _run() -> void:
	_population = JSON.parse_string(FileAccess.get_file_as_string("res://tests/population.json"))
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_population(actor, observer, actor_id, observer_id)
	if ready:
		ready = _homes_match(actor, "actor_initial") and _homes_match(observer, "peer_initial")
	if ready:
		ready = await _move_pair(actor, observer, actor_id, observer_id)
	if ready:
		await _raw_rejection(
			actor,
			"select_combat_target",
			[4294967295, 0],
			[&"U32", &"U32"],
			"unknown_population_target_rejected",
			"target"
		)
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = await _hunt_first_spawn(actor, observer, actor_id)
	if ready:
		ready = await _population_lifecycle(actor, observer, actor_id, observer_id)
	if not ready:
		_check("population_scenario_completed", false)
	_tokens.clear()
	_finish()


func _monster(client: GameConnection) -> Dictionary:
	var id := int(_population.spawns[0].id)
	for row: Dictionary in client.monsters:
		if int(row.id) == id:
			return row
	return {}


func _homes_match(client: GameConnection, label: String) -> bool:
	if not _check(
		label + "_exact_spawn_count", client.monsters.size() == _population.spawns.size()
	):
		return false
	for expected: Dictionary in _population.spawns:
		var rows := client.monsters.filter(
			func(row: Dictionary): return int(row.id) == int(expected.id)
		)
		if not _check(label + "_unique_id_%d" % int(expected.id), rows.size() == 1):
			return false
		var row: Dictionary = rows[0]
		if not _check(
			label + "_trusted_home_%d" % int(expected.id),
			(
				int(row.definition_vnum) == int(expected.definition_vnum)
				and (
					Vector3(float(row.x), float(row.y), float(row.z)).distance_to(
						Vector3(float(expected.x), float(expected.y), float(expected.z))
					)
					< 0.01
				)
			)
		):
			return false
	return true


func _enter_population(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	actor.select_character(actor_id)
	observer.select_character(observer_id)
	var selected := await _wait_until(
		func(): return actor.local_identity == actor_id and observer.local_identity == observer_id,
		5.0
	)
	if not _check("population_characters_selected", selected):
		return false
	actor.enter_selected()
	observer.enter_selected()
	var entered := await _wait_until(
		func():
			return (
				actor.state == "connected"
				and observer.state == "connected"
				and not _player(actor, observer_id).is_empty()
				and not _player(observer, actor_id).is_empty()
				and actor.monsters.size() == _population.spawns.size()
				and observer.monsters.size() == _population.spawns.size()
			),
		20.0
	)
	if not _check("population_mutual_subscriptions", entered):
		return false
	return _check(
		"population_map_protocol_definitions",
		(
			actor.world_info == observer.world_info
			and str(actor.world_info.map_id) == _population.map_id
			and str(actor.world_info.content_hash) == _population.map_content_hash
			and str(actor.world_info.definition_hash) == _expected_definition_hash
			and int(actor.world_info.protocol_version) == GameConnection.EXPECTED_PROTOCOL_VERSION
		)
	)


func _move_pair(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	var actor_before := _position(_player(observer, actor_id))
	var peer_before := _position(_player(actor, observer_id))
	actor.set_move_input(0.0, 1.0)
	observer.set_move_input(-1.0, 0.0)
	await create_timer(0.35).timeout
	actor.stop_moving()
	observer.stop_moving()
	var moved := await _wait_until(
		func():
			return (
				_position(_player(observer, actor_id)).distance_to(actor_before) > 0.5
				and _position(_player(actor, observer_id)).distance_to(peer_before) > 0.5
			),
		3.0
	)
	return _check("population_two_way_remote_movement", moved)


func _hunt_first_spawn(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	var dog := _monster(observer)
	actor.select_combat_target(int(dog.id), int(dog.life_sequence))
	if not await _wait_until(func(): return not actor.selected_combat_target().is_empty(), 3.0):
		return _check("population_live_target_selected", false)
	for index in 8:
		if int(_monster(observer).health) == 0:
			break
		if not await _population_hit(actor, observer, actor_id, index):
			return false
	var rewarded := await _wait_until(
		func():
			return (
				int(_monster(observer).health) == 0
				and int(_monster(actor).health) == 0
				and _has_experience(actor, actor_id, 15)
			),
		3.0
	)
	if not _check("population_kill_seen_by_both_and_rewarded_once", rewarded):
		return false
	for row: Dictionary in observer.monsters:
		if int(row.id) != int(dog.id):
			_check(
				"population_other_life_unchanged_%d" % int(row.id),
				int(row.health) == 100 and int(row.life_sequence) == 0
			)
	return true


func _population_hit(
	actor: GameConnection, observer: GameConnection, actor_id: String, index: int
) -> bool:
	var before := int(_monster(observer).health)
	var action := await _start_action(
		actor, observer, actor_id, COMBO_ONE, "population_attack_%d" % index
	)
	if action.is_empty():
		return false
	var hit := await _wait_until(func(): return int(_monster(observer).health) < before, 2.0)
	if not _check("population_damage_%d" % index, hit):
		return false
	var damage := before - int(_monster(observer).health)
	if not _check(
		"population_formula_%d" % index,
		damage in [17, 18, 20] or (int(_monster(observer).health) == 0 and damage <= 20)
	):
		return false
	if not await _wait_action_end(observer, actor_id, int(action.action_ends_at_us)):
		return false
	await create_timer(0.1).timeout
	return true


func _population_lifecycle(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	var life := int(_monster(observer).life_sequence)
	actor.move_to(660.0, 575.0)
	if not await _wait_until(
		func(): return _position(_player(observer, actor_id)).distance_to(Vector2(660, 575)) < 0.4,
		10.0
	):
		return _check("population_return_to_safe_town", false)
	actor.disconnect_game()
	if not _check(
		"population_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty(), 5.0)
	):
		return false
	var respawned := await _wait_until(
		func():
			return (
				int(_monster(observer).life_sequence) == life + 1
				and int(_monster(observer).health) == 100
			),
		16.0
	)
	if (
		not _check("population_respawn_new_life", respawned)
		or not _homes_match(observer, "respawn")
	):
		return false
	if not await _reconnect_idle(actor, observer, actor_id):
		return false
	if (
		not _homes_match(actor, "reconnect")
		or not _check("population_reconnect_no_reward_replay", _has_experience(actor, actor_id, 15))
	):
		return false
	observer.disconnect_game()
	return _check(
		"population_peer_disconnect_removes_presence",
		await _wait_until(func(): return _player(actor, observer_id).is_empty(), 5.0)
	)
