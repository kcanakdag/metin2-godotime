extends "res://tests/physical_combat_smoke.gd"
## Earn five ordinary kills per refreshed session, then spend three real stat points.

var _target_kills := 5
var _stat_cases: Array = []
var _growth_transition_ticks: Array[int] = []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size() - 1):
		if args[index] == "--account-config":
			var config: Dictionary = JSON.parse_string(
				FileAccess.get_file_as_string(args[index + 1])
			)
			_target_kills = int(config.get("target_kills", 5))
	var fixture: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://tests/physical-stat-cases.json")
	)
	_stat_cases = fixture.cases
	# JSON numbers are floats in Godot; Array membership compares Variant types.
	for expected: Dictionary in _stat_cases:
		expected.sword_damage = expected.sword_damage.map(func(value: Variant): return int(value))
		expected.dog_damage = expected.dog_damage.map(func(value: Variant): return int(value))
	super._initialize()


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _growth_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_physical_world(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _move_far_from_dog(actor, observer, actor_id)
	if ready and _target_kills == 5:
		ready = await _prepare_growth_dog(actor, observer, observer_id)
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = _check(
			"growth_starts_at_expected_kills", _growth_matches(actor, actor_id, _target_kills - 5)
		)
	if ready:
		for killed in range(_target_kills - 4, _target_kills + 1):
			if not await _earn_one_kill(actor, observer, actor_id, killed):
				ready = false
				break
	if ready:
		ready = _check(
			"growth_quarter_and_private_progression",
			(
				_growth_matches(actor, actor_id, _target_kills)
				and _private_progression(actor, 4)
				and _private_progression(observer, 1)
				and observer.progression_for(actor_id).is_empty()
			)
		)
	if ready and _target_kills == 20:
		ready = await _prove_earned_allocations(actor, observer, actor_id)
	if not ready:
		_check("physical_growth_completed", false)
	_timing_evidence.append(
		{"target_kills": _target_kills, "progression": actor.progression_for(actor_id)}
	)
	_tokens.clear()
	_finish()


func _prepare_growth_dog(
	actor: GameConnection, observer: GameConnection, observer_id: String
) -> bool:
	# A failed prior run can leave an injured living dog. The observer completes
	# that old life with ordinary combat so the measured character starts at zero XP.
	var old_life := int(_monster(actor).life_sequence)
	if int(_monster(actor).health) == 100:
		return true
	if not await _equip_combo_sword(observer, actor, observer_id):
		return false
	for hit in range(8):
		if int(_monster(actor).health) == 0:
			break
		if not await _physical_hit(
			observer, actor, observer_id, false, "growth_prepare_old_life_%d" % hit
		):
			return false
	observer.move_to(TRAINING_OBSERVER_SAFE.x, TRAINING_OBSERVER_SAFE.y)
	if not _check(
		"growth_preparation_natural_fresh_life",
		await _wait_until(
			func():
				return (
					int(_monster(actor).life_sequence) > old_life
					and int(_monster(actor).health) == 100
				),
			16.0
		)
	):
		return false
	return await _park_observer(observer, actor, observer_id)


func _growth_rosters(actor: GameConnection, observer: GameConnection) -> bool:
	if _target_kills == 5:
		return await _create_rosters(actor, observer)
	actor.connect_account(_server, _database, str(_tokens[0]), "physical-growth-owner")
	observer.connect_account(_server, _database, str(_tokens[1]), "physical-growth-observer")
	return _check(
		"growth_session_reconnect_preserves_rosters",
		await _wait_until(
			func():
				return (
					actor.state == "lobby"
					and observer.state == "lobby"
					and actor.characters.size() == 4
					and observer.characters.size() == 1
				),
			20.0
		)
	)


func _growth_matches(actor: GameConnection, actor_id: String, kills: int) -> bool:
	var row := actor.progression_for(actor_id)
	return (
		int(row.get("level", -1)) == (2 if kills == 20 else 1)
		and int(row.get("experience", -1)) == (0 if kills == 20 else kills * 15)
		and int(row.get("unspent_stat_points", -1)) == mini(kills / 5, 3)
	)


func _earn_one_kill(
	actor: GameConnection, observer: GameConnection, actor_id: String, killed: int
) -> bool:
	if not _check(
		"growth_%d_live_dog" % killed,
		await _wait_until(func(): return int(_monster(observer).health) == 100, 16.0)
	):
		return false
	var life := int(_monster(observer).life_sequence)
	for hit in range(8):
		if int(_monster(observer).health) == 0:
			break
		await _use_growth_potion(actor, observer, actor_id)
		if not await _physical_hit(
			actor, observer, actor_id, false, "growth_%d_hit_%d" % [killed, hit]
		):
			return false
	if not _check(
		"growth_%d_exact_reward" % killed,
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) == 0 and _growth_matches(actor, actor_id, killed)
				),
			5.0
		)
	):
		return false
	actor.move_to(TRAINING_ACTOR_SAFE.x, TRAINING_ACTOR_SAFE.y)
	var wait_started := Time.get_ticks_msec()
	var clock_started := observer.server_time_us
	var respawned := await _wait_until(
		func():
			return (
				int(_monster(observer).life_sequence) > life
				and int(_monster(observer).health) == 100
			),
		16.0
	)
	(
		_timing_evidence
		. append(
			{
				"phase": "growth_respawn",
				"kill": killed,
				"elapsed_ms": Time.get_ticks_msec() - wait_started,
				"server_elapsed_us": observer.server_time_us - clock_started,
				"server_time_us": observer.server_time_us,
				"monster": _monster(observer).duplicate(true),
				"client_state": observer.state,
			}
		)
	)
	if not _check("growth_%d_new_life" % killed, respawned):
		return false
	return await _move_far_from_dog(actor, observer, actor_id)


func _use_growth_potion(actor: GameConnection, observer: GameConnection, actor_id: String) -> void:
	var player := _player(observer, actor_id)
	if int(player.health) >= 400 or int(player.health) == 0:
		return
	for row: Dictionary in actor.inventory:
		if str(row.owner) == actor_id and int(row.vnum) == 27001 and int(row.count) > 0:
			await _raw_success(actor, "use_item", [int(row.id)], [&"U64"], "growth_ordinary_potion")
			return


func _case_matches(actor: GameConnection, actor_id: String, expected: Dictionary) -> bool:
	var row := actor.progression_for(actor_id)
	for field in ["level", "strength", "vitality", "dexterity"]:
		if int(row.get(field, -1)) != int(expected[field]):
			return false
	return (
		int(row.get("display_attack_min", -1)) == int(expected.attack_min)
		and int(row.get("display_attack_max", -1)) == int(expected.attack_max)
		and int(row.get("display_defense", -1)) == int(expected.defense)
		and int(row.get("unspent_stat_points", -1)) == int(expected.unspent)
	)


func _prove_earned_allocations(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not _check("growth_level_two_display", _case_matches(actor, actor_id, _stat_cases[0])):
		return false
	var passed := await _strength_during_queue(actor, observer, actor_id)
	if not passed and not _case_matches(actor, actor_id, _stat_cases[1]):
		return false
	for step in [2, 3]:
		var allocated := await _allocate_defensive_stat(actor, observer, actor_id, step)
		passed = passed and allocated
		if not allocated and not _case_matches(actor, actor_id, _stat_cases[step]):
			return false
	var private_final := _check(
		"growth_all_three_points_spent_privately",
		(
			observer.progression_for(actor_id).is_empty()
			and _case_matches(actor, actor_id, _stat_cases[3])
		)
	)
	return passed and private_final


func _allocate_defensive_stat(
	actor: GameConnection, observer: GameConnection, actor_id: String, step: int
) -> bool:
	if not await _move_far_from_dog(actor, observer, actor_id):
		return false
	var health := int(_player(observer, actor_id).health)
	var maximum := int(_player(observer, actor_id).max_health)
	var code := "ht" if step == 2 else "dx"
	if not await _raw_success(
		actor,
		"allocate_stat",
		[actor_id.hex_decode(), code],
		[&"__identity__", &"String"],
		"growth_spends_" + code
	):
		return false
	if not _check(
		"growth_" + code + "_display_and_no_heal",
		await _wait_until(
			func():
				return (
					_case_matches(actor, actor_id, _stat_cases[step])
					and int(_player(observer, actor_id).health) == health
					and (
						int(_player(observer, actor_id).max_health)
						== maximum + (40 if step == 2 else 0)
					)
				),
			5.0
		)
	):
		return false
	_expected_sword_domain = _stat_cases[step].sword_damage
	if not await _physical_hit(actor, observer, actor_id, false, "growth_after_" + code):
		return false
	if not await _sample_incoming(actor, observer, actor_id, _stat_cases[step]):
		return false
	return true


func _strength_during_queue(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	var dog := _monster(observer).duplicate(true)
	if not await _raw_success(
		actor,
		"select_combat_target",
		[int(dog.id), int(dog.life_sequence)],
		[&"U32", &"U32"],
		"growth_queue_exact_target"
	):
		return false
	_growth_transition_ticks.clear()
	observer.server_clock_changed.connect(_record_growth_tick)
	var first := await _raw_result(actor, "perform_attack", [], [])
	_record_raw_result("growth_queue_first", "perform_attack", first)
	if not _check("growth_queue_first_accepted", bool(first.accepted)):
		return false
	await create_timer(0.22).timeout
	var queue := await _raw_result(actor, "perform_attack", [], [])
	var stat := await _raw_result(
		actor, "allocate_stat", [actor_id.hex_decode(), "st"], [&"__identity__", &"String"]
	)
	_record_raw_result("growth_queue_receipt", "perform_attack", queue)
	_record_raw_result("growth_queue_stat_receipt", "allocate_stat", stat)
	if not _check(
		"growth_strength_changes_before_queued_transition",
		(
			bool(queue.accepted)
			and bool(stat.accepted)
			and int(queue.timestamp) >= int(first.timestamp) + 167_094
			and int(stat.timestamp) < int(first.timestamp) + 533_333
		)
	):
		return false
	# Send the timing-sensitive intents first; the hit subscription may follow its ACK.
	await _wait_until(func(): return int(_monster(observer).health) < int(dog.health), 0.2)
	var before := int(_monster(observer).health)
	if not _check(
		"growth_first_hit_uses_old_stats", int(dog.health) - before in _stat_cases[0].sword_damage
	):
		return false
	return await _observe_strength_transition(actor, observer, actor_id, before, first)


func _record_growth_tick(timestamp_us: int) -> void:
	_growth_transition_ticks.append(timestamp_us)
	if _growth_transition_ticks.size() > 64:
		_growth_transition_ticks.pop_front()


func _observe_strength_transition(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	first_health: int,
	first: Dictionary
) -> bool:
	if not _check(
		"growth_second_hit_uses_new_stats",
		await _wait_until(
			func():
				return (
					first_health - int(_monster(observer).health) in _stat_cases[1].sword_damage
					and _monster(observer).health == _monster(actor).health
					and _case_matches(actor, actor_id, _stat_cases[1])
				),
			2.0
		)
	):
		return false
	var second := _player(observer, actor_id).duplicate(true)
	var boundary := int(first.timestamp) + 533_333
	var due_ticks := _growth_transition_ticks.filter(func(tick: int): return tick > boundary)
	(
		_timing_evidence
		. append(
			{
				"phase": "growth_strength_transition",
				"first_health": first_health,
				"second_health": _monster(observer).health,
				"transition_boundary_us": boundary,
				"subscribed_ticks": _growth_transition_ticks.duplicate(),
				"second_action": second,
				"owner_progression": actor.progression_for(actor_id),
			}
		)
	)
	if not _check(
		"growth_second_is_queued_combo_two",
		(
			str(second.attack_action_id) == COMBO_TWO
			and not due_ticks.is_empty()
			and int(second.action_started_at_us) == due_ticks[0]
			and int(second.action_ends_at_us) - int(second.action_started_at_us) == 933_333
		)
	):
		return false
	return _check(
		"growth_strength_combo_finishes",
		await _wait_action_end(observer, actor_id, int(second.action_ends_at_us))
	)


func _sample_incoming(
	actor: GameConnection, observer: GameConnection, actor_id: String, expected: Dictionary
) -> bool:
	var before := int(_player(observer, actor_id).health)
	var domain: Array = expected.dog_damage
	var sampled := await _wait_until(
		func():
			return (
				before - int(_player(observer, actor_id).health) in domain
				and _player(actor, actor_id).health == _player(observer, actor_id).health
			),
		2.5
	)
	_timing_evidence.append(
		{
			"phase": "growth_incoming",
			"case": expected.id,
			"before": before,
			"after": _player(observer, actor_id).health,
			"expected_domain": domain
		}
	)
	return _check("growth_" + str(expected.id) + "_incoming_formula", sampled)
