extends "res://tests/combo_smoke.gd"
## Two authenticated clients exercise the four-step prefix and authoritative displacement.

const ROOT_COMBO_ONE := "actor.player.warrior-male.onehand.combo_1"
const ROOT_COMBO_TWO := "actor.player.warrior-male.onehand.combo_2"
const ROOT_COMBO_THREE := "actor.player.warrior-male.onehand.combo_3"
const ROOT_COMBO_FOUR := "actor.player.warrior-male.onehand.combo_4"
const ROOT_ENDPOINT_Z := {
	ROOT_COMBO_ONE: -1.317569580078125,
	ROOT_COMBO_TWO: -0.852515640258789,
	ROOT_COMBO_THREE: -1.4301394653320312,
	ROOT_COMBO_FOUR: -1.1964712524414062,
}
const ROOT_DURATION_US := {
	ROOT_COMBO_ONE: 1_000_000,
	ROOT_COMBO_TWO: 933_333,
	ROOT_COMBO_THREE: 1_066_667,
	ROOT_COMBO_FOUR: 1_266_667,
}
const ROOT_POSITION_TOLERANCE_M := 0.001
const ROOT_DISCONNECT_SAMPLE_TOLERANCE_M := 0.08
const ROOT_CROSSING_STAGE_DISTANCE_M := 0.12
const STONE_CLEAR_WAYPOINT := Vector2(-4.5, 0.0)
const STONE_APPROACH := Vector2(-4.5, -5.0)
const STONE_BLOCKED_TARGET := Vector2(-11.0, -5.0)


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
			"root_single_training_dog_subscribes",
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
		ready = await _prove_targetless_three(actor, observer, actor_id)
	if ready:
		ready = await _prove_training_stone_clip(actor, observer, actor_id)
	if ready:
		ready = await _prove_far_miss_three(actor, observer, actor_id)
	if ready:
		ready = await _prove_three_hits_and_death_root(actor, observer, actor_id)
	if ready:
		ready = await _wait_new_dog_life(actor, observer)
	if ready:
		ready = await _prove_equipment_cancel_root_continues(actor, observer, actor_id)
	if ready:
		ready = await _prove_disconnect_stops_root(actor, observer, actor_id)
	if ready:
		_tokens.clear()
	_finish()


func _prove_targetless_three(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	actor.clear_combat_target()
	if not _check(
		"root_targetless_selection_empty",
		await _wait_until(func(): return actor.selected_combat_target().is_empty())
	):
		return false
	if not await _move_far_from_dog(actor, observer, actor_id):
		return false
	var health_before := int(_monster(observer).health)
	var first_position := _position(_player(observer, actor_id))
	var first := await _start_action(
		actor, observer, actor_id, ROOT_COMBO_ONE, "root_targetless_one"
	)
	if first.is_empty():
		return false
	return await _finish_targetless_three(
		actor, observer, actor_id, health_before, first_position, first
	)


func _finish_targetless_three(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	first_position: Vector2,
	first: Dictionary
) -> bool:
	var second_result := await _send_direct_follow_up(
		actor, observer, int(first.action_started_at_us), false, "root_targetless_two"
	)
	if second_result.is_empty():
		return false
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), ROOT_COMBO_TWO
	)
	if second.is_empty():
		return _check("root_targetless_two_replicates", false)
	if not _check_root_segment(
		"root_targetless_one_endpoint",
		first_position,
		first,
		int(second.action_started_at_us),
		_position(second)
	):
		return false
	var second_position := _position(second)
	var third_result := await _send_direct_follow_up(
		actor, observer, int(second.action_started_at_us), true, "root_targetless_three"
	)
	if third_result.is_empty():
		return false
	var third := await _wait_action_after(
		observer, actor_id, int(second.attack_sequence), ROOT_COMBO_THREE
	)
	if third.is_empty():
		return _check("root_targetless_three_replicates", false)
	return await _finish_targetless_terminal(
		actor, observer, actor_id, health_before, second_position, second, third
	)


func _finish_targetless_terminal(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	second_position: Vector2,
	second: Dictionary,
	third: Dictionary
) -> bool:
	if not _check_root_segment(
		"root_targetless_two_endpoint",
		second_position,
		second,
		int(third.action_started_at_us),
		_position(third)
	):
		return false
	var third_position := _position(third)
	var fourth_result := await _send_terminal_follow_up(
		actor, observer, int(third.action_started_at_us), "root_targetless_four"
	)
	if fourth_result.is_empty():
		return false
	var fourth := await _wait_action_after(
		observer, actor_id, int(third.attack_sequence), ROOT_COMBO_FOUR
	)
	if fourth.is_empty():
		return _check("root_targetless_four_replicates", false)
	if not _check_root_segment(
		"root_targetless_three_endpoint",
		third_position,
		third,
		int(fourth.action_started_at_us),
		_position(fourth)
	):
		return false
	return await _finish_targetless_fourth(actor, observer, actor_id, health_before, fourth)


func _finish_targetless_fourth(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	fourth: Dictionary
) -> bool:
	await _raw_rejection(actor, "perform_attack", [], [], "root_bounded_fifth_rejected", "complete")
	var fourth_position := _position(fourth)
	if not await _wait_action_end(observer, actor_id, int(fourth.action_ends_at_us)):
		return _check("root_targetless_four_finishes", false)
	if not _check_root_segment(
		"root_targetless_four_endpoint",
		fourth_position,
		fourth,
		int(fourth.action_ends_at_us),
		_position(_player(observer, actor_id))
	):
		return false
	return _check(
		"root_targetless_four_deals_zero_damage",
		(
			int(_monster(observer).health) == health_before
			and actor.selected_combat_target().is_empty()
		)
	)


func _send_direct_follow_up(
	actor: GameConnection,
	observer: GameConnection,
	action_start_us: int,
	second_window: bool,
	label: String
) -> Dictionary:
	var timing_ready := (
		await _wait_step_two_direct_time(observer, action_start_us, label + "_send")
		if second_window
		else await _wait_direct_send_time(observer, action_start_us, label + "_send")
	)
	if not _check(label + "_send_time_reached", timing_ready):
		return {}
	var result := await _raw_result(actor, "perform_attack", [], [])
	_record_raw_result(label, "perform_attack", result)
	if not _check(label + "_accepted", bool(result.accepted)):
		return {}
	var direct_us := 543_248 if second_window else 533_333
	var limit_us := 636_581 if second_window else 602_564
	if not _check(
		label + "_inside_source_window",
		(
			int(result.timestamp) > action_start_us + direct_us
			and int(result.timestamp) <= action_start_us + limit_us
		)
	):
		return {}
	return result


func _send_terminal_follow_up(
	actor: GameConnection, observer: GameConnection, action_start_us: int, label: String
) -> Dictionary:
	var timing_ready := await _wait_for_estimated_action_time(
		observer, action_start_us, 380_000, 450_000, 475_000, label + "_send"
	)
	if not _check(label + "_send_time_reached", timing_ready):
		return {}
	var result := await _raw_result(actor, "perform_attack", [], [])
	_record_raw_result(label, "perform_attack", result)
	if not _check(label + "_accepted", bool(result.accepted)):
		return {}
	if not _check(
		label + "_inside_source_window",
		(
			int(result.timestamp) > action_start_us + 418_462
			and int(result.timestamp) <= action_start_us + 664_615
		)
	):
		return {}
	return result


func _wait_step_two_direct_time(
	observer: GameConnection, action_start_us: int, phase: String
) -> bool:
	return await _wait_for_estimated_action_time(
		observer, action_start_us, 490_000, 540_000, 565_000, phase
	)


func _prove_training_stone_clip(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _move_and_stop(actor, observer, actor_id, STONE_CLEAR_WAYPOINT, 12.0):
		return _check("root_stone_clear_waypoint_reached", false)
	if not await _move_and_stop(actor, observer, actor_id, STONE_APPROACH, 4.0):
		return _check("root_stone_east_staging_reached", false)
	actor.move_to(STONE_BLOCKED_TARGET.x, STONE_BLOCKED_TARGET.y)
	var reached_edge := await _wait_until(
		func():
			var position := _position(_player(observer, actor_id))
			return absf(position.x + 5.95) < 0.02 and absf(position.y + 5.0) < 0.05,
		3.0
	)
	actor.stop_moving()
	if not _check("root_stone_authoritative_edge_reached", reached_edge):
		return false
	if not _check(
		"root_stone_edge_is_stopped_before_attack",
		await _wait_until(
			func():
				var row := _player(observer, actor_id)
				var position := _position(row)
				return (
					int(row.get("activity", -1)) == 0
					and absf(position.x + 5.95) < 0.02
					and absf(position.y + 5.0) < 0.05
				),
			2.0
		)
	):
		return false
	return await _finish_training_stone_clip(actor, observer, actor_id)


func _finish_training_stone_clip(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var start_position := _position(_player(observer, actor_id))
	var action := await _start_action(actor, observer, actor_id, ROOT_COMBO_ONE, "root_stone_one")
	if action.is_empty():
		return false
	if not await _wait_action_end(observer, actor_id, int(action.action_ends_at_us)):
		return _check("root_stone_action_finishes", false)
	var clipped := _position(_player(observer, actor_id))
	if not _check(
		"root_stone_clips_authoritative_displacement",
		clipped.distance_to(start_position) <= ROOT_POSITION_TOLERANCE_M
	):
		return false
	await create_timer(0.2).timeout
	return _check(
		"root_stone_discards_blocked_remainder",
		_position(_player(observer, actor_id)).distance_to(clipped) <= ROOT_POSITION_TOLERANCE_M
	)


func _move_and_stop(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	destination: Vector2,
	timeout: float
) -> bool:
	actor.move_to(destination.x, destination.y)
	var arrived := await _wait_until(
		func(): return _position(_player(observer, actor_id)).distance_to(destination) < 0.05,
		timeout
	)
	actor.stop_moving()
	if not arrived:
		return false
	return await _wait_until(
		func():
			var row := _player(observer, actor_id)
			return (
				int(row.get("activity", -1)) == 0 and _position(row).distance_to(destination) < 0.06
			),
		2.0
	)


func _prove_far_miss_three(
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
		"root_far_target_selected"
	):
		return false
	if not _check(
		"root_far_target_out_of_reach",
		_position(_player(observer, actor_id)).distance_to(_position(dog)) > 8.0
	):
		return false
	var first := await _start_action(actor, observer, actor_id, ROOT_COMBO_ONE, "root_far_one")
	if first.is_empty():
		return false
	return await _finish_far_miss_three(actor, observer, actor_id, dog, first)


func _finish_far_miss_three(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	dog: Dictionary,
	first: Dictionary
) -> bool:
	var health_before := int(dog.health)
	var first_start := int(first.action_started_at_us)
	if not await _wait_server_time(observer, first_start + 250_000):
		return _check("root_far_two_queue_time", false)
	if not await _raw_success(actor, "perform_attack", [], [], "root_far_two_queued"):
		return false
	await _raw_rejection(
		actor, "perform_attack", [], [], "root_far_two_duplicate", "already queued"
	)
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), ROOT_COMBO_TWO
	)
	if second.is_empty():
		return _check("root_far_two_replicates", false)
	return await _finish_far_miss_terminal(actor, observer, actor_id, dog, health_before, second)


func _finish_far_miss_terminal(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	dog: Dictionary,
	health_before: int,
	second: Dictionary
) -> bool:
	var second_start := int(second.action_started_at_us)
	if not await _wait_server_time(observer, second_start + 250_000):
		return _check("root_far_three_queue_time", false)
	if not await _raw_success(actor, "perform_attack", [], [], "root_far_three_queued"):
		return false
	var third := await _wait_action_after(
		observer, actor_id, int(second.attack_sequence), ROOT_COMBO_THREE
	)
	if third.is_empty():
		return _check("root_far_three_replicates", false)
	if not _check(
		"root_far_three_stays_out_of_reach",
		_position(_player(observer, actor_id)).distance_to(_position(_monster(observer))) > 4.0
	):
		return false
	if not await _wait_action_end(observer, actor_id, int(third.action_ends_at_us)):
		return _check("root_far_three_finishes", false)
	return _check(
		"root_far_three_hits_independently_miss",
		(
			int(_monster(observer).health) == health_before
			and int(actor.selected_combat_target().get("target_id", 0)) == int(dog.id)
			and (
				int(actor.selected_combat_target().get("target_life_sequence", 0))
				== int(dog.life_sequence)
			)
		)
	)


func _prove_three_hits_and_death_root(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	if not await _stage_crossing_hit(actor, observer, actor_id):
		return false
	var dog := _monster(observer)
	var health_before := int(dog.health)
	var first := await _start_action(actor, observer, actor_id, ROOT_COMBO_ONE, "root_in_range_one")
	if first.is_empty():
		return false
	if not await _wait_server_time(observer, int(first.action_started_at_us) + 250_000):
		return _check("root_in_range_two_queue_time", false)
	if not await _raw_success(actor, "perform_attack", [], [], "root_in_range_two_queued"):
		return false
	return await _finish_three_hits(actor, observer, actor_id, health_before, first)


func _finish_three_hits(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	first: Dictionary
) -> bool:
	if not _check(
		"root_combo_one_exact_35",
		await _wait_until(func(): return int(_monster(observer).health) == health_before - 35)
	):
		return false
	_check_crossed_target_hit_heading(
		"root_combo_one_hit_preserves_crossing_heading", observer, actor_id, first
	)
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), ROOT_COMBO_TWO
	)
	if second.is_empty():
		return _check("root_in_range_two_replicates", false)
	if not _check(
		"root_combo_two_exact_35",
		await _wait_until(func(): return int(_monster(observer).health) == health_before - 70)
	):
		return false
	_check_action_heading_after_hit(
		"root_combo_two_hit_preserves_action_heading", observer, actor_id, second
	)
	var result := await _send_direct_follow_up(
		actor, observer, int(second.action_started_at_us), true, "root_in_range_three"
	)
	if result.is_empty():
		return false
	var third := await _wait_action_after(
		observer, actor_id, int(second.attack_sequence), ROOT_COMBO_THREE
	)
	if third.is_empty():
		return _check("root_in_range_three_replicates", false)
	return await _finish_death_root(actor, observer, actor_id, health_before, third)


func _finish_death_root(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	health_before: int,
	third: Dictionary
) -> bool:
	if not _check(
		"root_combo_three_defeats_after_65_30",
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) == 0
					and int(_monster(actor).health) == 0
					and actor.selected_combat_target().is_empty()
				),
			2.0
		)
	):
		return false
	var death_position := _position(_player(observer, actor_id))
	var third_position := _position(third)
	if not await _wait_action_end(observer, actor_id, int(third.action_ends_at_us)):
		return _check("root_terminal_action_finishes_after_target_death", false)
	var final_position := _position(_player(observer, actor_id))
	if not _check(
		"root_target_death_preserves_current_trajectory",
		final_position.distance_to(death_position) > 0.2
	):
		return false
	if not _check_root_segment(
		"root_terminal_full_endpoint",
		third_position,
		third,
		int(third.action_ends_at_us),
		final_position
	):
		return false
	return _check(
		"root_three_hits_are_exactly_once_for_both_clients",
		(
			health_before == 100
			and int(_player(actor, actor_id).attack_sequence) == int(third.attack_sequence)
		)
	)


func _stage_crossing_hit(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	var staged := false
	for _attempt in range(40):
		var actor_position := _position(_player(observer, actor_id))
		var dog_position := _position(_monster(observer))
		var away := actor_position - dog_position
		if away.is_zero_approx():
			away = Vector2.LEFT
		var destination := dog_position + away.normalized() * ROOT_CROSSING_STAGE_DISTANCE_M
		actor.move_to(destination.x, destination.y)
		await create_timer(0.05).timeout
		var distance := _position(_player(observer, actor_id)).distance_to(
			_position(_monster(observer))
		)
		if distance >= 0.06 and distance <= 0.18:
			actor.stop_moving()
			staged = await _wait_until(
				func():
					var row := _player(observer, actor_id)
					var current_distance := _position(row).distance_to(
						_position(_monster(observer))
					)
					return (
						int(row.get("activity", -1)) == 0
						and current_distance >= 0.05
						and current_distance <= 0.19
					),
				0.5
			)
			if staged:
				break
	actor.stop_moving()
	return _check("root_crossing_hit_staged_by_ordinary_movement", staged)


func _wait_new_dog_life(actor: GameConnection, observer: GameConnection) -> bool:
	var old_life := int(_monster(observer).life_sequence)
	return _check(
		"root_dog_natural_respawn_new_life",
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) == 100
					and int(_monster(observer).life_sequence) > old_life
					and actor.selected_combat_target().is_empty()
				),
			16.0
		)
	)


func _prove_equipment_cancel_root_continues(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _prove_equipment_cancel_preserves_hit(actor, observer, actor_id):
		return false
	var row := _player(observer, actor_id)
	var position_after_cancel := _position(row)
	var action_end := int(row.get("action_ends_at_us", 0))
	if not await _wait_action_end(observer, actor_id, action_end):
		return _check("root_equipment_cancel_action_finishes", false)
	return _check(
		"root_equipment_cancel_preserves_current_trajectory",
		_position(_player(observer, actor_id)).distance_to(position_after_cancel) > 0.1
	)


func _prove_disconnect_stops_root(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _move_far_from_dog(actor, observer, actor_id):
		return false
	var first := await _start_action(
		actor, observer, actor_id, ROOT_COMBO_ONE, "root_disconnect_one"
	)
	if first.is_empty():
		return false
	if not await _wait_server_time(observer, int(first.action_started_at_us) + 250_000):
		return _check("root_disconnect_queue_time", false)
	if not await _raw_success(actor, "perform_attack", [], [], "root_disconnect_two_queued"):
		return false
	var before_disconnect := _position(_player(observer, actor_id))
	actor.disconnect_game()
	if not _check(
		"root_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty())
	):
		return false
	await _wait_server_time(observer, int(first.action_ends_at_us) + 100_000)
	return await _reconnect_without_root_replay(actor, observer, actor_id, before_disconnect)


func _reconnect_without_root_replay(
	actor: GameConnection, observer: GameConnection, actor_id: String, before_disconnect: Vector2
) -> bool:
	actor.connect_account(_server, _database, str(_tokens[0]), "root-motion-smoke-reconnect")
	if not _check(
		"root_reconnect_returns_lobby",
		await _wait_until(func(): return actor.state == "lobby", 20.0)
	):
		return false
	actor.enter_selected()
	if not _check(
		"root_reconnect_reenters_idle",
		await _wait_until(
			func():
				return actor.state == "connected" and not _player(observer, actor_id).is_empty(),
			20.0
		)
	):
		return false
	var reentered := _position(_player(observer, actor_id))
	if not _check(
		"root_reconnect_has_no_catch_up",
		reentered.distance_to(before_disconnect) <= ROOT_DISCONNECT_SAMPLE_TOLERANCE_M
	):
		return false
	var sequence := int(_player(observer, actor_id).attack_sequence)
	await create_timer(0.9).timeout
	return _check(
		"root_reconnect_stays_idle_without_replay",
		(
			int(_player(observer, actor_id).attack_sequence) == sequence
			and (
				_position(_player(observer, actor_id)).distance_to(reentered)
				<= ROOT_POSITION_TOLERANCE_M
			)
		)
	)


func _check_root_segment(
	label: String,
	start_position: Vector2,
	action: Dictionary,
	through_us: int,
	actual_position: Vector2
) -> bool:
	var action_id := str(action.get("attack_action_id", ""))
	var duration_us := int(ROOT_DURATION_US.get(action_id, 0))
	var endpoint_z := float(ROOT_ENDPOINT_Z.get(action_id, 0.0))
	var elapsed_us: int = clampi(through_us - int(action.action_started_at_us), 0, duration_us)
	var fraction := float(elapsed_us) / float(duration_us) if duration_us > 0 else 0.0
	var heading := float(action.heading)
	var expected_delta := Vector2(
		sin(heading) * endpoint_z * fraction, cos(heading) * endpoint_z * fraction
	)
	var expected := start_position + expected_delta
	var error_m := actual_position.distance_to(expected)
	(
		_timing_evidence
		. append(
			{
				"phase": label,
				"action_id": action_id,
				"action_started_at_us": int(action.action_started_at_us),
				"through_us": through_us,
				"elapsed_us": elapsed_us,
				"heading": heading,
				"start_position": [start_position.x, start_position.y],
				"expected_position": [expected.x, expected.y],
				"actual_position": [actual_position.x, actual_position.y],
				"error_m": error_m,
			}
		)
	)
	return _check(label + "_matches_linear_endpoint", error_m <= ROOT_POSITION_TOLERANCE_M)


func _check_action_heading_after_hit(
	label: String, observer: GameConnection, actor_id: String, action: Dictionary
) -> bool:
	var actual := float(_player(observer, actor_id).get("heading", 0.0))
	var captured := float(action.get("heading", 0.0))
	var difference := absf(wrapf(actual - captured, -PI, PI))
	(
		_timing_evidence
		. append(
			{
				"phase": label,
				"attack_sequence": int(action.get("attack_sequence", 0)),
				"captured_heading": captured,
				"post_hit_heading": actual,
				"heading_difference": difference,
			}
		)
	)
	return _check(label, difference <= 0.000_001)


func _check_crossed_target_hit_heading(
	label: String, observer: GameConnection, actor_id: String, action: Dictionary
) -> bool:
	var player_row := _player(observer, actor_id)
	var monster_row := _monster(observer)
	var actual := float(player_row.get("heading", 0.0))
	var captured := float(action.get("heading", 0.0))
	var legacy_target_heading: float = atan2(
		_position(player_row).x - _position(monster_row).x,
		_position(player_row).y - _position(monster_row).y
	)
	var preserved_difference := absf(wrapf(actual - captured, -PI, PI))
	var legacy_difference := absf(wrapf(legacy_target_heading - captured, -PI, PI))
	(
		_timing_evidence
		. append(
			{
				"phase": label,
				"attack_sequence": int(action.get("attack_sequence", 0)),
				"captured_heading": captured,
				"post_hit_heading": actual,
				"legacy_target_heading": legacy_target_heading,
				"preserved_heading_difference": preserved_difference,
				"legacy_heading_difference": legacy_difference,
				"post_hit_player_position": [_position(player_row).x, _position(player_row).y],
				"post_hit_monster_position": [_position(monster_row).x, _position(monster_row).y],
			}
		)
	)
	return _check(label, preserved_difference <= 0.000_001 and legacy_difference >= PI * 0.75)
