extends "res://tests/finisher_smoke.gd"
## The physical formula preserves area capture, two victims, roots and GREAT reactions.

const PHYSICAL_SWORD_DAMAGE := [17, 18, 20]
var _health_history := {"actor": {}, "observer": {}}
var _area_anchors := {"actor": {}, "observer": {}}
var _area_health_before: Dictionary = {}
var _area_active := false
var _prefix_health := 100


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
		ready = await _wait_three_dogs_at_baseline(observer)
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		_record_physical_rows("actor", actor.monsters)
		_record_physical_rows("observer", observer.monsters)
		actor.monsters_changed.connect(func(rows: Array): _record_physical_rows("actor", rows))
		observer.monsters_changed.connect(
			func(rows: Array): _record_physical_rows("observer", rows)
		)
		ready = await _prove_terminal_area(actor, observer, actor_id)
	if ready:
		ready = await _park_finisher_actor(actor, observer, actor_id)
	if ready:
		actor.disconnect_game()
		ready = _check(
			"physical_finisher_disconnect_removes_presence",
			await _wait_until(func(): return _player(observer, actor_id).is_empty())
		)
	if ready:
		ready = await _reconnect_idle(actor, observer, actor_id)
	if not ready:
		_check("physical_finisher_completed", false)
	_timing_evidence.append(
		{"physical_health_history": _health_history, "area_anchors": _area_anchors}
	)
	_tokens.clear()
	_finish()


func _record_physical_rows(viewer: String, rows: Array) -> void:
	for row: Dictionary in rows:
		var id := int(row.id)
		if not _health_history[viewer].has(id):
			_health_history[viewer][id] = []
		var history: Array = _health_history[viewer][id]
		var changed: bool = (
			history.is_empty()
			or history[-1].health != row.health
			or history[-1].life_sequence != row.life_sequence
		)
		if changed:
			history.append(
				{
					"health": int(row.health),
					"life_sequence": int(row.life_sequence),
					"action_id": str(row.attack_action_id)
				}
			)
		if _area_active and id in [1, 2] and not _area_anchors[viewer].has(id):
			if (
				str(row.attack_action_id) == FINISHER_FRONT_KNOCKDOWN
				and int(row.health) < int(_area_health_before[id].health)
			):
				_area_anchors[viewer][id] = row.duplicate(true)


func _start_finisher_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> Dictionary:
	var target := _monster_by_id(observer, 1)
	if not await _raw_success(
		actor,
		"select_combat_target",
		[int(target.id), int(target.life_sequence)],
		[&"U32", &"U32"],
		"physical_finisher_selects_exact_life"
	):
		return {}
	var first := await _start_action(
		actor, observer, actor_id, ROOT_COMBO_ONE, "physical_finisher_one"
	)
	if first.is_empty():
		return {}
	if not _check(
		"physical_finisher_first_whiffs",
		await _wait_until(
			func():
				return (
					observer.server_time_us > int(first.action_started_at_us) + 350_000
					and int(_monster_by_id(observer, 1).health) == 100
				),
			1.0
		)
	):
		return {}
	var receipt := await _send_finisher_direct_follow_up(
		actor, observer, int(first.action_started_at_us), 1
	)
	if receipt.is_empty():
		return {}
	var second := await _wait_action_after(
		observer, actor_id, int(first.attack_sequence), ROOT_COMBO_TWO
	)
	if (
		second.is_empty()
		or not await _physical_prefix_hit(actor, observer, "physical_finisher_second")
	):
		return {}
	return {"first": first, "second": second}


func _physical_prefix_hit(actor: GameConnection, observer: GameConnection, label: String) -> bool:
	if not _check(
		label + "_subscribed_hit",
		await _wait_until(
			func():
				return (
					int(_monster_by_id(observer, 1).health) < _prefix_health
					and _monster_by_id(actor, 1).health == _monster_by_id(observer, 1).health
				),
			1.0
		)
	):
		return false
	var health := int(_monster_by_id(observer, 1).health)
	var damage := _prefix_health - health
	_timing_evidence.append(
		{"phase": label, "before": _prefix_health, "after": health, "damage": damage}
	)
	_prefix_health = health
	return _check(label + "_formula_domain", damage in PHYSICAL_SWORD_DAMAGE)


func _finish_finisher_chain(
	actor: GameConnection, observer: GameConnection, actor_id: String, second: Dictionary
) -> Dictionary:
	var third_receipt := await _send_finisher_direct_follow_up(
		actor, observer, int(second.action_started_at_us), 2
	)
	if third_receipt.is_empty():
		return {}
	var third := await _wait_action_after(
		observer, actor_id, int(second.attack_sequence), ROOT_COMBO_THREE
	)
	if (
		third.is_empty()
		or not await _physical_prefix_hit(actor, observer, "physical_finisher_third")
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
		_check("physical_finisher_fourth_replicates", false)
		return {}
	_check(
		"physical_finisher_fourth_source_duration",
		int(fourth.action_ends_at_us) - int(fourth.action_started_at_us) == 1_266_667
	)
	return fourth


func _mutate_during_finisher(
	actor: GameConnection, observer: GameConnection, actor_id: String, fourth: Dictionary
) -> bool:
	for id in [1, 2, 3]:
		_area_health_before[id] = _monster_by_id(observer, id).duplicate(true)
	_area_active = true
	await _raw_rejection(
		actor, "perform_attack", [], [], "physical_finisher_fifth_rejected", "complete"
	)
	if not await _raw_success(
		actor, "clear_combat_target", [], [], "physical_finisher_clear_accepted"
	):
		return false
	var unequip := await _raw_result(
		actor,
		"unequip_item",
		[int(_owned_sword(actor, actor_id).id), _sword_bag_cell],
		[&"U64", &"U8"]
	)
	_record_raw_result("physical_finisher_unequip", "unequip_item", unequip)
	if not _check(
		"physical_finisher_mutations_before_area",
		(
			bool(unequip.accepted)
			and int(unequip.timestamp) < int(fourth.action_started_at_us) + 666_667
		)
	):
		return false
	if not _check(
		"physical_finisher_two_victims_on_both_clients",
		await _wait_until(
			func(): return _area_anchors.actor.size() == 2 and _area_anchors.observer.size() == 2,
			1.5
		)
	):
		return false
	if not _verify_area_damage(actor, observer, actor_id):
		return false
	return await _verify_physical_force(actor, observer, actor_id, fourth)


func _verify_area_damage(actor: GameConnection, observer: GameConnection, actor_id: String) -> bool:
	var valid := true
	for id in [1, 2]:
		var a: Dictionary = _area_anchors.actor[id]
		var b: Dictionary = _area_anchors.observer[id]
		var before: Dictionary = _area_health_before[id]
		var damage := int(before.health) - int(b.health)
		valid = (
			_check(
				"physical_area_victim_%d_captured_sword_formula" % id,
				(
					damage in PHYSICAL_SWORD_DAMAGE
					and a.health == b.health
					and a.life_sequence == before.life_sequence
					and b.life_sequence == before.life_sequence
				)
			)
			and valid
		)
		valid = (
			_check(
				"physical_area_victim_%d_knockdown_duration" % id,
				int(b.action_ends_at_us) - int(b.action_started_at_us) == 1_166_667
			)
			and valid
		)
		_timing_evidence.append(
			{
				"phase": "physical_area_damage",
				"victim_id": id,
				"life_sequence": before.life_sequence,
				"before": before.health,
				"after": b.health,
				"damage": damage
			}
		)
	return _check(
		"physical_area_preserves_outside_life_and_owner_projection",
		(
			valid
			and _monster_by_id(actor, 3).health == _area_health_before[3].health
			and _monster_by_id(observer, 3).life_sequence == _area_health_before[3].life_sequence
			and actor.selected_combat_target().is_empty()
			and int(actor.progression_for(actor_id).display_attack_min) == 10
			and int(actor.progression_for(actor_id).display_attack_max) == 10
			and observer.progression_for(actor_id).is_empty()
		)
	)


func _verify_physical_force(
	actor: GameConnection, observer: GameConnection, actor_id: String, fourth: Dictionary
) -> bool:
	if not _check(
		"physical_finisher_both_victims_stand_up",
		await _wait_until(
			func():
				return [1, 2].all(
					func(id: int):
						return (
							(
								str(_monster_by_id(actor, id).attack_action_id)
								== FINISHER_FRONT_STANDUP
							)
							and (
								str(_monster_by_id(observer, id).attack_action_id)
								== FINISHER_FRONT_STANDUP
							)
						)
				),
			2.5
		)
	):
		return false
	if not await _wait_action_end(observer, actor_id, int(fourth.action_ends_at_us)):
		return _check("physical_finisher_root_finishes", false)
	var valid := true
	for viewer in ["actor", "observer"]:
		var client: GameConnection = actor if viewer == "actor" else observer
		for id in [1, 2]:
			var start: Dictionary = _area_anchors[viewer][id]
			var after := _monster_by_id(client, id)
			var distance := _position(after).distance_to(_position(start))
			valid = (
				_check(
					"physical_force_%s_%d_endpoint" % [viewer, id], absf(distance - 4.732) < 0.003
				)
				and valid
			)
			valid = (
				_check(
					"physical_force_%s_%d_standup_duration" % [viewer, id],
					int(after.action_ends_at_us) - int(after.action_started_at_us) == 1_000_000
				)
				and valid
			)
			_timing_evidence.append(
				{
					"phase": "physical_force",
					"viewer": viewer,
					"victim_id": id,
					"distance_m": distance
				}
			)
		valid = _check_finisher_root_endpoint(client, actor_id, fourth) and valid
	await create_timer(0.25).timeout
	return _check(
		"physical_finisher_once_per_life_histories", valid and _physical_histories_match()
	)


func _physical_histories_match() -> bool:
	if _health_history.actor != _health_history.observer:
		return false
	for viewer in ["actor", "observer"]:
		for id in [1, 2, 3]:
			var history: Array = _health_history[viewer][id]
			if history.size() != {1: 4, 2: 2, 3: 1}[id]:
				return false
			if not history.all(
				func(row: Dictionary): return row.life_sequence == history[0].life_sequence
			):
				return false
	return true
