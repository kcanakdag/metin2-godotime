extends "res://tests/crush_smoke.gd"
## A GREAT reaction during stun must not restart after affect expiry clears motion.


func _prepare_charge(first: GameConnection) -> bool:
	if not await super._prepare_charge(first):
		return false
	await create_timer(1.1).timeout
	first.admin_set_skill(_request_id(), "16 1")
	return _check("overlap_reaction_skill", await _wait_until(_learned.bind(first)))


func _learned(first: GameConnection) -> bool:
	return first.skill_revision(16) > 0


func _reacting(client: GameConnection) -> bool:
	var bear := _dog(client, 1)
	var action := str(bear.get("attack_action_id", ""))
	return (
		int(bear.get("activity", 0)) == 2
		and (action.contains("knockdown") or action.contains("standup"))
	)


func _both_reacting(first: GameConnection, second: GameConnection) -> bool:
	return _reacting(first) and _reacting(second)


func _observe(first: GameConnection, second: GameConnection, _before: Dictionary) -> void:
	var status := _stun(second).duplicate(true)
	await create_timer(1.35).timeout
	for offset in [-2.7, -2.0]:
		var destination := _xz(_dog(second, 1)) + Vector2(offset, 0.0)
		first.move_to(destination.x, destination.y)
		if not _check(
			"overlap_approach_%s" % offset,
			await _wait_until(_arrived.bind(first, second, destination), 2.0)
		):
			return
	first.stop_moving()
	if not _check(
		"overlap_cast",
		await _raw_success(first, "cast_skill", [16, first.skill_revision(16)], [&"U16", &"U32"])
	):
		return
	if not _check(
		"overlap_reaction_both", await _wait_until(_both_reacting.bind(first, second), 2.0)
	):
		return
	var bear := _dog(second, 1).duplicate(true)
	var sequence := int(bear.attack_sequence)
	var chain_end := int(bear.action_ends_at_us)
	if str(bear.attack_action_id).ends_with("front_knockdown"):
		chain_end += 1333333  # Original Brown Bear front-standup duration.
	_check("overlap_stun_still_active", _stun_shared(first, second))
	_check("overlap_reaction_crosses_expiry", chain_end > int(status.expires_at_us))
	_check("overlap_target_survives", int(bear.health) > 0)
	_check("overlap_expiry_both", await _wait_until(_stun_gone.bind(first, second), 3.0))
	_check("overlap_expiry_stops_motion", not _reacting(first) and not _reacting(second))
	var restarted := false
	for _frame in 30:
		await create_timer(0.1).timeout
		restarted = restarted or _reacting(first) or _reacting(second)
	_check("overlap_no_reaction_restart", not restarted)
	_check(
		"overlap_ai_recovers", await _wait_until(_resumed.bind(second, _xz(bear), sequence), 5.0)
	)
