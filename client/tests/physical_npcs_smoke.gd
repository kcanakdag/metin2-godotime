extends "res://tests/physical_population_smoke.gd"
## Live ordinary-account NPC authorization, private subscriptions and lifecycle.

const NPC_ID := "spawn.yongan.city-guard-20354"


func _run() -> void:
	_population = JSON.parse_string(FileAccess.get_file_as_string("res://tests/population.json"))
	var actor := _make_client()
	var peer := _make_client()
	var ready := await _create_rosters(actor, peer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var peer_id := str(peer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_population(actor, peer, actor_id, peer_id)
	if ready:
		await _raw_rejection(
			actor,
			"interact_npc",
			[NPC_ID, "wrong"],
			[&"String", &"String"],
			"stale_catalog_rejected",
			"content"
		)
		await _raw_rejection(
			actor,
			"interact_npc",
			["spawn.forged", actor.world_info.npc_catalog_hash],
			[&"String", &"String"],
			"forged_npc_rejected",
			"exist"
		)
		await _raw_rejection(
			actor,
			"interact_npc",
			[NPC_ID, actor.world_info.npc_catalog_hash],
			[&"String", &"String"],
			"remote_interaction_rejected",
			"closer"
		)
		ready = await _walk_to_guard(actor, peer, actor_id, peer_id)
	if ready:
		ready = await _conversation_checks(actor, peer, actor_id)
	if ready:
		ready = await _conversation_lifecycle(actor, peer, actor_id, peer_id)
	_check("npc_scenario_completed", ready)
	_tokens.clear()
	_finish()


func _walk_to_guard(
	actor: GameConnection, peer: GameConnection, actor_id: String, peer_id: String
) -> bool:
	var route: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://tests/npc-route.json")
	)
	for index in range(1, route.waypoints.size()):
		var point := Vector2(route.waypoints[index][0], route.waypoints[index][1])
		actor.move_to(point.x, point.y)
		peer.move_to(point.x, point.y)
		if not _check(
			"npc_two_way_route_%d" % index,
			await _wait_until(
				func():
					return (
						_position(_player(peer, actor_id)).distance_to(point) < 0.15
						and _position(_player(actor, peer_id)).distance_to(point) < 0.15
					),
				15.0
			)
		):
			return false
	# Five-meter source click distance; stand safely inside its boundary.
	actor.move_to(604, 667)
	peer.move_to(606, 667)
	return _check(
		"both_reach_interaction_range",
		await _wait_until(
			func():
				return (
					_position(_player(peer, actor_id)).distance_to(Vector2(604, 667)) < 0.1
					and _position(_player(actor, peer_id)).distance_to(Vector2(606, 667)) < 0.1
				),
			5.0
		)
	)


func _open(client: GameConnection, label: String) -> bool:
	client.interact_npc(NPC_ID)
	return _check(
		label, await _wait_until(func(): return client.npc_interaction.get("spawn_id") == NPC_ID)
	)


func _raw_rows(client: GameConnection) -> Array:
	return client._client.get_local_database().get_all_rows("npc_interaction")


func _conversation_checks(actor: GameConnection, peer: GameConnection, actor_id: String) -> bool:
	if not await _open(actor, "owner_receives_server_dialogue"):
		return false
	var first := actor.npc_interaction.duplicate(true)
	_check(
		"dialogue_belongs_to_active_owner",
		(
			first.account == actor.account_identity
			and first.character_id == actor_id
			and first.title == "City Guard"
		)
	)
	_check("other_account_subscription_has_no_dialogue_rows", _raw_rows(peer).is_empty())
	await _raw_rejection(
		peer,
		"close_npc_interaction",
		[int(first.session_id)],
		[&"U64"],
		"foreign_session_close_rejected",
		"closed"
	)
	actor.interact_npc(NPC_ID)
	await create_timer(0.2).timeout
	_check("duplicate_open_preserves_session_and_expiry", actor.npc_interaction == first)
	if not await _open(peer, "second_account_can_talk_independently"):
		return false
	_check(
		"both_raw_subscriptions_remain_owner_private",
		(
			_raw_rows(actor).size() == 1
			and _raw_rows(peer).size() == 1
			and int(peer.npc_interaction.session_id) != int(first.session_id)
		)
	)
	actor.close_npc_interaction(int(first.session_id))
	if not _check(
		"exact_session_close_removes_row",
		await _wait_until(func(): return actor.npc_interaction.is_empty())
	):
		return false
	if not await _open(actor, "reopen_allocates_new_session"):
		return false
	var second := actor.npc_interaction.duplicate(true)
	_check("session_ids_are_not_reused", int(second.session_id) > int(first.session_id))
	await _raw_rejection(
		actor,
		"close_npc_interaction",
		[int(first.session_id)],
		[&"U64"],
		"stale_close_cannot_close_new_session",
		"current"
	)
	_check("stale_close_preserves_current_row", actor.npc_interaction == second)
	return await _conversation_actions(actor, peer)


func _conversation_actions(actor: GameConnection, peer: GameConnection) -> bool:
	actor.set_move_input(1, 0)
	if not _check(
		"movement_closes_only_own_dialogue",
		await _wait_until(
			func(): return actor.npc_interaction.is_empty() and not peer.npc_interaction.is_empty()
		)
	):
		return false
	actor.stop_moving()
	if not await _open(actor, "can_reopen_after_movement"):
		return false
	actor.perform_attack()
	if not _check(
		"ordinary_attack_closes_dialogue",
		await _wait_until(func(): return actor.npc_interaction.is_empty())
	):
		return false
	await _raw_rejection(
		actor,
		"interact_npc",
		[NPC_ID, actor.world_info.npc_catalog_hash],
		[&"String", &"String"],
		"talk_during_attack_rejected",
		"attack"
	)
	# While exercising the owner, the peer's untouched session reaches real expiry.
	var deadline := int(peer.npc_interaction.expires_at_us)
	if not _check(
		"idle_conversation_expires_on_server_clock",
		await _wait_until(
			func(): return peer.server_time_us >= deadline and peer.npc_interaction.is_empty(), 65.0
		)
	):
		return false
	return true


func _conversation_lifecycle(
	actor: GameConnection, peer: GameConnection, actor_id: String, peer_id: String
) -> bool:
	if not await _open(actor, "open_before_leave"):
		return false
	actor.leave_world()
	if not _check(
		"leave_clears_dialogue_and_presence",
		await _wait_until(
			func():
				return (
					actor.state == "lobby"
					and actor.npc_interaction.is_empty()
					and _player(peer, actor_id).is_empty()
				),
			5.0
		)
	):
		return false
	await _raw_rejection(
		actor,
		"interact_npc",
		[NPC_ID, peer.world_info.npc_catalog_hash],
		[&"String", &"String"],
		"inactive_character_cannot_talk",
		"selected character"
	)
	actor.enter_selected()
	if not _check(
		"reentry_does_not_replay_conversation",
		await _wait_until(
			func():
				return (
					actor.state == "connected"
					and not _player(peer, actor_id).is_empty()
					and actor.npc_interaction.is_empty()
				),
			20.0
		)
	):
		return false
	return await _conversation_disconnect(actor, peer, actor_id, peer_id)


func _conversation_disconnect(
	actor: GameConnection, peer: GameConnection, actor_id: String, peer_id: String
) -> bool:
	if not await _open(actor, "open_before_disconnect"):
		return false
	actor.disconnect_game()
	if not _check(
		"disconnect_removes_presence",
		await _wait_until(func(): return _player(peer, actor_id).is_empty())
	):
		return false
	if not await _reconnect_idle(actor, peer, actor_id):
		return false
	_check(
		"reconnect_has_no_old_session",
		actor.npc_interaction.is_empty() and _raw_rows(actor).is_empty()
	)
	peer.disconnect_game()
	return _check(
		"peer_disconnect_removes_presence",
		await _wait_until(func(): return _player(actor, peer_id).is_empty())
	)
