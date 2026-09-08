extends "res://tests/actor_smoke.gd"
## Candidate wildlife through the real PvE node with controlled subscribed-state fixtures.


func _run() -> void:
	create_timer(45.0).timeout.connect(func(): quit(1))
	root.size = Vector2i(1280, 800)
	_check(_catalog.load_required(), "installed wildlife catalog loads through normal loader")
	_check(_effect_catalog.load_required(), "target effects load")
	if _failed:
		_finish()
		return
	_test_catalog_gate()
	_build_stage()
	var document: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://mob-gameplay.json")
	)
	for definition: Dictionary in document.mobs:
		await _test_species(definition)
	await _capture_named("wildlife-overview")
	_finish()


func _test_catalog_gate() -> void:
	var info := {
		"definition_profile": ActorCatalog.PROFILE_ID,
		"definition_hash": _catalog.gameplay_definition_hash(),
		"skill_catalog_hash": _catalog.skills.content_hash,
		"character_catalog_hash": _catalog.characters.content_hash,
		"training_target_hash": _catalog.training_target_hash,
		"mob_catalog_hash": _catalog.mob_gameplay_hash,
	}
	_check(not _catalog.mob_gameplay_hash.is_empty(), "installed mob gameplay hash is retained")
	_check(_catalog.validate_world(info), "matching mob hash accepted")
	_catalog.report_errors = false
	info.erase("mob_catalog_hash")
	_check(not _catalog.validate_world(info), "missing server mob hash rejects installed catalog")
	info.mob_catalog_hash = "0".repeat(64)
	_check(not _catalog.validate_world(info), "wrong server mob hash rejects installed catalog")
	info.mob_catalog_hash = _catalog.mob_gameplay_hash
	_check(_catalog.validate_world(info), "matching hash restores compatibility")
	_catalog.report_errors = true
	var document: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(ActorCatalog.MOB_PATH)
	)
	var probe := ActorCatalog.new()
	probe.report_errors = false
	document.actors[0].id = ActorCatalog.WARRIOR_ID
	_check(probe._mob_ids(document).is_empty(), "mob overlay cannot replace a player actor")


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
		for launch: Dictionary in attack.get("projectile_launches", []):
			_test_launch(mob, row, launch)
		mob.apply_state(row, int(row.action_ends_at_us) + 50_000)
		_check(mob.presentation_snapshot().frozen_pose, "completed action holds final pose")
		row.activity = 0
		mob.apply_state(row, int(row.action_ends_at_us) + 100_000)
		_check(
			is_equal_approx(float(mob.presentation_snapshot().animation_speed), 1.0),
			"idle resets playback rate"
		)
		_check(not mob.presentation_snapshot().frozen_pose, "idle releases held pose")
	var reactions: Array = definition.reactions.values()
	for action in ["front_damage", "back_damage"]:
		for motion: Dictionary in _catalog.motions(str(definition.id), "general", action):
			reactions.append(
				{
					"id": motion.action_id,
					"duration_us": motion.duration_us,
					"godot_name": motion.godot_name
				}
			)
	for reaction: Dictionary in reactions:
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


func _test_launch(mob: Node3D, row: Dictionary, launch: Dictionary) -> void:
	var emitted: Array[Dictionary] = []
	var listener := func(actor: Node3D, definition: Dictionary, origin: Vector3):
		emitted.append({"actor": actor, "definition": definition, "origin": origin})
	mob.projectile_launched.connect(listener)
	var presentation: Node3D = mob.get_node("ActorVisual/Presentation")
	row.attack_sequence += 1
	mob.apply_state(row, int(row.action_started_at_us))
	var player: AnimationPlayer = presentation.animation_player
	player.seek(float(int(launch.start_us) - 1) / 1e6, true)
	presentation._process(0)
	_check(emitted.is_empty(), "projectile does not launch before source deadline")
	player.seek(float(launch.start_us) / 1e6, true)
	presentation._process(0)
	_check(emitted.size() == 1, "projectile launches exactly at source deadline")
	if emitted.size() == 1:
		_check(emitted[0].actor == mob, "PvE launch identifies the subscribed actor")
		_check(
			emitted[0].definition.fly_definition == launch.fly_definition,
			"exact source flight reference"
		)
		_check(emitted[0].origin.is_finite(), "converted attachment bone resolves")
		_check(emitted[0].origin.distance_to(mob.global_position) > 0.01, "launch uses bone offset")
		var origin: Vector3 = emitted[0].origin
		mob.rotation.y = 1.7
		var rotated: Dictionary = presentation.projectile_launch_origin(launch)
		_check(
			rotated.position.distance_to(origin) < 0.0001,
			"source launch offset ignores actor heading"
		)
		mob.rotation.y = 0
		var shifted := launch.duplicate(true)
		shifted.source_position_cm = [10, 20, 30]
		var shifted_origin: Dictionary = presentation.projectile_launch_origin(shifted)
		_check(
			shifted_origin.position.distance_to(origin + Vector3(0.1, 0.3, -0.2)) < 0.0001,
			"source offset has correct units and axes"
		)
	presentation._process(0)
	_check(emitted.size() == 1, "repeated update cannot duplicate projectile")
	presentation.play_mob_action(
		"general",
		row.attack_action_id,
		row.attack_sequence,
		row.action_started_at_us,
		row.action_ends_at_us,
		row.action_started_at_us,
		true
	)
	player.seek(float(launch.start_us) / 1e6, true)
	presentation._process(0)
	_check(emitted.size() == 1, "resync and rewind cannot duplicate projectile")
	row.attack_sequence += 1
	mob.apply_state(row, int(row.action_started_at_us))
	player.seek(float(launch.start_us) / 1e6, true)
	presentation._process(0)
	_check(emitted.size() == 2, "new attack sequence can launch")
	row.attack_sequence += 1
	mob.apply_state(row, int(row.action_ends_at_us) - 1)
	presentation._process(0)
	_check(emitted.size() == 2, "late subscription skips historical launch")
	row.attack_sequence += 1
	mob.apply_state(row, int(row.action_started_at_us))
	player.advance(float(presentation.current_motion.duration_us) / 1e6 + 1)
	_check(emitted.size() == 3, "long frame crossing animation end still launches once")
	presentation._process(0)
	_check(emitted.size() == 3, "finished animation cannot repeat its launch")
	mob.projectile_launched.disconnect(listener)
