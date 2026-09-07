extends "res://tests/finisher_smoke.gd"
## The same two authenticated clients exercise terminal-event lifecycle cleanup.


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_finisher_fixture(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _park_finisher_actor(actor, observer, actor_id)
	if ready:
		ready = await _normalize_retained_finisher_fixture(actor, observer, actor_id)
	if ready:
		ready = await _wait_three_dogs_at_baseline(observer)
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = await _prove_terminal_area(actor, observer, actor_id)
	if ready:
		ready = await _prepare_next_finisher(actor, observer, actor_id)
	if ready:
		ready = await _prove_disconnect_before_area(actor, observer, actor_id)
	if ready:
		ready = await _prepare_next_finisher(actor, observer, actor_id)
	if ready:
		ready = await _prove_disconnect_after_force(actor, observer, actor_id)
	if ready:
		ready = await _prove_fresh_life_reuse(actor, observer, actor_id)
	if ready:
		_tokens.clear()
	_finish()


func _prepare_next_finisher(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _ensure_finisher_unarmed(actor, observer, actor_id):
		return false
	if not await _normalize_retained_finisher_fixture(actor, observer, actor_id):
		return false
	if not await _wait_three_dogs_at_baseline(observer):
		return false
	return await _equip_combo_sword(actor, observer, actor_id)


func _ensure_finisher_unarmed(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var sword := _owned_sword(actor, actor_id)
	if sword.is_empty():
		return _check("finisher_cleanup_sword_exists", false)
	if bool(sword.get("equipped", false)):
		actor.unequip_item(int(sword.id), _sword_bag_cell)
		if not _check(
			"finisher_cleanup_unequips_sword",
			await _wait_until(
				func():
					return (
						not bool(_owned_sword(actor, actor_id).get("equipped", true))
						and int(observer.appearance_for(actor_id).get("weapon_vnum", -1)) == 0
					),
				5.0
			)
		):
			return false
	return _check(
		"finisher_cleanup_is_unarmed", not bool(_owned_sword(actor, actor_id).get("equipped", true))
	)


func _start_lifecycle_fourth(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> Dictionary:
	if not await _stage_first_whiff(actor, observer, actor_id):
		return {}
	var first_half := await _start_finisher_chain(actor, observer, actor_id)
	if first_half.is_empty():
		return {}
	return await _finish_finisher_chain(actor, observer, actor_id, first_half.second)


func _prove_disconnect_before_area(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var fourth := await _start_lifecycle_fourth(actor, observer, actor_id)
	if fourth.is_empty():
		return false
	return await _disconnect_before_area_after_fourth(actor, observer, actor_id, fourth)


func _disconnect_before_area_after_fourth(
	actor: GameConnection, observer: GameConnection, actor_id: String, fourth: Dictionary
) -> bool:
	var start_us := int(fourth.action_started_at_us)
	if not _check(
		"finisher_prearea_disconnect_time_reached",
		await _wait_for_estimated_action_time(
			observer, start_us, 220_000, 290_000, 300_000, "finisher_prearea_disconnect"
		)
	):
		return false
	var before_position := _position(_player(observer, actor_id))
	var before_sequence := int(_player(observer, actor_id).attack_sequence)
	var disconnect_clock := observer.server_time_us
	actor.disconnect_game()
	var presence_removed := await _wait_until(
		func(): return _player(observer, actor_id).is_empty(), 5.0
	)
	var presence_removed_clock := observer.server_time_us
	if not _check("finisher_prearea_disconnect_removes_presence", presence_removed):
		return false
	if not _check(
		"finisher_prearea_disconnect_precedes_activation",
		disconnect_clock < start_us + 666_667 and presence_removed_clock < start_us + 666_667
	):
		return false
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_prearea_presence_removed",
				"action_started_at_us": start_us,
				"disconnect_sample_clock_us": disconnect_clock,
				"presence_removed_clock_us": presence_removed_clock,
				"activation_at_us": start_us + 666_667,
			}
		)
	)
	if not await _wait_server_time(observer, start_us + 1_466_667):
		return _check("finisher_prearea_observer_reaches_expired_event_time", false)
	var no_area := (
		int(_monster_by_id(observer, 1).health) == 30
		and int(_monster_by_id(observer, 2).health) == 100
		and int(_monster_by_id(observer, 3).health) == 100
		and not _is_great_reaction(_monster_by_id(observer, 1))
		and not _is_great_reaction(_monster_by_id(observer, 2))
	)
	if not _check("finisher_disconnect_before_activation_clears_area", no_area):
		return false
	return await _reconnect_finisher_without_replay(
		actor,
		observer,
		actor_id,
		before_position,
		before_sequence,
		"finisher_prearea",
	)


func _reconnect_finisher_without_replay(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	before_position: Vector2,
	before_sequence: int,
	label: String
) -> bool:
	actor.connect_account(_server, _database, str(_tokens[0]), label + "-reconnect")
	if not _check(
		label + "_reconnect_returns_lobby",
		await _wait_until(func(): return actor.state == "lobby", 20.0)
	):
		return false
	actor.enter_selected()
	if not _check(
		label + "_reconnect_reenters",
		await _wait_until(
			func():
				return actor.state == "connected" and not _player(observer, actor_id).is_empty(),
			20.0
		)
	):
		return false
	var reentered := _position(_player(observer, actor_id))
	if not _check(
		label + "_reconnect_has_no_position_catchup",
		reentered.distance_to(before_position) <= ROOT_DISCONNECT_SAMPLE_TOLERANCE_M
	):
		return false
	if not await _park_finisher_actor(actor, observer, actor_id):
		return false
	var parked := _position(_player(observer, actor_id))
	await create_timer(1.3).timeout
	return _check(
		label + "_reconnect_has_no_action_replay",
		(
			int(_player(observer, actor_id).attack_sequence) == before_sequence
			and (
				_position(_player(observer, actor_id)).distance_to(parked)
				<= ROOT_POSITION_TOLERANCE_M
			)
		),
	)


func _is_great_reaction(dog: Dictionary) -> bool:
	return (
		str(dog.get("attack_action_id", ""))
		in [FINISHER_FRONT_KNOCKDOWN, FINISHER_FRONT_STANDUP, FINISHER_BACK_KNOCKDOWN]
	)


func _prove_disconnect_after_force(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _stage_first_whiff(actor, observer, actor_id):
		return false
	var first_half := await _start_finisher_chain(actor, observer, actor_id)
	if first_half.is_empty():
		return false
	var force_anchor := {"ready": false}
	var capture_force := func(rows: Array):
		if bool(force_anchor.ready):
			return
		for row: Dictionary in rows:
			if (
				int(row.get("id", 0)) == 2
				and int(row.get("health", -1)) == 65
				and str(row.get("attack_action_id", "")) == FINISHER_FRONT_KNOCKDOWN
			):
				force_anchor.ready = true
				force_anchor.position = _position(row)
				force_anchor.action_started_at_us = int(row.get("action_started_at_us", 0))
				force_anchor.action_ends_at_us = int(row.get("action_ends_at_us", 0))
				force_anchor.attack_sequence = int(row.get("attack_sequence", 0))
				force_anchor.life_sequence = int(row.get("life_sequence", 0))
				force_anchor.observer_server_time_us = observer.server_time_us
				return
	observer.monsters_changed.connect(capture_force)
	var fourth := await _finish_finisher_chain(actor, observer, actor_id, first_half.second)
	if fourth.is_empty():
		observer.monsters_changed.disconnect(capture_force)
		return false
	if not _check(
		"finisher_postforce_acceptance_observed",
		await _wait_until(func(): return bool(force_anchor.ready), 1.5)
	):
		observer.monsters_changed.disconnect(capture_force)
		return false
	observer.monsters_changed.disconnect(capture_force)
	return await _finish_disconnect_after_force(actor, observer, actor_id, force_anchor)


func _finish_disconnect_after_force(
	actor: GameConnection, observer: GameConnection, actor_id: String, force_anchor: Dictionary
) -> bool:
	var before_position := _position(_player(observer, actor_id))
	var before_sequence := int(_player(observer, actor_id).attack_sequence)
	actor.disconnect_game()
	var presence_removed := await _wait_until(
		func(): return _player(observer, actor_id).is_empty(), 5.0
	)
	var presence_removed_clock := observer.server_time_us
	if not _check(
		"finisher_postforce_disconnect_removes_presence",
		(
			presence_removed
			and presence_removed_clock < int(force_anchor.action_started_at_us) + 1_000_000
		)
	):
		return false
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_postforce_presence_removed",
				"force_started_at_us": int(force_anchor.action_started_at_us),
				"presence_removed_clock_us": presence_removed_clock,
				"force_ends_at_us": int(force_anchor.action_started_at_us) + 1_000_000,
			}
		)
	)
	if not await _wait_server_time(observer, int(force_anchor.action_started_at_us) + 1_050_000):
		return _check("finisher_postforce_observer_reaches_force_end", false)
	var b_at_force_end := _monster_by_id(observer, 2)
	var force_distance := _position(b_at_force_end).distance_to(force_anchor.position)
	if not _check(
		"finisher_accepted_force_finishes_after_owner_disconnect",
		(
			absf(force_distance - FINISHER_FORCE_DISTANCE_M) <= 0.003
			and int(b_at_force_end.life_sequence) == int(force_anchor.life_sequence)
			and int(b_at_force_end.attack_sequence) == int(force_anchor.attack_sequence)
			and str(b_at_force_end.attack_action_id) == FINISHER_FRONT_KNOCKDOWN
			and int(b_at_force_end.action_started_at_us) == int(force_anchor.action_started_at_us)
			and int(b_at_force_end.action_ends_at_us) == int(force_anchor.action_ends_at_us)
			and (
				int(b_at_force_end.action_ends_at_us) - int(b_at_force_end.action_started_at_us)
				== 1_166_667
			)
			and int(b_at_force_end.health) == 65
		),
	):
		return false
	var standup := await _wait_until(
		func():
			var b := _monster_by_id(observer, 2)
			return (
				str(b.get("attack_action_id", "")) == FINISHER_FRONT_STANDUP
				and int(b.get("attack_sequence", 0)) == int(force_anchor.attack_sequence) + 1
				and (
					int(b.get("action_ends_at_us", 0)) - int(b.get("action_started_at_us", 0))
					== 1_000_000
				)
			),
		2.0
	)
	if not _check("finisher_reaction_finishes_after_owner_disconnect", standup):
		return false
	if not _check(
		"finisher_postforce_disconnect_does_not_repeat_area",
		(
			int(_monster_by_id(observer, 2).health) == 65
			and int(_monster_by_id(observer, 3).health) == 100
		),
	):
		return false
	return await _reconnect_finisher_without_replay(
		actor,
		observer,
		actor_id,
		before_position,
		before_sequence,
		"finisher_postforce",
	)


func _prove_fresh_life_reuse(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var fresh_b := await _prepare_fresh_b_life(actor, observer, actor_id)
	if fresh_b.is_empty():
		return false
	return await _hit_and_restore_fresh_b(actor, observer, actor_id, fresh_b)


func _prepare_fresh_b_life(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> Dictionary:
	var old_b_life := int(_monster_by_id(observer, 2).life_sequence)
	if not await _ensure_finisher_unarmed(actor, observer, actor_id):
		return {}
	if not await _normalize_retained_finisher_fixture(actor, observer, actor_id):
		return {}
	if not await _wait_three_dogs_at_baseline(observer):
		return {}
	var fresh_b := _monster_by_id(observer, 2).duplicate(true)
	if not _check(
		"finisher_fresh_b_life_after_force",
		int(fresh_b.life_sequence) > old_b_life and int(fresh_b.health) == 100
	):
		return {}
	var stable_position := _position(fresh_b)
	var stable_sequence := int(fresh_b.attack_sequence)
	await create_timer(1.1).timeout
	var after_stable := _monster_by_id(observer, 2)
	if not _check(
		"finisher_fresh_life_has_no_old_area_force_or_reaction",
		(
			int(after_stable.life_sequence) == int(fresh_b.life_sequence)
			and int(after_stable.health) == 100
			and int(after_stable.activity) == 0
			and int(after_stable.attack_sequence) == stable_sequence
			and _position(after_stable).distance_to(stable_position) <= 0.001
		),
	):
		return {}
	return fresh_b


func _hit_and_restore_fresh_b(
	actor: GameConnection, observer: GameConnection, actor_id: String, fresh_b: Dictionary
) -> bool:
	if not await _equip_combo_sword(actor, observer, actor_id):
		return false
	if not await _approach_finisher_dog(actor, observer, actor_id, 2):
		return false
	if not await _raw_success(
		actor,
		"select_combat_target",
		[int(fresh_b.id), int(fresh_b.life_sequence)],
		[&"U32", &"U32"],
		"finisher_fresh_b_exact_life_selected"
	):
		return false
	if not await _raw_success(
		actor, "perform_attack", [], [], "finisher_fresh_b_first_hit_accepted"
	):
		return false
	if not _check(
		"finisher_fresh_b_does_not_inherit_old_hit_cooldown",
		await _wait_until(func(): return int(_monster_by_id(observer, 2).health) == 65, 2.0)
	):
		return false
	await create_timer(1.05).timeout
	return await _restore_after_fresh_b_hit(actor, observer, actor_id)


func _restore_after_fresh_b_hit(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _ensure_finisher_unarmed(actor, observer, actor_id):
		return false
	if not await _normalize_retained_finisher_fixture(actor, observer, actor_id):
		return false
	return await _wait_three_dogs_at_baseline(observer)
