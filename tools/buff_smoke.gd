extends "res://tests/progression_admin_smoke.gd"
## Authenticated self-buff action/payment/reconnect qualification on a fresh database.


func _buff_config() -> Dictionary:
	var value: Variant = _config.get("buff", {})
	return value if value is Dictionary else {}


func _buff_vnum() -> int:
	return int(_buff_config().get("vnum", 0))


func _buff_effects() -> Dictionary:
	var value: Variant = _buff_config().get("effects", {})
	return value if value is Dictionary else {}


func _buff_level() -> int:
	return int(_buff_config().get("level", 5))


func _buff_rank() -> int:
	return int(_buff_config().get("rank", 1))


func _buff_skill(client: GameConnection) -> Dictionary:
	var vnum := _buff_vnum()
	for row: Dictionary in client.selected_skills():
		if int(row.skill_vnum) == vnum:
			return row
	return {}


func _prepare_buff_fixture(first: GameConnection) -> bool:
	var vnum := _buff_vnum()
	var level := _buff_level()
	var rank := _buff_rank()
	first.admin_raise_progression_level(_request_id(), str(level))
	var fixture_ok := _check(
		"buff_fixture_selected",
		vnum in [3, 4, 19] and not _buff_effects().is_empty() and rank in range(1, 21)
	)
	var level_ok := _check(
		"buff_level_fixture",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == level)
	)
	if not (fixture_ok and level_ok):
		return false
	var current_rank := int(_buff_skill(first).get("rank", 0))
	if current_rank == 0:
		if not _check(
			"buff_learn", await _raw_success(first, "learn_skill", [vnum, 0], [&"U16", &"U32"])
		):
			return false
		if not _check(
			"buff_rank_learned",
			await _wait_until(func(): return int(_buff_skill(first).get("rank", 0)) >= 1)
		):
			return false
	else:
		_check("buff_rank_learned", current_rank >= 1)
	if rank > 1 and current_rank != rank:
		# The developer command surface accepts one request per second.
		await create_timer(1.05).timeout
		var before_revision := first.skill_revision(vnum)
		if not _check(
			"buff_rank_granted",
			await _raw_success(
				first,
				"admin_set_skill",
				[_request_id(), "%d %d" % [vnum, rank]],
				[&"String", &"String"]
			)
		):
			return false
		if not _check(
			"buff_rank_applied",
			await _wait_until(func(): return _rank_applied(first, vnum, rank, before_revision))
		):
			return false
	_check("buff_rank_subscribed", await _wait_until(func(): return first.skill_revision(vnum) > 0))
	return true


func _rank_applied(client: GameConnection, vnum: int, rank: int, before_revision: int) -> bool:
	return (
		int(_buff_skill(client).get("rank", 0)) == rank
		and client.skill_revision(vnum) > before_revision
	)


func _cast_buff(first: GameConnection, second: GameConnection) -> bool:
	var vnum := _buff_vnum()
	var identity := first.local_identity
	var base := first.selected_progression().duplicate(true)
	var sp := int(first.selected_progression().current_sp)
	var revision := first.skill_revision(vnum)
	if not _check(
		"buff_cast", await _raw_success(first, "cast_skill", [vnum, revision], [&"U16", &"U32"])
	):
		return false
	if not _check(
		"buff_action_on_both_clients",
		await _wait_until(_matching_buff_action.bind(first, second, identity))
	):
		return false
	var cost := int(_buff_config().get("cost", -1))
	if not _check(
		"buff_sp_paid_once",
		await _wait_until(func(): return int(first.selected_progression().current_sp) == sp - cost)
	):
		return false
	if not _check("buff_projection_applied", await _wait_until(_buff_projection.bind(first, base))):
		return false
	if not _check("owner_receives_buff_status", await _wait_until(_has_buff_status.bind(first))):
		return false
	# Let the activation motion finish before ordinary combat or movement resumes.
	await create_timer(1.5).timeout
	return true


func _mean(values: Array) -> float:
	if values.is_empty():
		return 0.0
	var total := 0.0
	for value in values:
		total += float(value)
	return total / float(values.size())


func _all_in_domain(values: Array, domain: Array) -> bool:
	return values.all(func(value): return int(value) in domain)


func _any_outside_domain(values: Array, domain: Array) -> bool:
	return values.any(func(value): return not int(value) in domain)


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	var vnum := _buff_vnum()
	var rank := _buff_rank()
	if not await _prepare_buff_fixture(first):
		return
	var identity := first.local_identity
	var revision := first.skill_revision(vnum)
	var base := first.selected_progression().duplicate(true)
	var sp := int(first.selected_progression().current_sp)
	var cast_ticks := Time.get_ticks_msec()
	_check(
		"peer_unlearned_buff_rejected",
		not await _raw_success(second, "cast_skill", [vnum, 0], [&"U16", &"U32"])
	)
	if not _check(
		"unarmed_buff_cast",
		await _raw_success(first, "cast_skill", [vnum, revision], [&"U16", &"U32"])
	):
		return
	if not _check(
		"buff_action_on_both_clients",
		await _wait_until(_matching_buff_action.bind(first, second, identity))
	):
		return
	var cost := int(_buff_config().get("cost", -1))
	_check(
		"buff_sp_paid_once",
		await _wait_until(func(): return int(first.selected_progression().current_sp) == sp - cost)
	)
	_check("buff_projection_applied", await _wait_until(_buff_projection.bind(first, base)))
	var action := _player_row(second, identity).duplicate(true)
	_check("owner_receives_buff_status", await _wait_until(_has_buff_status.bind(first)))
	_check("peer_cannot_read_owner_buff_status", second.buffs.is_empty())
	if not first.buffs.is_empty():
		var status: Dictionary = first.buffs[0]
		_check(
			"buff_status_has_no_private_modifiers",
			not status.has("modifiers") and not status.has("next_tick_us")
		)
		_check(
			"buff_status_binds_owner_life",
			(
				str(status.character_id) == identity
				and int(status.life_sequence) == int(action.life_sequence)
			)
		)
	var ready := int(_buff_skill(first).ready_at_us)
	var cooldown_us := int(_buff_config().get("cooldown_us", -1))
	_check("buff_source_cooldown", ready - int(action.action_started_at_us) == cooldown_us)
	_check(
		"buff_action_has_duration", int(action.action_ends_at_us) > int(action.action_started_at_us)
	)
	_check(
		"stale_buff_cast_rejected",
		not await _raw_success(first, "cast_skill", [vnum, revision], [&"U16", &"U32"])
	)
	_check(
		"cooling_buff_cast_rejected",
		not await _raw_success(
			first, "cast_skill", [vnum, first.skill_revision(vnum)], [&"U16", &"U32"]
		)
	)
	_check(
		"rejected_casts_preserve_payment", int(first.selected_progression().current_sp) == sp - cost
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
	_check("buff_projection_restored", await _wait_until(_buff_projection.bind(first, base)))
	_check("buff_cooldown_persisted", int(_buff_skill(first).ready_at_us) == ready)
	_check("buff_rank_persisted", int(_buff_skill(first).rank) == rank)
	_check("reconnect_restores_owner_status", await _wait_until(_has_buff_status.bind(first)))
	_check("reconnect_does_not_leak_status", second.buffs.is_empty())
	var duration_ticks := int(_buff_config().get("duration_ticks", 0))
	if _check(
		"buff_expires_owner_status",
		await _wait_until(_no_buff_status.bind(first), float(duration_ticks) + 10.0)
	):
		var elapsed := Time.get_ticks_msec() - cast_ticks
		var owner := _player_row(first, identity)
		print(
			"BUFF_END state=",
			first.state,
			" vnum=",
			vnum,
			" name=",
			_buff_config().get("name", ""),
			" health=",
			owner.get("health", -1),
			" life=",
			owner.get("life_sequence", -1),
			" original_life=",
			action.life_sequence,
			" online=",
			owner.get("online", false)
		)
		_check(
			"expiry_requires_living_connected_owner",
			(
				first.state == "connected"
				and int(owner.get("health", 0)) > 0
				and bool(owner.get("online", false))
				and int(owner.get("life_sequence", -1)) == int(action.life_sequence)
			)
		)
		var duration_ms := duration_ticks * 1000
		_check(
			"offline_pause_extends_wall_duration",
			elapsed >= duration_ms + 1000 and elapsed <= duration_ms + 10000
		)
		_check(
			"buff_expires_to_base_projection",
			await _wait_until(_base_projection.bind(first, base), 2.0)
		)
		_check("expiry_preserves_cooldown", int(_buff_skill(first).ready_at_us) == ready)
		_check(
			"expiry_does_not_replay_cast",
			int(_player_row(second, identity).attack_sequence) == int(action.attack_sequence)
		)
		_check("expiry_preserves_rank", int(_buff_skill(first).rank) == 1)
		print("BUFF_EXPIRY elapsed_ms=", elapsed)


func _has_buff_status(client: GameConnection) -> bool:
	return client.buffs.size() == 1 and int(client.buffs[0].skill_vnum) == _buff_vnum()


func _no_buff_status(client: GameConnection) -> bool:
	return client.buffs.is_empty()


func _buff_projection(client: GameConnection, base: Dictionary) -> bool:
	var progression := client.selected_progression()
	var effects := _buff_effects()
	return (
		(
			int(progression.get("display_attack_speed", 0))
			== int(base.get("display_attack_speed", 0)) + int(effects.get("attack_speed", 0))
		)
		and (
			int(progression.get("display_defense", 0))
			== int(base.get("display_defense", 0)) + int(effects.get("defense_grade", 0))
		)
	)


func _base_projection(client: GameConnection, base: Dictionary) -> bool:
	var progression := client.selected_progression()
	return (
		int(progression.get("display_attack_speed", 0)) == int(base.get("display_attack_speed", 0))
		and int(progression.get("display_defense", 0)) == int(base.get("display_defense", 0))
	)


func _matching_buff_action(first: GameConnection, second: GameConnection, identity: String) -> bool:
	var action := str(_player_row(first, identity).get("attack_action_id", ""))
	return (
		action.ends_with(str(_buff_config().get("action_suffix", "")))
		and action == str(_player_row(second, identity).get("attack_action_id", ""))
	)
