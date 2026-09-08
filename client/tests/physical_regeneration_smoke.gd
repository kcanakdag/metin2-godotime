extends "res://tests/physical_combat_smoke.gd"
## Normal combat against the allocated two-member regeneration fixture.


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_physical_world(actor, observer, actor_id, observer_id, 2)
	if ready:
		ready = _check(
			"regeneration_fixture_marker",
			str(actor.world_info.content_hash) == "training-v7-regenerating-area-wild-dog-v1"
		)
	if ready:
		_timing_evidence.append(
			{
				"world_info": actor.world_info.duplicate(true),
				"initial_mobs": actor.monsters.duplicate(true)
			}
		)
		var position := _position(_monster(observer))
		ready = _check(
			"leader_sampled_inside_authored_area",
			position.x >= 7.5 and position.x <= 8.5 and position.y >= 7.5 and position.y <= 8.5
		)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = await _replace_leader(actor, observer, actor_id)
	if not ready:
		_check("regeneration_scenario_completed", false)
	_tokens.clear()
	_finish()


func _replace_leader(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	for index in range(8):
		if int(_monster(observer).health) == 0:
			break
		if not await _physical_hit(actor, observer, actor_id, false, "leader_hit_%d" % index):
			return false
	if not _check("leader_died_before_destruction", int(_monster(observer).health) == 0):
		return false
	if not _check(
		"corpse_retains_group_capacity",
		(
			actor.monsters_for_definition(101).size() == 2
			and observer.monsters_for_definition(101).size() == 2
		)
	):
		return false
	if not _check(
		"replacement_preserves_follower_and_uses_new_ids_on_both_clients",
		await _wait_until(
			func(): return _replacement_ids(actor) and _replacement_ids(observer), 20.0
		)
	):
		return false
	await _raw_rejection(
		actor,
		"select_combat_target",
		[900002, 0],
		[&"U32", &"U32"],
		"destroyed_leader_cannot_be_selected",
		"exist"
	)
	var observer_id := str(observer.local_identity)
	observer.disconnect_game()
	if not _check(
		"observer_disconnect_removes_presence_without_removing_group",
		(
			await _wait_until(func(): return _player(actor, observer_id).is_empty())
			and _replacement_ids(actor)
		)
	):
		return false
	return await _reconnect_group(actor, observer, observer_id)


func _reconnect_group(actor: GameConnection, observer: GameConnection, observer_id: String) -> bool:
	observer.connect_account(_server, _database, str(_tokens[1]), "regeneration-reconnect")
	if not _check(
		"regeneration_reconnect_lobby",
		await _wait_until(func(): return observer.state == "lobby", 20.0)
	):
		return false
	observer.enter_selected()
	return _check(
		"regeneration_reconnect_preserves_survivor_and_replacement",
		await _wait_until(
			func():
				return (
					observer.state == "connected"
					and not _player(actor, observer_id).is_empty()
					and _replacement_ids(actor)
					and _replacement_ids(observer)
				),
			20.0
		)
	)


func _replacement_ids(client: GameConnection) -> bool:
	var ids: Array[int] = []
	for mob: Dictionary in client.monsters_for_definition(101):
		if int(mob.health) <= 0 or int(mob.life_sequence) != 0:
			return false
		ids.append(int(mob.id))
	ids.sort()
	return ids == [900003, 900004, 900005]


func _monster(client: GameConnection) -> Dictionary:
	for mob: Dictionary in client.monsters_for_definition(101):
		if int(mob.id) == 900002:
			return mob
	return {}
