extends "res://tests/charge_smoke.gd"
## Immediate and previously activated charge strikes through real subscriptions.


func _dummy_subscribed(first: GameConnection, second: GameConnection) -> bool:
	return not _dog(first, 900001).is_empty() and not _dog(second, 900001).is_empty()


func _approach(first: GameConnection, second: GameConnection, offset: float) -> bool:
	var destination := _xz(_dog(second, 900001)) + Vector2(offset, 0.0)
	first.move_to(destination.x, destination.y)
	var arrived := await _wait_until(
		func():
			return _xz(_player_row(second, first.local_identity)).distance_to(destination) < 0.1,
		15.0
	)
	first.stop_moving()
	return arrived


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_charge(first):
		return
	if not _check(
		"strike_dummy_subscribed", await _wait_until(_dummy_subscribed.bind(first, second))
	):
		return
	if not _check("strike_outside_range", await _approach(first, second, -2.5)):
		return
	var life := int(_dog(second, 900001).life_sequence)
	if not _check(
		"strike_select_exact_life",
		await _raw_success(first, "select_combat_target", [900001, life], [&"U32", &"U32"])
	):
		return
	var sp := int(first.selected_progression().current_sp)
	var revision := first.skill_revision(5)
	var health := int(_dog(second, 900001).health)
	_check(
		"strike_far_rejected",
		not await _raw_success(first, "cast_skill", [5, revision], [&"U16", &"U32"])
	)
	_check(
		"strike_far_preserves_state",
		(
			first.skill_revision(5) == revision
			and int(first.selected_progression().current_sp) == sp
			and int(_dog(second, 900001).health) == health
			and _charge(first, first.local_identity).is_empty()
		)
	)
	if not _check("strike_immediate_approach", await _approach(first, second, -1.0)):
		return
	await _strike_once(first, second, "immediate", sp - 66, 0)
	await create_timer(12.2).timeout
	await _charged_strike(first, second, life)


func _charged_strike(first: GameConnection, second: GameConnection, life: int) -> void:
	if not _check("strike_clear_target", await _raw_success(first, "clear_combat_target", [], [])):
		return
	if not _check(
		"strike_charge_activates",
		await _raw_success(first, "cast_skill", [5, first.skill_revision(5)], [&"U16", &"U32"])
	):
		return
	if not _check(
		"strike_charge_projects",
		await _wait_until(_matching_charge.bind(first, second, first.local_identity))
	):
		return
	var paid_sp := int(first.selected_progression().current_sp)
	var ready := int(_skill(first).ready_at_us)
	if not _check(
		"strike_charge_reselect",
		await _raw_success(first, "select_combat_target", [900001, life], [&"U32", &"U32"])
	):
		return
	await _strike_once(first, second, "charged", paid_sp, ready)


func _strike_once(
	first: GameConnection, second: GameConnection, label: String, paid_sp: int, ready: int
) -> void:
	var health := int(_dog(second, 900001).health)
	var revision := first.skill_revision(5)
	if not _check(
		label + "_accepted",
		await _raw_success(first, "cast_skill", [5, revision], [&"U16", &"U32"])
	):
		return
	_check(label + "_damage_both", await _wait_until(_damage_both.bind(first, second, health)))
	_check(label + "_consumed_both", await _wait_until(_consumed_both.bind(first, second)))
	_check(label + "_single_payment", int(first.selected_progression().current_sp) == paid_sp)
	_check(label + "_revision_advanced", first.skill_revision(5) > revision)
	if ready > 0:
		_check(label + "_cooldown_preserved", int(_skill(first).ready_at_us) == ready)
	var damaged := int(_dog(second, 900001).health)
	_check(
		label + "_stale_replay_rejected",
		not await _raw_success(first, "cast_skill", [5, revision], [&"U16", &"U32"])
	)
	_check(
		label + "_fresh_replay_rejected",
		not await _raw_success(first, "cast_skill", [5, first.skill_revision(5)], [&"U16", &"U32"])
	)
	await create_timer(1.5).timeout
	_check(
		label + "_no_delayed_or_replay_damage",
		int(_dog(second, 900001).health) == damaged and int(_dog(first, 900001).health) == damaged
	)


func _damage_both(first: GameConnection, second: GameConnection, health: int) -> bool:
	return (
		int(_dog(second, 900001).health) < health
		and _dog(first, 900001).health == _dog(second, 900001).health
	)


func _consumed_both(first: GameConnection, second: GameConnection) -> bool:
	return (
		_charge(first, first.local_identity).is_empty()
		and _charge(second, first.local_identity).is_empty()
	)
