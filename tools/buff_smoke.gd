extends "res://tests/progression_admin_smoke.gd"
## Authenticated self-buff action/payment/reconnect qualification on a fresh database.


func _buff_skill(client: GameConnection) -> Dictionary:
	for row: Dictionary in client.selected_skills():
		if int(row.skill_vnum) == 3:
			return row
	return {}


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	first.admin_raise_progression_level(_request_id(), "5")
	if not _check(
		"buff_level_five",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 5)
	):
		return
	if int(_buff_skill(first).get("rank", 0)) == 0:
		if not _check(
			"buff_learn", await _raw_success(first, "learn_skill", [3, 0], [&"U16", &"U32"])
		):
			return
	if not _check(
		"buff_rank_one_fixture",
		await _wait_until(func(): return int(_buff_skill(first).get("rank", 0)) == 1)
	):
		return
	_check("buff_rank_subscribed", await _wait_until(func(): return first.skill_revision(3) > 0))
	var identity := first.local_identity
	var revision := first.skill_revision(3)
	var sp := int(first.selected_progression().current_sp)
	var cast_ticks := Time.get_ticks_msec()
	_check(
		"peer_unlearned_buff_rejected",
		not await _raw_success(second, "cast_skill", [3, 0], [&"U16", &"U32"])
	)
	if not _check(
		"unarmed_buff_cast",
		await _raw_success(first, "cast_skill", [3, revision], [&"U16", &"U32"])
	):
		return
	if not _check(
		"buff_action_on_both_clients",
		await _wait_until(_matching_buff_action.bind(first, second, identity))
	):
		return
	_check(
		"buff_sp_paid_once",
		await _wait_until(func(): return int(first.selected_progression().current_sp) == sp - 57)
	)
	_check(
		"buff_speed_projects",
		await _wait_until(
			func(): return int(first.selected_progression().display_attack_speed) == 102
		)
	)
	var action := _player_row(second, identity).duplicate(true)
	var ready := int(_buff_skill(first).ready_at_us)
	_check("buff_source_cooldown", ready - int(action.action_started_at_us) == 67000000)
	_check(
		"buff_action_has_duration", int(action.action_ends_at_us) > int(action.action_started_at_us)
	)
	_check(
		"stale_buff_cast_rejected",
		not await _raw_success(first, "cast_skill", [3, revision], [&"U16", &"U32"])
	)
	_check(
		"cooling_buff_cast_rejected",
		not await _raw_success(first, "cast_skill", [3, first.skill_revision(3)], [&"U16", &"U32"])
	)
	_check(
		"rejected_casts_preserve_payment", int(first.selected_progression().current_sp) == sp - 57
	)
	first.disconnect_game()
	_check(
		"buff_owner_presence_removed",
		await _wait_until(
			func(): return not bool(_player_row(second, identity).get("online", false))
		)
	)
	await create_timer(2.0).timeout
	first.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[0]), "buff-reconnect"
	)
	if not _check(
		"buff_reconnect_lobby", await _wait_until(func(): return first.state == "lobby", 20.0)
	):
		return
	first.enter_selected()
	_check(
		"buff_reconnect_world", await _wait_until(func(): return first.state == "connected", 20.0)
	)
	_check(
		"buff_speed_restored",
		await _wait_until(
			func(): return int(first.selected_progression().get("display_attack_speed", 0)) == 102
		)
	)
	_check("buff_cooldown_persisted", int(_buff_skill(first).ready_at_us) == ready)
	_check("buff_rank_persisted", int(_buff_skill(first).rank) == 1)
	if _check("buff_expires_to_base_speed", await _wait_until(_base_speed.bind(first), 70.0)):
		var elapsed := Time.get_ticks_msec() - cast_ticks
		_check("offline_pause_extends_wall_duration", elapsed >= 65000 and elapsed <= 72000)
		_check("expiry_preserves_cooldown", int(_buff_skill(first).ready_at_us) == ready)
		_check(
			"expiry_does_not_replay_cast",
			int(_player_row(second, identity).attack_sequence) == int(action.attack_sequence)
		)
		_check("expiry_preserves_rank", int(_buff_skill(first).rank) == 1)
		print("BUFF_EXPIRY elapsed_ms=", elapsed)


func _base_speed(client: GameConnection) -> bool:
	return int(client.selected_progression().get("display_attack_speed", 0)) == 100


func _matching_buff_action(first: GameConnection, second: GameConnection, identity: String) -> bool:
	var action := str(_player_row(first, identity).get("attack_action_id", ""))
	return (
		action.ends_with(".skill_3")
		and action == str(_player_row(second, identity).get("attack_action_id", ""))
	)
