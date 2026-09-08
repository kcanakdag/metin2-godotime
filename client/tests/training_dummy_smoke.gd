extends "res://tests/actor_smoke.gd"
## Real authored model through the ordinary PvE presentation and targeting path.


func _run() -> void:
	create_timer(20.0).timeout.connect(func(): quit(1))
	root.size = Vector2i(1280, 800)
	_check(_catalog.load_required(), "authored dummy catalog loads")
	_check(_effect_catalog.load_required(), "target effects load")
	if _failed:
		_finish()
		return
	_build_stage()
	var dummy := PveActor.new()
	dummy.configure(_catalog, _effect_catalog)
	_stage.add_child(dummy)
	var row := {
		"id": 900001,
		"definition_vnum": 900001,
		"actor_id": "actor.training.straw-dummy",
		"name": "Training Dummy",
		"health": 30000,
		"max_health": 30000,
		"x": 0.0,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"level": 1,
		"activity": 0,
		"attack_sequence": 0,
		"life_sequence": 0,
		"attack_action_id": "",
		"action_started_at_us": 0,
		"action_ends_at_us": 0,
	}
	dummy.apply_state(row, 1_000_000)
	await process_frame
	_check(dummy.presentation_snapshot().clip == "wait", "dummy plays authored idle")
	_check(dummy.is_pickable(), "dummy can be targeted")
	var bounds := _catalog.actor_bounds("actor.training.straw-dummy")
	_check(not bounds.is_empty(), "dummy supplies actual model pick bounds")
	if not bounds.is_empty():
		_check(bounds.maximum.y > 1.8 and bounds.maximum.y < 2.0, "dummy is human scale")
	dummy.set_targeted(true)
	_check(dummy.presentation_snapshot().targeted, "ordinary accepted-target state works")
	await _capture_from("training-dummy", Vector3(3.0, 2.0, -4.0), Vector3(0, 0.25, 0))
	row.health = 29000
	dummy.apply_state(row, 1_100_000)
	_check(dummy.presentation_snapshot().clip == "damage", "damage uses authored impact clip")
	await create_timer(0.15).timeout
	await _capture_named("training-dummy-hit")
	row.health = 0
	row.activity = 3
	row.action_started_at_us = 2_000_000
	row.action_ends_at_us = 4_000_000
	dummy.apply_state(row, 3_500_000)
	_check(not dummy.is_pickable(), "defeated dummy cannot be targeted")
	_check(dummy.presentation_snapshot().clip == "dead", "death uses authored broken pose")
	_check(dummy.presentation_snapshot().frozen_pose, "late death subscription holds final pose")
	row.health = 30000
	row.activity = 0
	row.life_sequence = 1
	dummy.apply_state(row, 4_100_000)
	_check(dummy.is_pickable(), "new dummy life restores targeting")
	_check(dummy.combat_target_intent().target_life_sequence == 1, "target intent uses new life")
	_check(dummy.presentation_snapshot().clip == "wait", "respawn restores idle")
	_check(not dummy.presentation_snapshot().frozen_pose, "respawn releases death pose")
	dummy.set_stream_visible(false)
	_check(not dummy.is_pickable(), "unstreamed dummy cannot receive targeting input")
	_finish()
