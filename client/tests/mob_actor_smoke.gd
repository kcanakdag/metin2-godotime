extends "res://tests/actor_smoke.gd"
## Candidate wildlife through the real PvE node with controlled subscribed-state fixtures.


func _run() -> void:
	create_timer(45.0).timeout.connect(func(): quit(1))
	root.size = Vector2i(1280, 800)
	_check(_catalog.load_required(), "merged wildlife fixture catalog loads")
	_check(_effect_catalog.load_required(), "target effects load")
	if _failed:
		_finish()
		return
	_build_stage()
	var document: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://mob-gameplay.json")
	)
	for definition: Dictionary in document.mobs:
		await _test_species(definition)
	await _capture_named("wildlife-overview")
	_finish()


func _test_species(definition: Dictionary) -> void:
	var mob := PveActor.new()
	mob.configure(_catalog, _effect_catalog)
	_stage.add_child(mob)
	var row := {
		"id": int(definition.vnum),
		"definition_vnum": int(definition.vnum),
		"actor_id": str(definition.id),
		"name": str(definition.name),
		"health": int(definition.health),
		"max_health": int(definition.health),
		"x": 0.0,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"level": int(definition.level),
		"activity": 0,
		"attack_sequence": 0,
		"life_sequence": 0,
		"attack_action_id": "",
		"action_started_at_us": 0,
		"action_ends_at_us": 0,
	}
	mob.apply_state(row, 1_000_000)
	await process_frame
	_check(mob.is_pickable(), "%s can be targeted" % definition.name)
	_check(mob.presentation_snapshot().error.is_empty(), "%s model loads" % definition.name)
	for attack: Dictionary in definition.attacks:
		row.activity = 2
		row.attack_sequence += 1
		row.attack_action_id = str(attack.id)
		row.action_started_at_us = 10_000_000
		row.action_ends_at_us = 10_000_000 + int(attack.playback_duration_us)
		var elapsed := int(attack.playback_duration_us) / 2
		mob.apply_state(row, 10_000_000 + elapsed)
		var snapshot := mob.presentation_snapshot()
		var rate := float(attack.duration_us) / float(attack.playback_duration_us)
		_check(snapshot.action_id == attack.id, "exact authoritative attack ID")
		_check(snapshot.clip == attack.godot_name, "exact converted attack variant")
		_check(
			absf(float(snapshot.animation_speed) - rate) < 0.00001, "authoritative playback rate"
		)
		_check(
			absf(float(snapshot.animation_position) - float(elapsed) / 1e6 * rate) < 0.005,
			"late subscription seeks at scaled rate"
		)
		mob.apply_state(row, int(row.action_ends_at_us) + 50_000)
		_check(mob.presentation_snapshot().frozen_pose, "completed action holds final pose")
		row.activity = 0
		mob.apply_state(row, int(row.action_ends_at_us) + 100_000)
		_check(
			is_equal_approx(float(mob.presentation_snapshot().animation_speed), 1.0),
			"idle resets playback rate"
		)
		_check(not mob.presentation_snapshot().frozen_pose, "idle releases held pose")
	for reaction: Dictionary in definition.reactions.values():
		row.activity = 2
		row.attack_sequence += 1
		row.attack_action_id = str(reaction.id)
		row.action_started_at_us = 20_000_000
		row.action_ends_at_us = 20_000_000 + int(reaction.duration_us)
		mob.apply_state(row, 20_000_000 + int(reaction.duration_us) / 2)
		_check(
			mob.presentation_snapshot().clip == reaction.godot_name,
			"species-specific recovery clip"
		)
		_check(
			is_equal_approx(float(mob.presentation_snapshot().animation_speed), 1.0),
			"recovery uses unscaled source duration"
		)
	row.activity = 0
	mob.apply_state(row, 30_000_000)
	mob.set_targeted(true)
	await _capture_from("wildlife-%s" % definition.vnum, Vector3(3, 2, -4), Vector3.ZERO)
	row.activity = 3
	row.health = 0
	row.action_started_at_us = 30_000_000
	row.action_ends_at_us = 40_000_000
	mob.apply_state(row, 39_000_000)
	_check(not mob.is_pickable(), "dead wildlife cannot be targeted")
	_check(mob.presentation_snapshot().frozen_pose, "late death holds final pose")
	row.activity = 0
	row.health = int(definition.health)
	row.life_sequence = 1
	mob.apply_state(row, 40_000_000)
	_check(mob.is_pickable(), "respawn restores targeting")
	_check(not mob.presentation_snapshot().frozen_pose, "new life releases death pose")
	mob.queue_free()
	await process_frame
