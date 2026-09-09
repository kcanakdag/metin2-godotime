extends "res://tests/progression_admin_smoke.gd"
## Two-client acceptance of persisted charge activation, movement and invalidation.


func _charge(client: GameConnection, identity: String) -> Dictionary:
	for row: Dictionary in client.charges:
		if str(row.character_id) == identity:
			return row
	return {}


func _skill(client: GameConnection) -> Dictionary:
	for row: Dictionary in client.selected_skills():
		if int(row.skill_vnum) == 5:
			return row
	return {}


func _matching_charge(first: GameConnection, second: GameConnection, identity: String) -> bool:
	return (
		not _charge(first, identity).is_empty()
		and _charge(first, identity) == _charge(second, identity)
	)


func _prepare_charge(first: GameConnection) -> bool:
	first.admin_raise_progression_level(_request_id(), "5")
	if not _check(
		"charge_level_five",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 5)
	):
		return false
	if not _check(
		"charge_learn", await _raw_success(first, "learn_skill", [5, 0], [&"U16", &"U32"])
	):
		return false
	_check("charge_rank_subscribes", await _wait_until(func(): return first.skill_revision(5) > 0))
	var swords := first.inventory.filter(func(item): return int(item.vnum) == 10)
	if not _check("charge_sword_available", swords.size() == 1):
		return false
	first.equip_item(int(swords[0].id))
	if not _check(
		"charge_sword_equipped",
		await _wait_until(func(): return _has_equipped_item(first, int(swords[0].id)))
	):
		return false
	return true


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_charge(first):
		return
	var identity := first.local_identity
	var sp := int(first.selected_progression().current_sp)
	var revision := first.skill_revision(5)
	_check(
		"unlearned_peer_cannot_charge",
		not await _raw_success(second, "cast_skill", [5, revision], [&"U16", &"U32"])
	)
	if not _check(
		"charge_activates", await _raw_success(first, "cast_skill", [5, revision], [&"U16", &"U32"])
	):
		return
	if not _check(
		"charge_projects_to_both", await _wait_until(_matching_charge.bind(first, second, identity))
	):
		return
	var status := _charge(first, identity).duplicate(true)
	_check(
		"charge_public_projection_minimal",
		not status.has("connection_id") and not status.has("rank") and not status.has("source_life")
	)
	_check(
		"charge_original_duration_speed",
		(
			int(status.expires_at_us) - int(status.starts_at_us) == 3000000
			and int(status.speed_bonus) == 150
		)
	)
	_check(
		"charge_pays_once",
		await _wait_until(func(): return int(first.selected_progression().current_sp) == sp - 66)
	)
	var ready := int(_skill(first).ready_at_us)
	_check("charge_original_cooldown", ready - int(status.starts_at_us) == 12000000)
	_check(
		"charge_replay_rejects",
		not await _raw_success(first, "cast_skill", [5, revision], [&"U16", &"U32"])
	)
	_check(
		"charge_refresh_rejects",
		not await _raw_success(first, "cast_skill", [5, first.skill_revision(5)], [&"U16", &"U32"])
	)
	_check("charge_rejections_preserve_sp", int(first.selected_progression().current_sp) == sp - 66)
	var start := _xz(_player_row(second, identity))
	first.set_move_input(-1.0, 0.0)
	await create_timer(0.3).timeout
	first.stop_moving()
	await create_timer(0.1).timeout
	var distance := start.distance_to(_xz(_player_row(second, identity)))
	_check("charge_boost_moves_remote_actor", distance > 1.8 and distance < 4.5)
	_check(
		"charge_expiry_removes_both_projections",
		await _wait_until(
			func():
				return _charge(first, identity).is_empty() and _charge(second, identity).is_empty(),
			5.0
		)
	)
	_check(
		"charge_expiry_preserves_cost_cooldown",
		(
			int(first.selected_progression().current_sp) == sp - 66
			and int(_skill(first).ready_at_us) == ready
		)
	)
	_check("charge_expiry_advances_revision", first.skill_revision(5) > revision + 1)
	_check(
		"charge_still_cooling",
		not await _raw_success(first, "cast_skill", [5, first.skill_revision(5)], [&"U16", &"U32"])
	)
	await create_timer(9.5).timeout
	if not _check(
		"charge_can_activate_after_cooldown",
		await _raw_success(first, "cast_skill", [5, first.skill_revision(5)], [&"U16", &"U32"])
	):
		return
	_check(
		"second_charge_projects",
		await _wait_until(func(): return not _charge(second, identity).is_empty())
	)
	var paid_sp := int(first.selected_progression().current_sp)
	var cooldown := int(_skill(first).ready_at_us)
	first.disconnect_game()
	_check(
		"disconnect_removes_charge",
		await _wait_until(func(): return _charge(second, identity).is_empty())
	)
	first.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[0]), "charge-reconnect"
	)
	if not _check(
		"charge_reconnect_lobby", await _wait_until(func(): return first.state == "lobby", 20.0)
	):
		return
	first.enter_selected()
	_check(
		"charge_reconnect_world", await _wait_until(func(): return first.state == "connected", 20.0)
	)
	_check(
		"reconnect_does_not_restore_charge",
		_charge(first, identity).is_empty() and _charge(second, identity).is_empty()
	)
	_check(
		"reconnect_preserves_charge_payment",
		(
			int(first.selected_progression().current_sp) == paid_sp
			and int(_skill(first).ready_at_us) == cooldown
		)
	)
