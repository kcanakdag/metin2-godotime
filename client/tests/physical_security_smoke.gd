extends "res://tests/physical_recovery_smoke.gd"
## Hostile ordinary clients; every accepted mutation still uses the production reducers.


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_physical_world(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _move_far_from_dog(actor, observer, actor_id)
	if ready:
		ready = await _prove_two_way_movement(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _inventory_attacks(actor, observer, actor_id)
	if ready:
		ready = await _receive_ordinary_damage(actor, observer, actor_id, 300)
	if ready:
		ready = await _consumption_replay(actor, observer, actor_id)
	if ready:
		ready = await _pickup_race(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _audit_privacy(actor) and await _audit_privacy(observer)
	if ready:
		observer.disconnect_game()
		ready = _check(
			"security_observer_disconnect_removes_presence",
			await _wait_until(func(): return _player(actor, observer_id).is_empty())
		)
	if not ready:
		_check("security_scenario_completed", false)
	_tokens.clear()
	_finish()


func _inventory_attacks(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	var items := actor.inventory.duplicate(true)
	var ids: Array = []
	for item: Dictionary in items + observer.inventory:
		if not _check(
			"unique_server_item_%d" % int(item.id), int(item.id) > 0 and not int(item.id) in ids
		):
			return false
		ids.append(int(item.id))
	var potion := _potion(actor, 27001)
	var id := int(potion.id)
	var revision := int(potion.revision)
	for attacker: GameConnection in [actor, observer]:
		await _raw_rejection(
			attacker,
			"move_item",
			[id, 255, revision],
			[&"U64", &"U8", &"U32"],
			"invalid_cell_or_foreign_owner",
			"page" if attacker == actor else "another"
		)
	for forged in [0, revision + 100, 4294967295]:
		await _raw_rejection(
			actor,
			"use_item",
			[id, forged],
			[&"U64", &"U32"],
			"forged_revision_%d_rejected" % forged,
			"changed"
		)
	var inactive := items.filter(func(row: Dictionary): return str(row.owner) != actor_id)
	if not _check("inactive_character_items_available", not inactive.is_empty()):
		return false
	await _raw_rejection(
		actor,
		"equip_item",
		[int(inactive[0].id), int(inactive[0].revision)],
		[&"U64", &"U32"],
		"same_account_inactive_character_rejected",
		"another"
	)
	await _raw_rejection(
		actor,
		"use_item",
		[9223372036854775807, 1],
		[&"U64", &"U32"],
		"invented_id_rejected",
		"exist"
	)
	if not _check("all_rejections_preserve_inventory", actor.inventory == items):
		return false
	if not await _raw_success(
		actor, "move_item", [id, 44, revision], [&"U64", &"U8", &"U32"], "versioned_move_accepted"
	):
		return false
	await _raw_rejection(
		actor,
		"move_item",
		[id, 43, revision],
		[&"U64", &"U8", &"U32"],
		"stale_move_rejected",
		"changed"
	)
	var moved := await _wait_until(
		func():
			return (
				int(_potion(actor, 27001).cell) == 44
				and int(_potion(actor, 27001).revision) == revision + 1
				and int(_potion(actor, 27001).count) == int(potion.count)
			)
	)
	return _check(
		"move_preserves_identity_and_quantity_advances_revision",
		moved and _private_inventory(actor) and _private_inventory(observer)
	)


func _consumption_replay(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	var potion := _potion(actor, 27001).duplicate(true)
	var before := _health(observer, actor_id)
	var args := [int(potion.id), int(potion.revision)]
	var types := [&"U64", &"U32"]
	if not await _raw_success(actor, "use_item", args, types, "first_consume_accepted"):
		return false
	# The remaining health deficit could accept another small potion. Only the stale
	# revision prevents this replay; the recovery-cap check cannot make this test pass.
	await _raw_rejection(
		actor, "use_item", args, types, "identical_consume_replay_rejected", "changed"
	)
	if not _check(
		"replayed_consume_grants_only_one_effect",
		await _wait_until(func(): return _health(observer, actor_id) == before + 300, 12.0)
	):
		return false
	await create_timer(1.3).timeout
	var saved := actor.inventory.duplicate(true)
	actor.disconnect_game()
	if not _check(
		"security_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty())
	):
		return false
	actor.connect_account(_server, _database, str(_tokens[0]), "security-reconnect")
	if not _check(
		"security_reconnect_lobby", await _wait_until(func(): return actor.state == "lobby", 20.0)
	):
		return false
	actor.enter_selected()
	if not _check(
		"security_reconnect_inventory_persists",
		await _wait_until(
			func():
				return (
					actor.state == "connected"
					and not _player(observer, actor_id).is_empty()
					and _same_inventory(actor.inventory, saved)
				),
			20.0
		)
	):
		return false
	await _raw_rejection(
		actor, "use_item", args, types, "reconnect_cannot_replay_consume", "changed"
	)
	return _check(
		"reconnect_has_no_duplicate_starters_or_effects",
		(
			int(_potion(actor, 27001).count) == int(potion.count) - 1
			and int(_potion(actor, 27001).revision) == int(potion.revision) + 1
			and _health(observer, actor_id) == before + 300
		)
	)


func _pickup_race(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	if not await _create_security_drop(actor, observer, actor_id):
		return false
	var drop: Dictionary = actor.item_drops[0].duplicate(true)
	await _raw_rejection(
		observer,
		"pickup_item_drop",
		[int(drop.id)],
		[&"U64"],
		"reserved_drop_theft_rejected",
		"reserved"
	)
	var origin := Vector2(float(drop.x), float(drop.z))
	actor.move_to(origin.x, origin.y)
	observer.move_to(origin.x, origin.y)
	if not _check(
		"both_racers_within_pickup_range",
		await _wait_until(
			func():
				return (
					_position(_player(actor, actor_id)).distance_to(origin) < 1.0
					and _position(_player(observer, observer_id)).distance_to(origin) < 1.0
				),
			12.0
		)
	):
		return false
	actor.stop_moving()
	observer.stop_moving()
	if not _check(
		"drop_reservation_expires_normally",
		await _wait_until(
			func(): return observer.server_time_us >= int(drop.reserved_until_us), 12.0
		)
	):
		return false
	var before := _total_potions(actor, observer)
	var results := {"done": 0, "accepted": 0, "timestamps": [0, 0]}
	_track_raw_call(actor, "pickup_item_drop", [int(drop.id)], [&"U64"], results, 0)
	_track_raw_call(observer, "pickup_item_drop", [int(drop.id)], [&"U64"], results, 1)
	if not _check(
		"concurrent_pickup_has_exactly_one_winner",
		await _wait_until(func(): return int(results.done) == 2) and int(results.accepted) == 1
	):
		return false
	_timing_evidence.append(
		{"phase": "pickup_race", "drop_id": drop.id, "results": results.duplicate(true)}
	)
	await _raw_rejection(
		actor,
		"pickup_item_drop",
		[int(drop.id)],
		[&"U64"],
		"collected_drop_replay_rejected",
		"collected"
	)
	var collected := await _wait_until(
		func():
			return (
				actor.item_drops.is_empty()
				and observer.item_drops.is_empty()
				and _total_potions(actor, observer) == before + int(drop.count)
			),
		5.0
	)
	return _check("pickup_quantity_conserved_and_drop_removed_on_both_clients", collected)


func _audit_privacy(client: GameConnection) -> bool:
	var result := {"done": false, "rejected": false}
	var error := client._client.one_off_query(
		"SELECT * FROM item_audit",
		func(response: OneOffQueryResponseMessage):
			result.done = true
			result.rejected = not response.result_err.is_empty() and response.result_ok.is_empty()
	)
	return _check(
		"private_item_audit_is_unreadable_" + client.local_identity,
		error == OK and await _wait_until(func(): return result.done) and bool(result.rejected)
	)


func _total_potions(actor: GameConnection, observer: GameConnection) -> int:
	return int(_potion(actor, 27001).count) + int(_potion(observer, 27001).count)


func _create_security_drop(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _equip_combo_sword(actor, observer, actor_id):
		return false
	for index in range(8):
		if int(_monster(observer).health) == 0:
			break
		if not await _physical_hit(
			actor, observer, actor_id, false, "security_drop_kill_%d" % index
		):
			return false
	return _check(
		"ordinary_kill_produces_drop_on_both_clients",
		await _wait_until(
			func():
				return not actor.item_drops.is_empty() and actor.item_drops == observer.item_drops,
			5.0
		)
	)
