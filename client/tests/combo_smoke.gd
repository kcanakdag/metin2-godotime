extends "res://tests/account_smoke.gd"
## Two authenticated clients exercise the accepted combo-prefix behavior on protocol 9.

const COMBO_ONE := "actor.player.warrior-male.onehand.combo_1"
const COMBO_TWO := "actor.player.warrior-male.onehand.combo_2"
const TRAINING_DOG_HOME := Vector2(3.0, 3.0)
const TRAINING_ACTOR_SAFE := Vector2(-18.0, 3.0)
const TRAINING_OBSERVER_SAFE := Vector2(-18.0, 6.0)
var _sword_bag_cell := -1
var _timing_evidence: Array = []
var _raw_results: Array = []


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_combo_fixture(actor, observer, actor_id, observer_id)
	if ready:
		ready = _check(
			"combo_single_training_dog_subscribes",
			await _wait_until(
				func(): return observer.monsters_for_definition(101).size() == 1, 16.0
			)
		)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _prove_two_way_movement(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _restore_dog(actor, observer, actor_id)
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = await _prove_targetless_chain(actor, observer, actor_id)
	if ready:
		ready = await _prove_far_miss_chain(actor, observer, actor_id)
	if ready:
		ready = await _prove_two_hits(actor, observer, actor_id)
	if ready:
		ready = await _defeat_and_respawn_dog(actor, observer, actor_id)
	if ready:
		ready = await _prove_equipment_cancel_preserves_hit(actor, observer, actor_id)
	if ready:
		ready = await _prove_disconnect_clears_chain(actor, observer, actor_id)
	if ready:
		_tokens.clear()
	_finish()


func _enter_combo_fixture(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	actor.select_character(actor_id)
	observer.select_character(observer_id)
	if not _check(
		"combo_characters_selected",
		await _wait_until(
			func():
				return actor.local_identity == actor_id and observer.local_identity == observer_id,
			5.0
		)
	):
		return false
	actor.enter_selected()
	observer.enter_selected()
	if not _check(
		"combo_clients_enter",
		await _wait_until(
			func(): return actor.state == "connected" and observer.state == "connected"
		)
	):
		return false
	if not _check(
		"combo_uses_flat_training_fixture",
		(
			str(actor.world_info.get("map_id", "")) == "training"
			and str(actor.world_info.get("map_name", "")) == "Training Grounds"
			and float(actor.world_info.get("half_size", 0.0)) == 32.0
			and actor.world_info == observer.world_info
		)
	):
		return false
	return _check(
		"protocol_nine_definition",
		(
			int(actor.world_info.get("protocol_version", 0)) == 9
			and str(actor.world_info.get("definition_hash", "")) == _expected_definition_hash
			and actor.world_info == observer.world_info
		)
	)


func _equip_combo_sword(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	var sword := _owned_sword(actor, actor_id)
	if not _check("combo_sword_exists", not sword.is_empty()):
		return false
	_sword_bag_cell = int(sword.cell)
	actor.equip_item(int(sword.id))
	return _check(
		"combo_sword_equipped",
		await _wait_until(
			func():
				return (
					bool(_owned_sword(actor, actor_id).get("equipped", false))
					and int(observer.appearance_for(actor_id).get("weapon_vnum", 0)) == 10
				),
			5.0
		)
	)


func _prove_targetless_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	actor.clear_combat_target()
	if not _check(
		"targetless_selection_empty",
		await _wait_until(func(): return actor.selected_combat_target().is_empty())
	):
		return false
	if not await _move_far_from_dog(actor, observer, actor_id):
		return false
	var health_before := int(_monster(observer).health)
	var first := await _start_action(actor, observer, actor_id, COMBO_ONE, "targetless_combo_one")
	if first.is_empty():
		return false
	return await _finish_targetless_chain(actor, observer, actor_id, health_before, first)


func _finish_targetless_chain(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	first: Dictionary
) -> bool:
	var start := int(first.action_started_at_us)
	if not await _wait_direct_send_time(observer, start, "targetless_direct_send"):
		return _check("targetless_direct_input_time_reached", false)
	var follow_up := await _raw_result(actor, "perform_attack", [], [])
	_record_raw_result("targetless_direct_follow_up", "perform_attack", follow_up)
	if not _check("targetless_direct_follow_up", bool(follow_up.accepted)):
		return false
	_check(
		"targetless_direct_receipt_inside_source_window",
		int(follow_up.timestamp) > start + 533_333 and int(follow_up.timestamp) <= start + 602_564
	)
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), COMBO_TWO
	)
	if second.is_empty():
		return _check("targetless_combo_two_replicates", false)
	_record_action_pair("targetless_direct", first, second)
	_check(
		"targetless_direct_uses_server_receipt_time",
		(
			int(second.action_started_at_us) == int(follow_up.timestamp)
			and int(second.action_ends_at_us) - int(second.action_started_at_us) == 933_333
		)
	)
	await _wait_action_end(observer, actor_id, int(second.action_ends_at_us))
	return _check(
		"targetless_two_steps_deal_zero_damage",
		(
			int(_monster(observer).health) == health_before
			and actor.selected_combat_target().is_empty()
		)
	)


func _prove_far_miss_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	await create_timer(1.05).timeout
	if not await _move_far_from_dog(actor, observer, actor_id):
		return false
	var dog := _monster(observer)
	if not await _raw_success(
		actor,
		"select_combat_target",
		[int(dog.id), int(dog.life_sequence)],
		[&"U32", &"U32"],
		"far_target_selected"
	):
		return false
	if not _check(
		"far_target_out_of_reach",
		_position(_player(observer, actor_id)).distance_to(_position(dog)) > 4.0
	):
		return false
	var health_before := int(dog.health)
	var first := await _start_action(actor, observer, actor_id, COMBO_ONE, "far_combo_one")
	if first.is_empty():
		return false
	return await _finish_far_miss_chain(actor, observer, actor_id, dog, health_before, first)


func _finish_far_miss_chain(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	dog: Dictionary,
	health_before: int,
	first: Dictionary
) -> bool:
	var start := int(first.action_started_at_us)
	if not await _wait_server_time(observer, start + 250_000):
		return _check("far_queue_time_reached", false)
	if not await _raw_success(actor, "perform_attack", [], [], "far_follow_up_queued"):
		return false
	await _raw_rejection(
		actor, "perform_attack", [], [], "far_duplicate_rejected", "already queued"
	)
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), COMBO_TWO
	)
	if second.is_empty():
		return _check("far_queued_combo_two_replicates", false)
	_record_action_pair("far_queued", first, second)
	_check(
		"queued_transition_uses_first_tick_after_direct_boundary",
		(
			int(second.action_started_at_us) > start + 533_333
			and int(second.action_started_at_us) <= start + 650_000
		)
	)
	await _wait_action_end(observer, actor_id, int(second.action_ends_at_us))
	return _check(
		"far_selected_hits_independently_miss",
		(
			int(_monster(observer).health) == health_before
			and int(actor.selected_combat_target().get("target_id", 0)) == int(dog.id)
		)
	)


func _prove_two_hits(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	var dog := _monster(observer)
	var health_before := int(dog.health)
	var first := await _start_action(actor, observer, actor_id, COMBO_ONE, "in_range_combo_one")
	if first.is_empty():
		return false
	return await _finish_two_hits(actor, observer, actor_id, health_before, first)


func _finish_two_hits(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	first: Dictionary
) -> bool:
	var start := int(first.action_started_at_us)
	if not await _wait_server_time(observer, start + 250_000):
		return _check("in_range_queue_time_reached", false)
	if not await _raw_success(actor, "perform_attack", [], [], "in_range_follow_up_queued"):
		return false
	if not _check(
		"combo_one_exact_35_damage",
		await _wait_until(func(): return int(_monster(observer).health) == health_before - 35, 2.0)
	):
		return false
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), COMBO_TWO
	)
	if second.is_empty():
		return _check("in_range_combo_two_replicates", false)
	_record_action_pair("in_range_queued", first, second)
	if not _check(
		"combo_two_exact_second_35_damage",
		await _wait_until(func(): return int(_monster(observer).health) == health_before - 70, 2.0)
	):
		return false
	await create_timer(0.4).timeout
	return _check(
		"two_combo_hits_are_exactly_once_for_both_clients",
		(
			int(_monster(actor).health) == health_before - 70
			and int(_monster(observer).health) == health_before - 70
			and int(_player(actor, actor_id).attack_sequence) == int(second.attack_sequence)
		)
	)


func _defeat_and_respawn_dog(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var defeated_life := int(_monster(observer).life_sequence)
	await _wait_action_end(
		observer, actor_id, int(_player(observer, actor_id).get("action_ends_at_us", 0))
	)
	var first := await _start_action(actor, observer, actor_id, COMBO_ONE, "lethal_combo_one")
	if first.is_empty():
		return false
	if not _check(
		"target_death_clears_chain_before_follow_up",
		await _wait_until(func(): return int(_monster(observer).health) == 0, 2.0)
	):
		return false
	await _raw_rejection(
		actor, "perform_attack", [], [], "dead_target_chain_cannot_advance", "cooling down"
	)
	return _check(
		"ordinary_twelve_second_respawn_is_new_life",
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) == 100
					and int(_monster(observer).life_sequence) > defeated_life
					and actor.selected_combat_target().is_empty()
				),
			16.0
		)
	)


func _prove_equipment_cancel_preserves_hit(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	var dog := _monster(observer)
	await create_timer(1.05).timeout
	if not await _raw_success(
		actor,
		"select_combat_target",
		[int(dog.id), int(dog.life_sequence)],
		[&"U32", &"U32"],
		"cancel_target_selected"
	):
		return false
	var sword := _owned_sword(actor, actor_id)
	var health_before := int(dog.health)
	var first := await _start_action(actor, observer, actor_id, COMBO_ONE, "cancel_combo_one")
	if first.is_empty():
		return false
	return await _finish_equipment_cancel(actor, observer, actor_id, sword, health_before, first)


func _finish_equipment_cancel(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	sword: Dictionary,
	health_before: int,
	first: Dictionary
) -> bool:
	var start := int(first.action_started_at_us)
	if not await _wait_overlap_send_time(observer, start, "equipment_cancel_send"):
		return _check("cancel_overlap_time_reached", false)
	var calls := _send_follow_up_then_unequip(actor, int(sword.id), _sword_bag_cell)
	var unequipped_before_hit := await _wait_until(
		func():
			return (
				int(observer.appearance_for(actor_id).get("weapon_vnum", -1)) == 0
				and int(_monster(observer).health) == health_before
			),
		0.2
	)
	if not _check(
		"queue_then_equipment_change_are_both_accepted",
		await _wait_until(func(): return calls.done == 2) and calls.accepted == 2
	):
		return false
	(
		_timing_evidence
		. append(
			{
				"phase": "equipment_cancel",
				"combo_one_started_at_us": start,
				"follow_up_received_at_us": int(calls.timestamps[0]),
				"unequip_received_at_us": int(calls.timestamps[1]),
				"unequipped_while_health_unchanged_observed": unequipped_before_hit,
				"observation_server_time_us": observer.server_time_us,
			}
		)
	)
	_check(
		"queue_cancel_received_while_first_hit_pending",
		(
			int(calls.timestamps[0]) > start + 167_094
			and int(calls.timestamps[0]) <= start + 533_333
			and int(calls.timestamps[1]) >= int(calls.timestamps[0])
			and int(calls.timestamps[1]) < start + 192_308
		)
	)
	if not _check(
		"equipment_cancel_preserves_captured_first_hit",
		await _wait_until(func(): return int(_monster(observer).health) == health_before - 35, 2.0)
	):
		return false
	await _wait_server_time(observer, start + 700_000)
	_check(
		"equipment_cancel_prevents_combo_two",
		(
			int(_player(observer, actor_id).attack_sequence) == int(first.attack_sequence)
			and str(_player(observer, actor_id).attack_action_id) == COMBO_ONE
			and int(_monster(observer).health) == health_before - 35
		)
	)
	_check(
		"equipment_cancel_projects_final_unequipped_state",
		await _wait_until(
			func():
				return (
					not bool(_owned_sword(actor, actor_id).get("equipped", true))
					and int(observer.appearance_for(actor_id).get("weapon_vnum", -1)) == 0
				),
			5.0
		)
	)
	actor.equip_item(int(sword.id))
	return _check(
		"cancel_test_restores_equipped_sword",
		await _wait_until(func(): return bool(_owned_sword(actor, actor_id).get("equipped", false)))
	)


func _prove_disconnect_clears_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	await _wait_action_end(
		observer, actor_id, int(_player(observer, actor_id).get("action_ends_at_us", 0))
	)
	var health_before := int(_monster(observer).health)
	var first := await _start_action(actor, observer, actor_id, COMBO_ONE, "disconnect_combo_one")
	if first.is_empty():
		return false
	return await _finish_disconnect(actor, observer, actor_id, health_before, first)


func _finish_disconnect(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	first: Dictionary
) -> bool:
	var start := int(first.action_started_at_us)
	if not await _wait_server_time(observer, start + 250_000):
		return _check("disconnect_queue_time_reached", false)
	if not _check(
		"disconnect_first_hit_applies_before_leave",
		await _wait_until(func(): return int(_monster(observer).health) == health_before - 35)
	):
		return false
	var follow_up := await _raw_result(actor, "perform_attack", [], [])
	if not _check("disconnect_follow_up_queued", bool(follow_up.accepted)):
		return false
	(
		_timing_evidence
		. append(
			{
				"phase": "disconnect_queued",
				"combo_one_started_at_us": start,
				"follow_up_received_at_us": int(follow_up.timestamp),
			}
		)
	)
	_check(
		"disconnect_follows_accepted_queue_before_direct_boundary",
		int(follow_up.timestamp) > start + 167_094 and int(follow_up.timestamp) <= start + 533_333
	)
	actor.disconnect_game()
	if not _check(
		"combo_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty())
	):
		return false
	await _wait_server_time(observer, start + 750_000)
	_check(
		"disconnect_prevents_queued_second_hit",
		int(_monster(observer).health) == health_before - 35
	)
	return await _reconnect_idle(actor, observer, actor_id)


func _reconnect_idle(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	actor.connect_account(_server, _database, str(_tokens[0]), "combo-smoke-reconnect")
	if not _check(
		"combo_reconnect_returns_lobby",
		await _wait_until(func(): return actor.state == "lobby", 20.0)
	):
		return false
	actor.enter_selected()
	if not _check(
		"combo_reconnect_reenters_idle",
		await _wait_until(
			func():
				return actor.state == "connected" and not _player(observer, actor_id).is_empty(),
			20.0
		)
	):
		return false
	var sequence := int(_player(observer, actor_id).attack_sequence)
	await create_timer(0.9).timeout
	return _check(
		"reconnect_does_not_revive_combo_two",
		(
			int(_player(observer, actor_id).attack_sequence) == sequence
			and str(_player(observer, actor_id).get("attack_action_id", "")) != COMBO_TWO
		)
	)


func _start_action(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	action_id: String,
	label: String
) -> Dictionary:
	var sequence := int(_player(observer, actor_id).get("attack_sequence", 0))
	actor.perform_attack()
	var observed := await _wait_until(
		func():
			var row := _player(observer, actor_id)
			return (
				int(row.get("attack_sequence", 0)) > sequence
				and str(row.get("attack_action_id", "")) == action_id
			),
		2.0
	)
	_check(label + "_replicates", observed)
	if not observed:
		return {}
	var row := _player(observer, actor_id).duplicate(true)
	var speed := int(row.get("attack_speed_percent", 0))
	if not _check(label + "_captured_speed_valid", speed >= 100 and speed <= 170):
		return {}
	var source_duration := 1_000_000 if action_id == COMBO_ONE else 933_333
	_check(
		label + "_captured_speed_duration",
		(
			int(row.action_ends_at_us) - int(row.action_started_at_us)
			== ceili(float(source_duration) * 100.0 / speed)
		)
	)
	return row


func _wait_action_after(
	observer: GameConnection, actor_id: String, sequence: int, action_id: String
) -> Dictionary:
	var ready := await _wait_until(
		func():
			var row := _player(observer, actor_id)
			return (
				int(row.get("attack_sequence", 0)) > sequence
				and str(row.get("attack_action_id", "")) == action_id
			),
		2.0
	)
	return _player(observer, actor_id).duplicate(true) if ready else {}


func _wait_action_end(observer: GameConnection, actor_id: String, end_us: int) -> bool:
	if end_us <= 0:
		return true
	return await _wait_until(
		func():
			var row := _player(observer, actor_id)
			return (
				observer.server_time_us > end_us + 75_000
				and int(row.get("action_ends_at_us", 0)) == 0
			),
		3.0
	)


func _wait_server_time(client: GameConnection, target_us: int) -> bool:
	return await _wait_until(func(): return client.server_time_us >= target_us, 2.0)


func _wait_overlap_send_time(observer: GameConnection, action_start_us: int, phase: String) -> bool:
	return await _wait_for_estimated_action_time(
		observer, action_start_us, 110_000, 167_000, 175_000, phase
	)


func _wait_direct_send_time(observer: GameConnection, action_start_us: int, phase: String) -> bool:
	return await _wait_for_estimated_action_time(
		observer, action_start_us, 480_000, 533_000, 550_000, phase
	)


func _wait_for_estimated_action_time(
	observer: GameConnection,
	action_start_us: int,
	anchor_min_elapsed_us: int,
	anchor_max_elapsed_us: int,
	target_elapsed_us: int,
	phase: String
) -> bool:
	var captured := {"ready": false, "server_time_us": 0, "ticks_us": 0}
	var receive_clock := func(server_time_us: int):
		var elapsed := server_time_us - action_start_us
		if (
			not captured.ready
			and elapsed >= anchor_min_elapsed_us
			and elapsed <= anchor_max_elapsed_us
		):
			captured.ready = true
			captured.server_time_us = server_time_us
			captured.ticks_us = Time.get_ticks_usec()
	observer.server_clock_changed.connect(receive_clock)
	var capture_deadline_ticks := Time.get_ticks_usec() + 1_000_000
	while not captured.ready and Time.get_ticks_usec() < capture_deadline_ticks:
		await process_frame
	observer.server_clock_changed.disconnect(receive_clock)
	if not captured.ready:
		return false
	var estimated_server_time_us := int(captured.server_time_us)
	while estimated_server_time_us < action_start_us + target_elapsed_us:
		await process_frame
		estimated_server_time_us = (
			int(captured.server_time_us) + Time.get_ticks_usec() - int(captured.ticks_us)
		)
	(
		_timing_evidence
		. append(
			{
				"phase": phase,
				"action_start_us": action_start_us,
				"anchor_server_time_us": int(captured.server_time_us),
				"anchor_observed_at_ticks_us": int(captured.ticks_us),
				"target_elapsed_us": target_elapsed_us,
				"estimated_send_server_time_us": estimated_server_time_us,
				"send_observed_at_ticks_us": Time.get_ticks_usec(),
			}
		)
	)
	return true


func _raw_success(
	client: GameConnection, reducer: String, args: Array, types: Array, label: String
) -> bool:
	var observed := await _raw_result(client, reducer, args, types)
	_record_raw_result(label, reducer, observed)
	return _check(label, bool(observed.accepted))


func _raw_result(client: GameConnection, reducer: String, args: Array, types: Array) -> Dictionary:
	var observed := {"done": false, "accepted": false, "timestamp": 0, "error": ""}
	var intent := _versioned_item_intent(client, reducer, args, types)
	args = intent.args
	types = intent.types
	var call := client._client.call_reducer(reducer, args, types)
	if call.error != OK:
		return observed
	call.response.connect(
		func(response: ReducerResultMessage):
			observed.done = true
			observed.accepted = response.reducer_result.value == ReducerOutcomeEnum.Options.ok
			observed.timestamp = response.timestamp
			if response.reducer_result.value == ReducerOutcomeEnum.Options.err:
				observed.error = response.reducer_result.get_err()
	)
	await _wait_until(func(): return observed.done)
	return observed


func _record_raw_result(label: String, reducer: String, result: Dictionary) -> void:
	(
		_raw_results
		. append(
			{
				"label": label,
				"reducer": reducer,
				"accepted": bool(result.accepted),
				"timestamp": int(result.timestamp),
				"error": str(result.error),
			}
		)
	)


func _send_follow_up_then_unequip(
	client: GameConnection, item_id: int, bag_cell: int
) -> Dictionary:
	var observed := {"done": 0, "accepted": 0, "timestamps": [0, 0]}
	_track_raw_call(client, "perform_attack", [], [], observed, 0)
	_track_raw_call(client, "unequip_item", [item_id, bag_cell], [&"U64", &"U8"], observed, 1)
	return observed


func _track_raw_call(
	client: GameConnection,
	reducer: String,
	args: Array,
	types: Array,
	observed: Dictionary,
	index: int
) -> void:
	var intent := _versioned_item_intent(client, reducer, args, types)
	args = intent.args
	types = intent.types
	var call := client._client.call_reducer(reducer, args, types)
	if call.error != OK:
		observed.done += 1
		return
	call.response.connect(
		func(response: ReducerResultMessage):
			observed.done += 1
			observed.timestamps[index] = response.timestamp
			if response.reducer_result.value == ReducerOutcomeEnum.Options.ok:
				observed.accepted += 1
	)


func _record_action_pair(phase: String, first: Dictionary, second: Dictionary) -> void:
	(
		_timing_evidence
		. append(
			{
				"phase": phase,
				"combo_one_sequence": int(first.attack_sequence),
				"combo_one_started_at_us": int(first.action_started_at_us),
				"combo_one_ends_at_us": int(first.action_ends_at_us),
				"combo_two_sequence": int(second.attack_sequence),
				"combo_two_started_at_us": int(second.action_started_at_us),
				"combo_two_ends_at_us": int(second.action_ends_at_us),
			}
		)
	)


func _approach_dog(
	actor: GameConnection, observer: GameConnection, actor_id: String, attempts: int = 50
) -> bool:
	for _attempt in range(attempts):
		var actor_position := _position(_player(observer, actor_id))
		var dog_position := _position(_monster(observer))
		if actor_position.distance_to(dog_position) <= 2.5:
			actor.stop_moving()
			return _check("combo_actor_in_melee_reach", true)
		var away := actor_position - dog_position
		if away.is_zero_approx():
			away = Vector2.LEFT
		var destination := dog_position + away.normalized() * 2.0
		actor.move_to(destination.x, destination.y)
		await create_timer(0.2).timeout
	actor.stop_moving()
	return _check("combo_actor_in_melee_reach", false)


func _move_far_from_dog(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	actor.move_to(TRAINING_ACTOR_SAFE.x, TRAINING_ACTOR_SAFE.y)
	var arrived := await _wait_until(
		func():
			return _position(_player(observer, actor_id)).distance_to(TRAINING_ACTOR_SAFE) < 0.25,
		12.0
	)
	actor.stop_moving()
	if not _check("combo_actor_reaches_training_safe_waypoint", arrived):
		return false
	return _check(
		"combo_actor_stable_outside_home_chase",
		await _wait_training_safe_state(observer, actor_id),
	)


func _park_observer(observer: GameConnection, actor: GameConnection, observer_id: String) -> bool:
	observer.move_to(TRAINING_OBSERVER_SAFE.x, TRAINING_OBSERVER_SAFE.y)
	var parked := await _wait_until(
		func():
			return (
				_position(_player(actor, observer_id)).distance_to(TRAINING_OBSERVER_SAFE) < 0.25
				and _position(_player(actor, observer_id)).distance_to(TRAINING_DOG_HOME) > 16.0
			),
		12.0
	)
	observer.stop_moving()
	return _check("combo_observer_parked_outside_home_chase", parked)


func _wait_training_safe_state(observer: GameConnection, actor_id: String) -> bool:
	var stable_since_ticks := 0
	var deadline_ticks := Time.get_ticks_msec() + 12_000
	while Time.get_ticks_msec() < deadline_ticks:
		var actor_position := _position(_player(observer, actor_id))
		var dog := _monster(observer)
		var dog_position := _position(dog)
		var stable := (
			actor_position.distance_to(TRAINING_ACTOR_SAFE) < 0.35
			and actor_position.distance_to(TRAINING_DOG_HOME) > 16.0
			and actor_position.distance_to(dog_position) > 8.0
			and dog_position.distance_to(TRAINING_DOG_HOME) < 0.35
			and int(dog.get("activity", -1)) == 0
		)
		if stable:
			if stable_since_ticks == 0:
				stable_since_ticks = Time.get_ticks_msec()
			elif Time.get_ticks_msec() - stable_since_ticks >= 500:
				return true
		else:
			stable_since_ticks = 0
		await create_timer(0.025).timeout
	return false


func _prove_two_way_movement(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	var actor_start := _position(_player(observer, actor_id))
	actor.set_move_input(1.0, 0.0)
	await create_timer(0.3).timeout
	actor.stop_moving()
	var actor_seen := await _wait_until(
		func(): return _position(_player(observer, actor_id)).distance_to(actor_start) > 0.2
	)
	var observer_start := _position(_player(actor, observer_id))
	observer.set_move_input(-1.0, 0.0)
	await create_timer(0.3).timeout
	observer.stop_moving()
	var observer_seen := await _wait_until(
		func(): return _position(_player(actor, observer_id)).distance_to(observer_start) > 0.2
	)
	return _check(
		"combo_two_way_movement_replicates",
		(
			actor_seen
			and observer_seen
			and _position(_player(actor, observer_id)).distance_to(TRAINING_DOG_HOME) > 16.0
		),
	)


func _restore_dog(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	if not _check(
		"combo_dog_available",
		await _wait_until(func(): return not observer.monsters_for_definition(101).is_empty(), 16.0)
	):
		return false
	var dog := _monster(observer)
	if int(dog.health) == 100:
		return true
	var old_life := int(dog.life_sequence)
	if int(dog.health) > 0:
		if not await _approach_dog(actor, observer, actor_id):
			return false
		var sword := _owned_sword(actor, actor_id)
		if bool(sword.get("equipped", false)):
			actor.unequip_item(int(sword.id), 0)
			if not await _wait_until(
				func(): return not bool(_owned_sword(actor, actor_id).equipped)
			):
				return _check("restore_unequips_sword", false)
		while int(_monster(observer).health) > 0:
			var before := int(_monster(observer).health)
			actor.perform_attack()
			if not _check(
				"restore_ordinary_hit_%d" % before,
				await _wait_until(func(): return int(_monster(observer).health) < before, 2.0)
			):
				return false
			await create_timer(0.9).timeout
	return _check(
		"restore_natural_respawn",
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) == 100
					and int(_monster(observer).life_sequence) > old_life
				),
			16.0
		)
	)


func _monster(client: GameConnection) -> Dictionary:
	return (
		client.monsters_for_definition(101)[0]
		if not client.monsters_for_definition(101).is_empty()
		else {}
	)


func _finish() -> void:
	if _finished:
		return
	_finished = true
	var evidence: Array = []
	for client: GameConnection in _clients:
		(
			evidence
			. append(
				{
					"state": client.state,
					"identity": client.local_identity,
					"players": client.players,
					"monsters": client.monsters_for_definition(101),
					"target": client.selected_combat_target(),
					"server_time_us": client.server_time_us,
					"last_reducer_rtt_ms": client.last_reducer_rtt_ms,
				}
			)
		)
	print("COMBO_FINAL_STATE ", JSON.stringify(evidence))
	print("COMBO_TIMING_EVIDENCE ", JSON.stringify(_timing_evidence))
	var client_states: Array = []
	for client: GameConnection in _clients:
		client_states.append({"state": client.state, "message": client.state_message})
		client.disconnect_game()
	await create_timer(0.1).timeout
	var passed := _checks.all(func(check: Dictionary): return check["passed"])
	var report := {
		"passed": passed,
		"database": _database,
		"checks": _checks,
		"client_states": client_states,
		"reducer_errors_observed": _errors.size(),
		"timing_evidence": _timing_evidence,
		"raw_results": _raw_results,
		"final_snapshots": evidence,
	}
	var file := FileAccess.open(_report_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	else:
		printerr("Cannot write combo report: ", _report_path)
		passed = false
	print("MT2_MULTIPLAYER_SMOKE ", "PASS" if passed else "FAIL")
	quit(0 if passed else 1)
