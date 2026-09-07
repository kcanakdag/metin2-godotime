extends "res://tests/account_smoke.gd"
## Two authenticated clients exercise private target locking against the dual-dog fixture.


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	if not await _create_rosters(actor, observer):
		_finish()
		return
	var actor_id := str(actor.characters[0].character_id)
	var observer_id := str(observer.characters[0].character_id)
	if not await _enter_fixture(actor, observer, actor_id, observer_id):
		_finish()
		return
	var near_id := 1
	var far_id := 2
	var far := _monster_by_id(observer, far_id)
	await _raw_success(
		actor,
		"select_combat_target",
		[far_id, int(far.life_sequence)],
		[&"U32", &"U32"],
		"far_target_selected"
	)
	_check(
		"owner_target_projection_exact",
		await _wait_until(
			func(): return _target_is(actor, actor_id, far_id, int(far.life_sequence))
		)
	)
	_check("other_account_cannot_subscribe_target", _private_target(observer))
	await _raw_success(
		actor,
		"select_combat_target",
		[far_id, int(far.life_sequence)],
		[&"U32", &"U32"],
		"same_target_reselection_succeeds"
	)
	actor.clear_combat_target()
	_check(
		"clear_is_immediate",
		await _wait_until(func(): return actor.selected_combat_target().is_empty())
	)
	var near := _monster_by_id(observer, near_id)
	await _raw_rejection(
		actor,
		"select_combat_target",
		[near_id, int(near.life_sequence)],
		[&"U32", &"U32"],
		"clear_does_not_reset_change_deadline",
		"Wait one second"
	)
	await create_timer(1.05).timeout
	await _raw_rejection(
		actor,
		"select_combat_target",
		[999_999, 0],
		[&"U32", &"U32"],
		"unknown_target_rejected",
		"does not exist"
	)
	await _raw_success(
		actor,
		"select_combat_target",
		[far_id, int(far.life_sequence)],
		[&"U32", &"U32"],
		"invalid_target_does_not_consume_deadline"
	)
	await _raw_rejection(
		actor,
		"select_combat_target",
		[far_id, int(far.life_sequence) + 1],
		[&"U32", &"U32"],
		"stale_target_life_rejected",
		"no longer active"
	)
	if not _check("nearer_candidate_reached", await _approach(actor, observer, actor_id, near_id)):
		_finish()
		return
	near = _monster_by_id(observer, near_id)
	far = _monster_by_id(observer, far_id)
	var actor_position := _position(_player(observer, actor_id))
	_check(
		"selected_target_is_farther_than_candidate",
		(
			actor_position.distance_to(_position(far)) > 2.7
			and actor_position.distance_to(_position(near)) < 2.7
		)
	)
	var near_health := int(near.health)
	var far_health := int(far.health)
	actor.perform_attack()
	await create_timer(0.7).timeout
	_check(
		"out_of_range_lock_never_falls_back",
		(
			int(_monster_by_id(observer, near_id).health) == near_health
			and int(_monster_by_id(observer, far_id).health) == far_health
		)
	)
	actor.clear_combat_target()
	await create_timer(1.05).timeout
	near = _monster_by_id(observer, near_id)
	near_health = int(near.health)
	actor.perform_attack()
	_check(
		"fallback_hit_applies_once",
		await _wait_until(
			func(): return int(_monster_by_id(observer, near_id).health) == near_health - 25, 2.0
		)
	)
	var fallback_life := int(_monster_by_id(observer, near_id).life_sequence)
	_check(
		"fallback_hit_publishes_target",
		await _wait_until(_target_is.bind(actor, actor_id, near_id, fallback_life))
	)
	_check("fallback_projection_remains_private", _private_target(observer))
	actor.clear_combat_target()
	await create_timer(1.05).timeout
	near_health = int(_monster_by_id(observer, near_id).health)
	actor.perform_attack()
	actor.clear_combat_target()
	_check(
		"clear_during_swing_preserves_damage_without_fallback_projection",
		await _wait_until(
			func():
				return (
					int(_monster_by_id(observer, near_id).health) == near_health - 25
					and actor.selected_combat_target().is_empty()
				),
			2.0
		)
	)
	await create_timer(1.05).timeout
	near_health = int(_monster_by_id(observer, near_id).health)
	far_health = int(_monster_by_id(observer, far_id).health)
	actor.perform_attack()
	await _raw_success(
		actor,
		"select_combat_target",
		[far_id, int(_monster_by_id(observer, far_id).life_sequence)],
		[&"U32", &"U32"],
		"selection_during_swing_accepted"
	)
	_check(
		"selection_during_swing_does_not_redirect_pending_hit",
		await _wait_until(
			func():
				return (
					int(_monster_by_id(observer, near_id).health) == near_health - 25
					and int(_monster_by_id(observer, far_id).health) == far_health
					and int(actor.selected_combat_target().get("target_id", 0)) == far_id
				),
			2.0
		)
	)
	var reconnect_elapsed := await _reconnect_inside_deadline(actor, observer, actor_id, far_id)
	if reconnect_elapsed < 0:
		_finish()
		return
	await _raw_rejection(
		actor,
		"select_combat_target",
		[near_id, int(_monster_by_id(observer, near_id).life_sequence)],
		[&"U32", &"U32"],
		"reconnect_does_not_bypass_target_deadline",
		"Wait one second"
	)
	if reconnect_elapsed < 1050:
		await create_timer(float(1050 - reconnect_elapsed) / 1000.0).timeout
	if not await _kill_selected_target(actor, observer, actor_id, near_id):
		_finish()
		return
	var defeated_life := int(_monster_by_id(observer, near_id).life_sequence)
	_check("target_death_clears_projection", actor.selected_combat_target().is_empty())
	_check(
		"new_target_life_does_not_reuse_selection",
		await _wait_until(
			func():
				return (
					int(_monster_by_id(observer, near_id).life_sequence) > defeated_life
					and actor.selected_combat_target().is_empty()
				),
			16.0
		)
	)
	if not await _prove_owner_death_cleanup(actor, observer, actor_id, observer_id, near_id):
		_finish()
		return
	_tokens.clear()
	_finish()


func _enter_fixture(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	actor.select_character(actor_id)
	observer.select_character(observer_id)
	if not _check(
		"target_characters_selected",
		await _wait_until(_both_selected.bind(actor, observer, actor_id, observer_id))
	):
		return false
	actor.enter_selected()
	observer.enter_selected()
	if not _check(
		"target_clients_enter",
		await _wait_until(
			func(): return actor.state == "connected" and observer.state == "connected"
		)
	):
		return false
	if not _check(
		"reviewed_dual_dog_fixture", await _wait_until(func(): return _valid_dual_fixture(observer))
	):
		return false
	observer.move_to(-20.0, -20.0)
	if not _check(
		"observer_parked_outside_fixture_ai",
		await _wait_until(
			func():
				return (
					_position(_player(actor, observer_id)).distance_to(Vector2(-20.0, -20.0)) < 0.2
				),
			12.0
		)
	):
		return false
	return await _restore_fixture_lives(actor, observer, actor_id)


func _both_selected(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	return actor.local_identity == actor_id and observer.local_identity == observer_id


func _reconnect_inside_deadline(
	actor: GameConnection, observer: GameConnection, actor_id: String, far_id: int
) -> int:
	var deadline_started := Time.get_ticks_msec()
	if not await _raw_success(
		actor,
		"select_combat_target",
		[far_id, int(_monster_by_id(observer, far_id).life_sequence)],
		[&"U32", &"U32"],
		"same_target_renews_reconnect_deadline"
	):
		return -1
	actor.disconnect_game()
	_check(
		"disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty())
	)
	actor.connect_account(_server, _database, str(_tokens[0]), "target-smoke-reconnect")
	if not _check(
		"target_reconnect_returns_lobby", await _wait_until(func(): return actor.state == "lobby")
	):
		return -1
	_check("reconnect_clears_private_target", actor.selected_combat_target().is_empty())
	actor.enter_selected()
	if not _check(
		"target_reconnect_reenters",
		await _wait_until(
			func(): return actor.state == "connected" and not _player(observer, actor_id).is_empty()
		)
	):
		return -1
	_check("reentry_does_not_restore_target", actor.selected_combat_target().is_empty())
	var elapsed := Time.get_ticks_msec() - deadline_started
	if not _check("reconnect_completed_inside_target_deadline", elapsed < 850):
		return -1
	return elapsed


func _valid_dual_fixture(client: GameConnection) -> bool:
	if client.monsters.size() != 2:
		return false
	var first := _monster_by_id(client, 1)
	var second := _monster_by_id(client, 2)
	return (
		int(client.world_info.get("protocol_version", 0)) == 7
		and str(client.world_info.get("content_hash", "")) == "training-v2-dual-wild-dog-v1"
		and int(first.get("definition_vnum", 0)) == 101
		and int(second.get("definition_vnum", 0)) == 101
		and int(first.get("level", 0)) == 1
		and int(second.get("level", 0)) == 1
		and str(first.get("name", "")) == "Wild Dog"
		and str(second.get("name", "")) == "Wild Dog"
	)


func _monster_by_id(client: GameConnection, id: int) -> Dictionary:
	for row: Dictionary in client.monsters:
		if int(row.get("id", 0)) == id:
			return row
	return {}


func _target_is(
	client: GameConnection, character_id: String, target_id: int, target_life_sequence: int
) -> bool:
	var row := client.selected_combat_target()
	return (
		row.size() == 4
		and str(row.get("character_id", "")) == character_id
		and int(row.get("target_id", 0)) == target_id
		and int(row.get("target_life_sequence", -1)) == target_life_sequence
	)


func _private_target(client: GameConnection) -> bool:
	return client._client.get_local_database().get_all_rows("combat_target_view").is_empty()


func _approach(
	actor: GameConnection, observer: GameConnection, actor_id: String, target_id: int
) -> bool:
	for _attempt in range(40):
		var dog := _monster_by_id(observer, target_id)
		var player_position := _position(_player(observer, actor_id))
		var dog_position := _position(dog)
		if player_position.distance_to(dog_position) < 2.2:
			actor.stop_moving()
			return true
		var offset := (player_position - dog_position).normalized() * 1.5
		var destination := dog_position + offset
		actor.move_to(destination.x, destination.y)
		await create_timer(0.2).timeout
	actor.stop_moving()
	return false


func _restore_fixture_lives(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	for target_id in [1, 2]:
		var target := _monster_by_id(observer, target_id)
		if int(target.get("health", 0)) == 100:
			continue
		var old_life := int(target.get("life_sequence", 0))
		if int(target.get("health", 0)) > 0:
			if not await _approach(actor, observer, actor_id, target_id):
				return _check("fixture_restore_approach_%d" % target_id, false)
			for attack in range(4):
				target = _monster_by_id(observer, target_id)
				if int(target.get("health", 0)) == 0:
					break
				var health_before := int(target.health)
				actor.perform_attack()
				if not _check(
					"fixture_restore_hit_%d_%d" % [target_id, attack],
					await _wait_until(
						func():
							return int(_monster_by_id(observer, target_id).health) < health_before,
						2.0
					)
				):
					return false
				await create_timer(0.9).timeout
		if not _check(
			"fixture_restore_respawn_%d" % target_id,
			await _wait_until(
				func():
					var current := _monster_by_id(observer, target_id)
					return int(current.health) == 100 and int(current.life_sequence) > old_life,
				16.0
			)
		):
			return false
	actor.move_to(-4.0, 3.0)
	return _check(
		"fixture_restore_actor_start",
		await _wait_until(
			func():
				return _position(_player(observer, actor_id)).distance_to(Vector2(-4.0, 3.0)) < 0.2,
			12.0
		)
	)


func _kill_selected_target(
	actor: GameConnection, observer: GameConnection, actor_id: String, target_id: int
) -> bool:
	if not await _approach(actor, observer, actor_id, target_id):
		return _check("target_death_approach", false)
	var sword: Dictionary = _owned_sword(actor, actor_id)
	if sword.is_empty():
		return _check("target_death_sword_available", false)
	actor.equip_item(int(sword.id))
	if not _check(
		"target_death_sword_equipped",
		await _wait_until(func(): return bool(_owned_sword(actor, actor_id).get("equipped", false)))
	):
		return false
	var target := _monster_by_id(observer, target_id)
	await _raw_success(
		actor,
		"select_combat_target",
		[target_id, int(target.life_sequence)],
		[&"U32", &"U32"],
		"target_for_death_selected"
	)
	for attack in range(4):
		target = _monster_by_id(observer, target_id)
		if int(target.health) == 0:
			break
		var before := int(target.health)
		actor.perform_attack()
		if not _check(
			"target_death_hit_%d" % attack,
			await _wait_until(
				func(): return int(_monster_by_id(observer, target_id).health) < before, 2.0
			)
		):
			return false
		await create_timer(0.9).timeout
	return _check("selected_target_defeated", int(_monster_by_id(observer, target_id).health) == 0)


func _prove_owner_death_cleanup(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	observer_id: String,
	target_id: int
) -> bool:
	_check(
		"observer_remains_parked_for_owner_death",
		_position(_player(actor, observer_id)).distance_to(Vector2(-20.0, -20.0)) < 0.5
	)
	if not await _approach(actor, observer, actor_id, target_id):
		return _check("owner_death_approach", false)
	var target := _monster_by_id(observer, target_id)
	await _raw_success(
		actor,
		"select_combat_target",
		[target_id, int(target.life_sequence)],
		[&"U32", &"U32"],
		"owner_death_target_selected"
	)
	if not _check(
		"owner_death_occurs",
		await _wait_until(func(): return int(_player(observer, actor_id).health) == 0, 65.0)
	):
		return false
	return _check(
		"owner_death_clears_projection",
		await _wait_until(func(): return actor.selected_combat_target().is_empty())
	)


func _raw_success(
	client: GameConnection, reducer: String, args: Array, types: Array, label: String
) -> bool:
	var observed := {"done": false, "accepted": false}
	var call := client._client.call_reducer(reducer, args, types)
	if call.error != OK:
		return _check(label, false)
	call.response.connect(
		func(response: ReducerResultMessage):
			observed.done = true
			observed.accepted = response.reducer_result.value == ReducerOutcomeEnum.Options.ok
	)
	return _check(label, await _wait_until(func(): return observed.done) and observed.accepted)


func _finish() -> void:
	var snapshots: Array = []
	for client: GameConnection in _clients:
		var snapshot := {
			"state": client.state,
			"identity": client.local_identity,
			"players": client.players,
			"monsters": client.monsters,
			"target": client.selected_combat_target(),
		}
		snapshots.append(snapshot)
	print("TARGET_FINAL_STATE ", JSON.stringify(snapshots))
	super._finish()
