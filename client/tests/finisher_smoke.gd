extends "res://tests/root_motion_smoke.gd"
## Two authenticated clients exercise combo4, fixed splash and GREAT knockback.

const FINISHER_COMBO_FOUR := "actor.player.warrior-male.onehand.combo_4"
const FINISHER_FRONT_KNOCKDOWN := "actor.mob.wild-dog-101.general.front_knockdown"
const FINISHER_FRONT_STANDUP := "actor.mob.wild-dog-101.general.front_standup"
const FINISHER_BACK_KNOCKDOWN := "actor.mob.wild-dog-101.general.back_knockdown"
const FINISHER_DOG_HOMES := {
	1: Vector2(3.0, 3.0),
	2: Vector2(3.25, 3.0),
	3: Vector2(11.5, 3.0),
}
const FINISHER_BAIT := Vector2(-4.5, 3.0)
const FINISHER_MISS_DISTANCE_M := 3.4
const FINISHER_FORCE_DISTANCE_M := 4.732


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
		_tokens.clear()
	_finish()


func _enter_finisher_fixture(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	actor.select_character(actor_id)
	observer.select_character(observer_id)
	if not _check(
		"finisher_characters_selected",
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
		"finisher_clients_enter",
		await _wait_until(
			func(): return actor.state == "connected" and observer.state == "connected", 20.0
		)
	):
		return false
	if not _check(
		"finisher_protocol_nine_definition",
		(
			int(actor.world_info.get("protocol_version", 0)) == 9
			and str(actor.world_info.get("map_id", "")) == "training"
			and str(actor.world_info.get("definition_hash", "")) == _expected_definition_hash
			and actor.world_info == observer.world_info
		)
	):
		return false
	if not _check(
		"finisher_bait_is_inside_both_acquisition_ranges_and_outside_attack_reach",
		(
			FINISHER_BAIT.distance_to(FINISHER_DOG_HOMES[1]) < 8.0
			and FINISHER_BAIT.distance_to(FINISHER_DOG_HOMES[2]) < 8.0
			and FINISHER_BAIT.distance_to(FINISHER_DOG_HOMES[1]) > 1.9
			and FINISHER_BAIT.distance_to(FINISHER_DOG_HOMES[2]) > 1.9
		)
	):
		return false
	return _check(
		"finisher_exact_three_dog_fixture",
		await _wait_until(
			func():
				if observer.monsters.size() != 3:
					return false
				for id in FINISHER_DOG_HOMES:
					var dog := _monster_by_id(observer, id)
					if dog.is_empty():
						return false
				return true,
			16.0
		)
	)


func _wait_three_dogs_at_baseline(observer: GameConnection) -> bool:
	var stable_since := 0
	var deadline := Time.get_ticks_msec() + 16_000
	while Time.get_ticks_msec() < deadline:
		var stable := true
		for id in FINISHER_DOG_HOMES:
			var dog := _monster_by_id(observer, id)
			stable = (
				stable
				and not dog.is_empty()
				and int(dog.get("health", 0)) == 100
				and int(dog.get("activity", -1)) == 0
				and _position(dog).distance_to(FINISHER_DOG_HOMES[id]) < 0.1
			)
		if stable:
			if stable_since == 0:
				stable_since = Time.get_ticks_msec()
			elif Time.get_ticks_msec() - stable_since >= 500:
				return _check("finisher_three_dogs_healthy_idle_at_trusted_homes", true)
		else:
			stable_since = 0
		await process_frame
	return _check("finisher_three_dogs_healthy_idle_at_trusted_homes", false)


func _normalize_retained_finisher_fixture(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var sword := _owned_sword(actor, actor_id)
	if not _check("finisher_normalization_starts_unarmed", not bool(sword.get("equipped", false))):
		return false
	var c_before := _monster_by_id(observer, 3).duplicate(true)
	var restored_lives := {}
	for id in [1, 2]:
		var dog := _monster_by_id(observer, id)
		if int(dog.get("health", 0)) == 100:
			continue
		restored_lives[id] = int(dog.get("life_sequence", 0))
		if int(dog.get("health", 0)) > 0:
			if not await _defeat_injured_dog_unarmed(actor, observer, actor_id, id):
				return false
	actor.clear_combat_target()
	if not await _park_finisher_actor(actor, observer, actor_id):
		return false
	for id in restored_lives:
		var old_life := int(restored_lives[id])
		if not _check(
			"finisher_normalization_dog_%d_natural_respawn" % id,
			await _wait_until(
				func():
					var row := _monster_by_id(observer, id)
					return (
						int(row.get("life_sequence", 0)) > old_life
						and int(row.get("health", 0)) == 100
					),
				16.0
			)
		):
			return false
	var c_after := _monster_by_id(observer, 3)
	return _check(
		"finisher_normalization_preserves_healthy_c",
		(
			int(c_before.get("health", 0)) == 100
			and int(c_after.get("health", 0)) == 100
			and int(c_after.get("life_sequence", -1)) == int(c_before.get("life_sequence", -2))
		),
	)


func _defeat_injured_dog_unarmed(
	actor: GameConnection, observer: GameConnection, actor_id: String, dog_id: int
) -> bool:
	for _attempt in range(6):
		var dog := _monster_by_id(observer, dog_id)
		var before := int(dog.get("health", 0))
		if before == 0:
			break
		if not await _approach_finisher_dog(actor, observer, actor_id, dog_id):
			return false
		dog = _monster_by_id(observer, dog_id)
		if not await _raw_success(
			actor,
			"select_combat_target",
			[int(dog.id), int(dog.life_sequence)],
			[&"U32", &"U32"],
			"finisher_normalization_selects_dog_%d_at_%d" % [dog_id, before]
		):
			return false
		actor.perform_attack()
		if not _check(
			"finisher_normalization_dog_%d_hit_from_%d" % [dog_id, before],
			await _wait_until(
				func(): return int(_monster_by_id(observer, dog_id).get("health", 0)) < before, 2.0
			)
		):
			return false
		if int(_monster_by_id(observer, dog_id).get("health", 0)) > 0:
			var actor_position := _position(_player(observer, actor_id))
			var dog_position := _position(_monster_by_id(observer, dog_id))
			var away := (actor_position - dog_position).normalized()
			if away.is_zero_approx():
				away = Vector2.LEFT
			if not await _move_and_stop(actor, observer, actor_id, dog_position + away * 3.4, 2.0):
				return _check("finisher_normalization_retreats_after_hit", false)
		await create_timer(0.6).timeout
	return _check(
		"finisher_normalization_dog_%d_defeated" % dog_id,
		int(_monster_by_id(observer, dog_id).get("health", -1)) == 0,
	)


func _approach_finisher_dog(
	actor: GameConnection, observer: GameConnection, actor_id: String, dog_id: int
) -> bool:
	for _attempt in range(60):
		var actor_position := _position(_player(observer, actor_id))
		var dog_position := _position(_monster_by_id(observer, dog_id))
		if actor_position.distance_to(dog_position) <= 2.5:
			actor.stop_moving()
			return _check("finisher_normalization_reaches_dog_%d" % dog_id, true)
		var away := actor_position - dog_position
		if away.is_zero_approx():
			away = Vector2.LEFT
		var destination := dog_position + away.normalized() * 2.0
		actor.move_to(destination.x, destination.y)
		await create_timer(0.2).timeout
	actor.stop_moving()
	return _check("finisher_normalization_reaches_dog_%d" % dog_id, false)


func _park_finisher_actor(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var arrived := await _move_and_stop(actor, observer, actor_id, TRAINING_ACTOR_SAFE, 12.0)
	if not arrived:
		return _check("finisher_actor_parks_at_training_safe_waypoint", false)
	var outside_all := true
	for home: Vector2 in FINISHER_DOG_HOMES.values():
		outside_all = (
			outside_all and _position(_player(observer, actor_id)).distance_to(home) > 16.0
		)
	return _check("finisher_actor_parks_outside_all_home_chase", outside_all)


func _stage_first_whiff(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	for attempt in range(3):
		if await _stage_first_whiff_once(actor, observer, actor_id):
			return _check("finisher_first_whiff_geometry_is_stable", true)
		_timing_evidence.append({"phase": "finisher_restaging", "attempt": attempt + 1})
		if not await _park_finisher_actor(actor, observer, actor_id):
			break
		if not await _wait_three_dogs_at_baseline(observer):
			break
	return _check("finisher_first_whiff_geometry_is_stable", false)


func _stage_first_whiff_once(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	actor.move_to(FINISHER_BAIT.x, FINISHER_BAIT.y)
	var intercepted := await _wait_until(
		func():
			var a := _monster_by_id(observer, 1)
			var b := _monster_by_id(observer, 2)
			return (
				int(a.get("activity", -1)) == 2
				and int(b.get("activity", -1)) == 2
				and int(b.get("health", 0)) == 100
				and _position(a).distance_to(_position(b)) <= 0.5
			),
		8.0
	)
	actor.stop_moving()
	if not intercepted:
		_record_stage_snapshot("a_outer_attack_intercept_failed", observer, actor_id)
		return false
	if not await _wait_until(
		func(): return int(_player(observer, actor_id).get("activity", -1)) == 0, 1.0
	):
		_record_stage_snapshot("outer_intercept_stop_failed", observer, actor_id)
		return false
	var a_position := _position(_monster_by_id(observer, 1))
	var actor_position := _position(_player(observer, actor_id))
	var away := (actor_position - a_position).normalized()
	if away.is_zero_approx():
		away = Vector2.LEFT
	var destination := a_position + away * FINISHER_MISS_DISTANCE_M
	var travel_distance := actor_position.distance_to(destination)
	var required_remaining_us := ceili(travel_distance / 5.0 * 1_000_000.0) + 400_000
	var remaining_us := (
		int(_monster_by_id(observer, 1).get("action_ends_at_us", 0)) - observer.server_time_us
	)
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_stage_pre_retreat",
				"server_time_us": observer.server_time_us,
				"actor_position": [actor_position.x, actor_position.y],
				"a_position": [a_position.x, a_position.y],
				"destination": [destination.x, destination.y],
				"travel_distance_m": travel_distance,
				"required_remaining_us": required_remaining_us,
				"observed_remaining_us": remaining_us,
			}
		)
	)
	_record_stage_snapshot("pre_retreat", observer, actor_id)
	if remaining_us < required_remaining_us:
		_record_stage_snapshot("a_dynamic_attack_margin_failed", observer, actor_id)
		return false
	if not await _move_and_stop(actor, observer, actor_id, destination, 2.0):
		_record_stage_snapshot("retreat_arrival_failed", observer, actor_id)
		return false
	var a := _monster_by_id(observer, 1)
	var b := _monster_by_id(observer, 2)
	var arrival_position := _position(_player(observer, actor_id))
	var arrival_remaining_us := int(a.get("action_ends_at_us", 0)) - observer.server_time_us
	var ready := (
		int(a.get("activity", -1)) == 2
		and arrival_remaining_us >= 350_000
		and arrival_position.distance_to(_position(a)) >= 3.3
		and int(b.get("health", 0)) == 100
		and _position(a).distance_to(_position(b)) <= 0.5
	)
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_stage_retreat_arrival",
				"server_time_us": observer.server_time_us,
				"actor_position": [arrival_position.x, arrival_position.y],
				"a_position": [_position(a).x, _position(a).y],
				"b_position": [_position(b).x, _position(b).y],
				"a_remaining_us": arrival_remaining_us,
				"actor_a_distance_m": arrival_position.distance_to(_position(a)),
				"a_b_distance_m": _position(a).distance_to(_position(b)),
			}
		)
	)
	_record_stage_snapshot(
		"post_retreat_ready" if ready else "post_retreat_margin_failed", observer, actor_id
	)
	return ready


func _record_stage_snapshot(phase: String, observer: GameConnection, actor_id: String) -> void:
	var players := []
	for row: Dictionary in observer.players:
		(
			players
			. append(
				{
					"identity": str(row.get("identity", "")),
					"position": [_position(row).x, _position(row).y],
					"activity": int(row.get("activity", -1)),
					"health": int(row.get("health", -1)),
				}
			)
		)
	var dogs := []
	for id in [1, 2]:
		var dog := _monster_by_id(observer, id)
		(
			dogs
			. append(
				{
					"id": id,
					"position": [_position(dog).x, _position(dog).y],
					"health": int(dog.get("health", -1)),
					"activity": int(dog.get("activity", -1)),
					"action_started_at_us": int(dog.get("action_started_at_us", 0)),
					"action_ends_at_us": int(dog.get("action_ends_at_us", 0)),
				}
			)
		)
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_stage_" + phase,
				"server_time_us": observer.server_time_us,
				"actor_id": actor_id,
				"players": players,
				"dogs": dogs,
			}
		)
	)


func _send_finisher_direct_follow_up(
	actor: GameConnection, observer: GameConnection, action_start_us: int, step: int
) -> Dictionary:
	var timing: Array = {
		1: [480_000, 533_000, 550_000, 533_333, 602_564],
		2: [490_000, 540_000, 565_000, 543_248, 636_581],
		3: [380_000, 450_000, 475_000, 418_462, 664_615],
	}[step]
	var label := "finisher_step_%d_direct_follow_up" % (step + 1)
	if not _check(
		label + "_send_time_reached",
		await _wait_for_estimated_action_time(
			observer, action_start_us, timing[0], timing[1], timing[2], label
		)
	):
		return {}
	var result := await _raw_result(actor, "perform_attack", [], [])
	_record_raw_result(label, "perform_attack", result)
	if not _check(label + "_accepted", bool(result.accepted)):
		return {}
	if not _check(
		label + "_inside_source_window",
		(
			int(result.timestamp) > action_start_us + int(timing[3])
			and int(result.timestamp) <= action_start_us + int(timing[4])
		)
	):
		return {}
	return result


func _prove_terminal_area(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _stage_first_whiff(actor, observer, actor_id):
		return false
	var first_half := await _start_finisher_chain(actor, observer, actor_id)
	if first_half.is_empty():
		return false
	var fourth := await _finish_finisher_chain(actor, observer, actor_id, first_half.second)
	if fourth.is_empty():
		return false
	return await _mutate_during_finisher(actor, observer, actor_id, fourth)


func _start_finisher_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> Dictionary:
	var a := _monster_by_id(observer, 1)
	var selected := await _raw_success(
		actor,
		"select_combat_target",
		[int(a.id), int(a.life_sequence)],
		[&"U32", &"U32"],
		"finisher_selects_exact_a_life"
	)
	var first := {}
	if selected:
		first = await _start_action(actor, observer, actor_id, ROOT_COMBO_ONE, "finisher_combo_one")
	if first.is_empty():
		return {}
	if not _check(
		"finisher_combo_one_whiffs",
		await _wait_until(
			func():
				return (
					observer.server_time_us > int(first.action_started_at_us) + 350_000
					and int(_monster_by_id(observer, 1).get("health", 0)) == 100
				),
			1.0
		)
	):
		return {}
	var second_receipt := await _send_finisher_direct_follow_up(
		actor, observer, int(first.action_started_at_us), 1
	)
	if second_receipt.is_empty():
		return {}
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), ROOT_COMBO_TWO
	)
	if second.is_empty():
		_check("finisher_combo_two_replicates", false)
		return {}
	if not _check(
		"finisher_combo_two_hits_a_once",
		await _wait_until(func(): return int(_monster_by_id(observer, 1).health) == 65, 1.0)
	):
		return {}
	return {"first": first, "second": second}


func _finish_finisher_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String, second: Dictionary
) -> Dictionary:
	var third_receipt := await _send_finisher_direct_follow_up(
		actor, observer, int(second.action_started_at_us), 2
	)
	var third := {}
	if not third_receipt.is_empty():
		third = await _wait_action_after(
			observer, actor_id, int(second.attack_sequence), ROOT_COMBO_THREE
		)
	if third.is_empty():
		_check("finisher_combo_three_replicates", false)
		return {}
	if not _check(
		"finisher_combo_three_hits_a_once",
		await _wait_until(func(): return int(_monster_by_id(observer, 1).health) == 30, 1.0)
	):
		return {}
	var fourth_receipt := await _send_finisher_direct_follow_up(
		actor, observer, int(third.action_started_at_us), 3
	)
	if fourth_receipt.is_empty():
		return {}
	var fourth := await _wait_action_after(
		observer, actor_id, int(third.attack_sequence), FINISHER_COMBO_FOUR
	)
	if fourth.is_empty():
		_check("finisher_combo_four_replicates", false)
		return {}
	if not _check(
		"finisher_combo_four_source_duration",
		int(fourth.action_ends_at_us) - int(fourth.action_started_at_us) == 1_266_667
	):
		return {}
	return fourth


func _mutate_during_finisher(
	actor: GameConnection, observer: GameConnection, actor_id: String, fourth: Dictionary
) -> bool:
	var force_anchor := {"ready": false}
	var capture_first_reaction := func(rows: Array):
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
				force_anchor.observer_server_time_us = observer.server_time_us
				force_anchor.observed_at_ticks_us = Time.get_ticks_usec()
				return
	observer.monsters_changed.connect(capture_first_reaction)
	await _raw_rejection(
		actor, "perform_attack", [], [], "finisher_fifth_input_rejected", "complete"
	)
	if not await _raw_success(
		actor, "clear_combat_target", [], [], "finisher_target_clear_accepted"
	):
		return false
	var sword := _owned_sword(actor, actor_id)
	if not await _raw_success(
		actor,
		"unequip_item",
		[int(sword.id), _sword_bag_cell],
		[&"U64", &"U8"],
		"finisher_unequip_after_action_accepted"
	):
		return false
	if not _check(
		"finisher_target_and_equipment_mutations_project_before_area",
		await _wait_until(
			func():
				return (
					actor.selected_combat_target().is_empty()
					and not bool(_owned_sword(actor, actor_id).get("equipped", true))
					and int(_monster_by_id(observer, 1).health) == 30
				),
			0.5
		)
	):
		return false
	var observed := await _observe_area_and_force(actor, observer, actor_id, fourth, force_anchor)
	if observer.monsters_changed.is_connected(capture_first_reaction):
		observer.monsters_changed.disconnect(capture_first_reaction)
	return observed


func _observe_area_and_force(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	fourth: Dictionary,
	force_anchor: Dictionary
) -> bool:
	var start := await _observe_area_start(actor, observer, force_anchor)
	if start.is_empty():
		return false
	return await _observe_force_finish(observer, actor_id, fourth, start)


func _observe_area_start(
	actor: GameConnection, observer: GameConnection, force_anchor: Dictionary
) -> Dictionary:
	var reaction := await _wait_until(
		func():
			var a := _monster_by_id(observer, 1)
			var b := _monster_by_id(observer, 2)
			return (
				int(a.get("health", -1)) == 0
				and int(b.get("health", -1)) == 65
				and str(b.get("attack_action_id", "")) == FINISHER_FRONT_KNOCKDOWN
				and bool(force_anchor.ready)
			),
		1.5
	)
	if not _check("finisher_area_hits_inside_a_and_b", reaction):
		return {}
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_first_subscribed_reaction",
				"position": [force_anchor.position.x, force_anchor.position.y],
				"action_started_at_us": force_anchor.action_started_at_us,
				"action_ends_at_us": force_anchor.action_ends_at_us,
				"attack_sequence": force_anchor.attack_sequence,
				"observer_server_time_us": force_anchor.observer_server_time_us,
				"observed_at_ticks_us": force_anchor.observed_at_ticks_us,
			}
		)
	)
	if not _check(
		"finisher_area_leaves_outside_c_unchanged",
		int(_monster_by_id(observer, 3).get("health", -1)) == 100
	):
		return {}
	if not _check(
		"finisher_target_stays_clear_after_lethal_a", actor.selected_combat_target().is_empty()
	):
		return {}
	if not _check(
		"finisher_front_knockdown_has_source_duration",
		int(force_anchor.action_ends_at_us) - int(force_anchor.action_started_at_us) == 1_166_667
	):
		return {}
	return {"force_start": force_anchor.position, "reaction_sequence": force_anchor.attack_sequence}


func _observe_force_finish(
	observer: GameConnection, actor_id: String, fourth: Dictionary, start: Dictionary
) -> bool:
	if not _check(
		"finisher_current_root_continues_after_target_and_equipment_change",
		await _wait_until(
			func():
				return _position(_player(observer, actor_id)).distance_to(_position(fourth)) > 0.2,
			1.0
		)
	):
		return false
	var standup := await _wait_until(
		func():
			return (
				str(_monster_by_id(observer, 2).get("attack_action_id", ""))
				== FINISHER_FRONT_STANDUP
			),
		2.0
	)
	if not _check("finisher_front_standup_replicates", standup):
		return false
	var standup_row := _monster_by_id(observer, 2)
	if not _check(
		"finisher_front_standup_has_source_duration",
		int(standup_row.action_ends_at_us) - int(standup_row.action_started_at_us) == 1_000_000
	):
		return false
	if not await _check_finisher_endpoints(observer, actor_id, fourth, start):
		return false
	await create_timer(0.25).timeout
	return _check(
		"finisher_area_is_once_per_exact_life",
		(
			int(_monster_by_id(observer, 2).health) == 65
			and int(_monster_by_id(observer, 3).health) == 100
		)
	)


func _check_finisher_endpoints(
	observer: GameConnection, actor_id: String, fourth: Dictionary, start: Dictionary
) -> bool:
	if not await _wait_action_end(observer, actor_id, int(fourth.action_ends_at_us)):
		return _check("finisher_combo_four_action_finishes", false)
	var force_delta := _position(_monster_by_id(observer, 2)).distance_to(start.force_start)
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_force_endpoint",
				"start_position": [start.force_start.x, start.force_start.y],
				"final_position":
				[
					_position(_monster_by_id(observer, 2)).x,
					_position(_monster_by_id(observer, 2)).y,
				],
				"distance_m": force_delta,
				"error_m": absf(force_delta - FINISHER_FORCE_DISTANCE_M),
			}
		)
	)
	if not _check(
		"finisher_force_reaches_derived_endpoint",
		absf(force_delta - FINISHER_FORCE_DISTANCE_M) <= 0.003
	):
		return false
	return _check_finisher_root_endpoint(observer, actor_id, fourth)


func _check_finisher_root_endpoint(
	observer: GameConnection, actor_id: String, fourth: Dictionary
) -> bool:
	var start_position := _position(fourth)
	var heading := float(fourth.heading)
	var endpoint_z := -1.1964712524414062
	var expected := start_position + Vector2(sin(heading) * endpoint_z, cos(heading) * endpoint_z)
	var actual := _position(_player(observer, actor_id))
	var error_m := actual.distance_to(expected)
	(
		_timing_evidence
		. append(
			{
				"phase": "finisher_combo_four_root_endpoint",
				"start_position": [start_position.x, start_position.y],
				"expected_position": [expected.x, expected.y],
				"actual_position": [actual.x, actual.y],
				"heading": heading,
				"error_m": error_m,
			}
		)
	)
	return _check(
		"finisher_combo_four_matches_linear_endpoint", error_m <= ROOT_POSITION_TOLERANCE_M
	)


func _monster_by_id(client: GameConnection, id: int) -> Dictionary:
	for row: Dictionary in client.monsters:
		if int(row.get("id", 0)) == id:
			return row
	return {}
