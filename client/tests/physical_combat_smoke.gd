extends "res://tests/combo_smoke.gd"
## Focused current-protocol proof through two real subscriptions and ordinary reducers.

const SWORD_DAMAGE := [17, 18, 20]
const UNARMED_DAMAGE := [1, 2, 3, 4, 5]
const DOG_DAMAGE := [29, 30, 32, 33, 35]
var _expected_sword_domain: Array = SWORD_DAMAGE
var _incoming: Array = []
var _previous_health: Dictionary = {}


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
		ready = await _prove_physical_display(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _prove_targetless_physical(actor, observer, actor_id)
	if ready:
		observer.players_changed.connect(func(_rows: Array): _record_incoming(observer, actor_id))
		ready = await _approach_dog(actor, observer, actor_id)
	if ready:
		ready = await _physical_hit(actor, observer, actor_id, true, "captured_sword")
	if ready:
		ready = await _physical_hit(actor, observer, actor_id, false, "unarmed_next_action")
	if ready:
		ready = await _physical_hit(actor, observer, actor_id, false, "unarmed_second_action")
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = await _kill_with_physical_hits(actor, observer, actor_id)
	if ready:
		ready = await _prove_physical_reentry(actor, observer, actor_id, observer_id)
	if ready:
		_tokens.clear()
	if not ready:
		_check("physical_scenario_completed", false)
	_finish()


func _enter_physical_world(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	actor.select_character(actor_id)
	observer.select_character(observer_id)
	if not _check(
		"physical_characters_selected",
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
		"physical_mutual_subscribed_presence",
		await _wait_until(
			func():
				return (
					actor.state == "connected"
					and observer.state == "connected"
					and not _player(actor, observer_id).is_empty()
					and not _player(observer, actor_id).is_empty()
					and actor.monsters_for_definition(101).size() == 1
					and observer.monsters_for_definition(101).size() == 1
				),
			20.0
		)
	):
		return false
	return _check(
		"physical_protocol_and_definition_match",
		(
			int(actor.world_info.protocol_version) == GameConnection.EXPECTED_PROTOCOL_VERSION
			and str(actor.world_info.definition_hash) == _expected_definition_hash
			and str(actor.world_info.map_id) == "training"
			and actor.world_info == observer.world_info
		)
	)


func _display_is(client: GameConnection, identity: String, minimum: int, maximum: int) -> bool:
	var row := client.progression_for(identity)
	return (
		int(row.get("display_attack_min", -1)) == minimum
		and int(row.get("display_attack_max", -1)) == maximum
		and int(row.get("display_defense", -1)) == 5
	)


func _prove_physical_display(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	if not _check(
		"physical_initial_private_unarmed_display",
		await _wait_until(
			func():
				return (
					_display_is(actor, actor_id, 10, 10)
					and _display_is(observer, observer_id, 10, 10)
				),
			5.0
		)
	):
		return false
	await _raw_rejection(
		actor,
		"allocate_stat",
		[actor_id.hex_decode(), "st"],
		[&"__identity__", &"String"],
		"physical_no_free_stat_points",
		"No unspent"
	)
	await _raw_rejection(
		observer,
		"allocate_stat",
		[actor_id.hex_decode(), "st"],
		[&"__identity__", &"String"],
		"physical_foreign_stat_rejected",
		"selected"
	)
	if not await _equip_combo_sword(actor, observer, actor_id):
		return false
	if not _check(
		"physical_equipped_owner_display",
		await _wait_until(func(): return _display_is(actor, actor_id, 28, 31))
	):
		return false
	actor.equip_item(int(_owned_sword(actor, actor_id).id))
	await create_timer(0.2).timeout
	return _check(
		"physical_idempotent_equipment_and_owner_privacy",
		(
			_display_is(actor, actor_id, 28, 31)
			and _display_is(observer, observer_id, 10, 10)
			and observer.progression_for(actor_id).is_empty()
			and actor.progression_for(observer_id).is_empty()
			and _private_progression(actor, 4)
			and _private_progression(observer, 1)
		)
	)


func _prove_targetless_physical(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var before := _monster(observer).duplicate(true)
	await _raw_rejection(
		actor,
		"select_combat_target",
		[int(before.id), int(before.life_sequence) + 1],
		[&"U32", &"U32"],
		"physical_stale_target_life_rejected",
		"life"
	)
	actor.clear_combat_target()
	if not await _wait_until(func(): return actor.selected_combat_target().is_empty()):
		return _check("physical_targetless_selection_cleared", false)
	var action := await _start_action(actor, observer, actor_id, COMBO_ONE, "physical_targetless")
	if (
		action.is_empty()
		or not await _wait_action_end(observer, actor_id, int(action.action_ends_at_us))
	):
		return false
	return _check(
		"physical_targetless_no_damage",
		_monster(actor).health == before.health and _monster(observer).health == before.health
	)


func _physical_hit(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	unequip_after_accept: bool,
	label: String
) -> bool:
	if not await _approach_dog(actor, observer, actor_id):
		return false
	var before := _monster(observer).duplicate(true)
	var armed := bool(_owned_sword(actor, actor_id).equipped)
	var domain: Array = _expected_sword_domain if armed else UNARMED_DAMAGE
	if not await _raw_success(
		actor,
		"select_combat_target",
		[int(before.id), int(before.life_sequence)],
		[&"U32", &"U32"],
		label + "_select_life"
	):
		return false
	var sequence := int(_player(observer, actor_id).attack_sequence)
	var accepted := await _raw_result(actor, "perform_attack", [], [])
	_record_raw_result(label + "_attack", "perform_attack", accepted)
	if not _check(label + "_accepted", bool(accepted.accepted)):
		return false
	if unequip_after_accept:
		var unequipped := await _raw_result(
			actor,
			"unequip_item",
			[int(_owned_sword(actor, actor_id).id), _sword_bag_cell],
			[&"U64", &"U8"]
		)
		_record_raw_result(label + "_unequip", "unequip_item", unequipped)
		if not _check(
			label + "_unequipped_before_due_hit",
			(
				bool(unequipped.accepted)
				and int(unequipped.timestamp) < int(accepted.timestamp) + 192_308
			)
		):
			return false
	return await _observe_physical_hit(
		actor,
		observer,
		actor_id,
		{
			"before": before,
			"armed": armed,
			"domain": domain,
			"sequence": sequence,
			"accepted": accepted,
			"unequip_after_accept": unequip_after_accept,
			"label": label,
		}
	)


func _observe_physical_hit(
	actor: GameConnection, observer: GameConnection, actor_id: String, sample: Dictionary
) -> bool:
	var before: Dictionary = sample.before
	var armed: bool = sample.armed
	var domain: Array = sample.domain
	var sequence: int = sample.sequence
	var accepted: Dictionary = sample.accepted
	var unequip_after_accept: bool = sample.unequip_after_accept
	var label: String = sample.label
	if not _check(
		label + "_same_life_hit_on_both_clients",
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) < int(before.health)
					and _monster(actor).health == _monster(observer).health
					and _monster(actor).life_sequence == before.life_sequence
					and _monster(observer).life_sequence == before.life_sequence
				),
			2.0
		)
	):
		return false
	var after := int(_monster(observer).health)
	var damage := int(before.health) - after
	var valid := domain.any(func(value: int): return mini(value, int(before.health)) == damage)
	_timing_evidence.append(
		{
			"label": label,
			"monster_id": before.id,
			"life_sequence": before.life_sequence,
			"health_before": before.health,
			"health_after": after,
			"applied_damage": damage,
			"nominal_domain": domain,
			"attack_receipt_us": accepted.timestamp,
			"owner_display": actor.progression_for(actor_id).duplicate(true)
		}
	)
	if not _check(label + "_source_formula_domain", valid):
		return false
	var end_us := int(accepted.timestamp) + (1_000_000 if armed else 933_333)
	if not _check(label + "_action_finishes", await _wait_action_end(observer, actor_id, end_us)):
		return false
	if (
		unequip_after_accept
		and not _check(label + "_unarmed_projection", _display_is(actor, actor_id, 10, 10))
	):
		return false
	return _check(
		label + "_exactly_one_hit",
		(
			int(_monster(observer).health) == after
			and int(_monster(actor).health) == after
			and int(_player(observer, actor_id).attack_sequence) == sequence + 1
		)
	)


func _record_incoming(observer: GameConnection, actor_id: String) -> void:
	var row := _player(observer, actor_id)
	if row.is_empty():
		return
	if not _previous_health.is_empty() and row.life_sequence == _previous_health.life_sequence:
		var delta := int(_previous_health.health) - int(row.health)
		if delta > 0:
			_incoming.append(
				{
					"damage": delta,
					"health_before": _previous_health.health,
					"health_after": row.health,
					"player_life": row.life_sequence,
					"dog_life": _monster(observer).life_sequence,
					"dog_attack_sequence": _monster(observer).attack_sequence
				}
			)
	_previous_health = row.duplicate(true)


func _kill_with_physical_hits(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	for index in range(8):
		if int(_monster(observer).health) == 0:
			break
		if not await _physical_hit(actor, observer, actor_id, false, "sword_%d" % index):
			return false
	_timing_evidence.append({"incoming_dog_hits": _incoming.duplicate(true)})
	if not _check(
		"physical_dog_formula_domain",
		(
			not _incoming.is_empty()
			and _incoming.all(func(row: Dictionary): return int(row.damage) in DOG_DAMAGE)
		)
	):
		return false
	if not _check(
		"physical_ordinary_kill_rewards_once",
		await _wait_until(
			func():
				return int(_monster(observer).health) == 0 and _has_experience(actor, actor_id, 15),
			5.0
		)
	):
		return false
	var life := int(_monster(observer).life_sequence)
	actor.move_to(TRAINING_ACTOR_SAFE.x, TRAINING_ACTOR_SAFE.y)
	if not _check(
		"physical_natural_new_dog_life",
		await _wait_until(
			func():
				return (
					int(_monster(observer).life_sequence) > life
					and int(_monster(observer).health) == 100
				),
			16.0
		)
	):
		return false
	return await _move_far_from_dog(actor, observer, actor_id)


func _prove_physical_reentry(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	actor.disconnect_game()
	if not _check(
		"physical_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty())
	):
		return false
	if not await _reconnect_idle(actor, observer, actor_id):
		return false
	if not _check(
		"physical_reconnect_rebuilds_private_display",
		await _wait_until(
			func():
				return _display_is(actor, actor_id, 28, 31) and _has_experience(actor, actor_id, 15),
			5.0
		)
	):
		return false
	return await _prove_physical_switch(actor, observer, actor_id, observer_id)


func _prove_physical_switch(
	actor: GameConnection, observer: GameConnection, actor_id: String, observer_id: String
) -> bool:
	var alternative := str(actor.characters[1].character_id)
	actor.leave_world()
	if not await _wait_until(func(): return actor.state == "lobby"):
		return _check("physical_switch_lobby", false)
	actor.select_character(alternative)
	if not await _wait_until(func(): return actor.local_identity == alternative):
		return _check("physical_switch_selected", false)
	actor.enter_selected()
	if not _check(
		"physical_switch_unarmed_display",
		await _wait_until(
			func():
				return (
					actor.state == "connected"
					and _display_is(actor, alternative, 10, 10)
					and not _player(observer, alternative).is_empty()
				),
			5.0
		)
	):
		return false
	return _check(
		"physical_reentry_stays_private",
		(
			_private_progression(actor, 4)
			and _private_progression(observer, 1)
			and observer.progression_for(actor_id).is_empty()
			and actor.progression_for(observer_id).is_empty()
		)
	)
