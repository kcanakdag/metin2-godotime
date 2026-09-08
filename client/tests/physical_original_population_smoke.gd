extends "res://tests/physical_population_smoke.gd"
## Initial full-map population, movement and reconnect through two real clients.

var _catalog: Dictionary = {}


func _run() -> void:
	_catalog = JSON.parse_string(FileAccess.get_file_as_string("res://tests/mob-catalog.json"))
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		actor.select_character(actor_id)
		observer.select_character(observer_id)
		ready = await _wait_until(
			func():
				return actor.local_identity == actor_id and observer.local_identity == observer_id,
			5.0
		)
	if ready:
		actor.enter_selected()
		observer.enter_selected()
		ready = _check(
			"original_population_mutual_subscriptions",
			await _wait_until(
				func():
					return (
						actor.state == "connected"
						and observer.state == "connected"
						and not _player(actor, observer_id).is_empty()
						and not _player(observer, actor_id).is_empty()
						and actor.monsters.size() > 2000
						and actor.monsters.size() == observer.monsters.size()
					),
				30.0
			)
		)
	if ready:
		ready = _check(
			"original_population_matching_world",
			(
				actor.world_info == observer.world_info
				and str(actor.world_info.map_id) == "metin2_map_a1"
				and str(actor.world_info.mob_catalog_hash) == str(_catalog.content_hash)
			)
		)
	if ready:
		ready = _population_valid(actor, "actor") and _population_valid(observer, "observer")
	if ready:
		ready = await _move_pair(actor, observer, actor_id, observer_id)
	if ready:
		await _raw_rejection(
			actor,
			"select_combat_target",
			[4294967295, 0],
			[&"U32", &"U32"],
			"unknown_original_target_rejected",
			"target"
		)
		actor.disconnect_game()
		ready = _check(
			"original_disconnect_removes_presence",
			await _wait_until(func(): return _player(observer, actor_id).is_empty(), 5.0)
		)
	if ready:
		ready = await _reconnect_idle(actor, observer, actor_id)
	if ready:
		ready = _population_valid(actor, "reconnected")
		observer.disconnect_game()
		ready = (
			_check(
				"original_peer_disconnect_removes_presence",
				await _wait_until(func(): return _player(actor, observer_id).is_empty(), 5.0)
			)
			and ready
		)
	if not ready:
		_check("original_population_scenario_completed", false)
	_tokens.clear()
	_finish()


func _population_valid(client: GameConnection, label: String) -> bool:
	var ids: Dictionary = {}
	var counts: Dictionary = {}
	var registered: Dictionary = {}
	for mob: Dictionary in _catalog.mobs:
		registered[int(mob.vnum)] = true
	var valid := true
	for mob: Dictionary in client.monsters:
		var id := int(mob.id)
		var vnum := int(mob.definition_vnum)
		if id == 900001:  # Independently authored practice dummy.
			continue
		valid = valid and id > 900001 and not ids.has(id) and registered.has(vnum)
		valid = (
			valid
			and is_finite(float(mob.x))
			and is_finite(float(mob.y))
			and is_finite(float(mob.z))
		)
		ids[id] = true
		counts[vnum] = int(counts.get(vnum, 0)) + 1
	_timing_evidence.append(
		{
			"label": label,
			"count": ids.size(),
			"species_counts": counts,
			"world_info": client.world_info
		}
	)
	return _check(label + "_original_unique_registered_population", valid and ids.size() > 2000)
