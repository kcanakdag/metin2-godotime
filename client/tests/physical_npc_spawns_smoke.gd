extends "res://tests/physical_population_smoke.gd"
## Real authenticated subscriptions: NPC positions persist independently of player sessions.

var _areas: Array = []


func _run() -> void:
	_population = JSON.parse_string(FileAccess.get_file_as_string("res://tests/population.json"))
	var catalog: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://tests/npc-catalog.json")
	)
	_areas = catalog.maps[0].areas
	var actor := _make_client()
	var peer := _make_client()
	var ready := await _create_rosters(actor, peer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var peer_id := str(peer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_population(actor, peer, actor_id, peer_id)
	if ready:
		ready = await _wait_until(
			func():
				return (
					actor.npc_spawns.size() == _areas.size()
					and peer.npc_spawns.size() == _areas.size()
				)
		)
		_check("both_clients_subscribe_all_area_npcs", ready and not _areas.is_empty())
	if ready:
		var baseline := _sorted_spawns(actor)
		print("NPC_SPAWN_SNAPSHOT ", JSON.stringify(baseline))
		_check("same_authoritative_npc_rows_for_both_identities", baseline == _sorted_spawns(peer))
		_check_bounds(baseline)
		ready = await _move_pair(actor, peer, actor_id, peer_id)
		await _raw_rejection(
			actor,
			"interact_npc",
			["spawn.forged", actor.world_info.npc_catalog_hash],
			[&"String", &"String"],
			"forged_npc_rejected_without_reroll",
			"exist"
		)
		await _raw_rejection(
			actor,
			"interact_npc",
			[str(_areas[0].id), "wrong"],
			[&"String", &"String"],
			"stale_npc_catalog_rejected_without_reroll",
			"content"
		)
		_check(
			"movement_and_rejections_preserve_positions",
			baseline == _sorted_spawns(actor) and baseline == _sorted_spawns(peer)
		)
		for index in 2:
			actor.disconnect_game()
			_check(
				"disconnect_clears_local_npc_subscription_%d" % index, actor.npc_spawns.is_empty()
			)
			_check(
				"disconnect_removes_player_presence_%d" % index,
				await _wait_until(func(): return _player(peer, actor_id).is_empty())
			)
			_check(
				"peer_retains_npcs_after_disconnect_%d" % index, baseline == _sorted_spawns(peer)
			)
			actor.connect_account(_server, _database, str(_tokens[0]), "npc-spawn-reconnect")
			ready = await _wait_until(func(): return actor.state == "lobby", 20.0)
			_check("reconnect_restores_private_roster_%d" % index, ready)
			if not ready:
				break
			actor.enter_selected()
			ready = await _wait_until(
				func():
					return (
						actor.state == "connected"
						and not _player(peer, actor_id).is_empty()
						and baseline == _sorted_spawns(actor)
					),
				20.0
			)
			_check("reconnect_restores_exact_persistent_npcs_%d" % index, ready)
			_check(
				"reconnect_does_not_reroll_peer_npcs_%d" % index, baseline == _sorted_spawns(peer)
			)
			if not ready:
				break
		if ready:
			actor.disconnect_game()
			peer.disconnect_game()
			_check(
				"both_disconnect_clear_replica_state",
				actor.npc_spawns.is_empty() and peer.npc_spawns.is_empty()
			)
			await create_timer(0.3).timeout
			actor.connect_account(_server, _database, str(_tokens[0]), "npc-empty-world-reconnect")
			ready = await _wait_until(func(): return actor.state == "lobby", 20.0)
			if ready:
				actor.enter_selected()
				ready = await _wait_until(
					func(): return actor.state == "connected" and baseline == _sorted_spawns(actor),
					20.0
				)
			_check("empty_world_preserves_npc_positions", ready)
	if not ready:
		_check("npc_spawn_scenario_completed", false)
	_tokens.clear()
	_finish()


func _sorted_spawns(client: GameConnection) -> Array:
	var rows := client.npc_spawns.duplicate(true)
	rows.sort_custom(func(a: Dictionary, b: Dictionary): return str(a.spawn_id) < str(b.spawn_id))
	return rows


func _check_bounds(rows: Array) -> void:
	for area: Dictionary in _areas:
		var matches := rows.filter(func(row: Dictionary): return row.spawn_id == area.id)
		if not _check("unique_area_" + str(area.id), matches.size() == 1):
			continue
		var row: Dictionary = matches[0]
		var b: Array = area.bounds_cm
		_check(
			"original_bounds_" + str(area.id),
			(
				row.actor_id == area.actor_id
				and row.map_id == "metin2_map_a1"
				and row.x_cm >= b[0]
				and row.x_cm <= b[2]
				and row.z_cm >= b[1]
				and row.z_cm <= b[3]
				and is_finite(float(row.height_m))
				and row.heading_degrees >= 0
				and row.heading_degrees <= 360
			)
		)
		var expected := fposmod(PI + deg_to_rad(float(row.heading_degrees % 360)), TAU)
		_check(
			"original_heading_" + str(area.id),
			absf(wrapf(float(row.yaw) - expected, -PI, PI)) < 0.00001
		)
