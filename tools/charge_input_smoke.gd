extends "res://tests/charge_strike_smoke.gd"
## Real ChargeSkillInput drives two-client automatic approach and completion.
var _intents: Array[String] = []


func _completed(name: String, succeeded: bool, _timestamp: int) -> void:
	if name in ["begin_charge", "cast_skill"]:
		_intents.append(name + (":ok" if succeeded else ":rejected"))


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_charge(first):
		return
	if not _check(
		"input_dummy_subscribed", await _wait_until(_dummy_subscribed.bind(first, second))
	):
		return
	if not _check("input_far_approach", await _approach(first, second, -4.0)):
		return
	var before := _dog(second, 900001).duplicate(true)
	if not _check(
		"input_target",
		await _raw_success(
			first, "select_combat_target", [900001, before.life_sequence], [&"U32", &"U32"]
		)
	):
		return
	var driver := ChargeSkillInput.new()
	root.add_child(driver)
	driver.configure(first)
	first.reducer_completed.connect(_completed)
	var sp := int(first.selected_progression().current_sp)
	var start := _xz(_player_row(second, first.local_identity))
	_check("input_handled", driver.request(5))
	for _press in 5:
		_check("input_repeat_handled", driver.request(5))
	if not _check(
		"input_auto_damage_both",
		await _wait_until(_damage_both.bind(first, second, int(before.health)), 6.0)
	):
		driver.queue_free()
		return
	_check(
		"input_remote_actor_approached",
		_xz(_player_row(second, first.local_identity)).distance_to(start) > 2.0
	)
	_check("input_single_payment", int(first.selected_progression().current_sp) == sp - 66)
	_check("input_charge_consumed", await _wait_until(_consumed_both.bind(first, second)))
	await create_timer(0.2).timeout
	_check("input_exactly_one_begin_and_finish", _intents == ["begin_charge:ok", "cast_skill:ok"])
	var health := int(_dog(second, 900001).health)
	await create_timer(1.0).timeout
	_check("input_no_late_duplicate_damage", int(_dog(second, 900001).health) == health)
	await create_timer(12.0).timeout
	await _cancel_approach(first, second, driver)
	driver.queue_free()


func _cancel_approach(
	first: GameConnection, second: GameConnection, driver: ChargeSkillInput
) -> void:
	if not _check("input_cancel_far_position", await _approach(first, second, -8.0)):
		return
	var health := int(_dog(second, 900001).health)
	var count := _intents.size()
	_check("input_cancel_begin_handled", driver.request(5))
	if not _check(
		"input_cancel_charge_shared",
		await _wait_until(_matching_charge.bind(first, second, first.local_identity))
	):
		return
	driver.cancel(true)
	await create_timer(1.0).timeout
	_check("input_cancel_no_strike", _intents.slice(count) == ["begin_charge:ok"])
	_check("input_cancel_no_damage", int(_dog(second, 900001).health) == health)
	_check("input_cancel_reservation_cleared", driver._approach.phase == "idle")
