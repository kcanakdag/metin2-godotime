extends SceneTree
## Real Main, real actors and resources; explicit offline network spy.

const MainScene := preload("res://scenes/main.tscn")


class ConnectionSpy:
	extends GameConnection
	var entries := 0
	var disconnects := 0

	func _ready() -> void:
		pass

	func enter_loaded_world() -> void:
		entries += 1
		state = "connected"
		connection_state_changed.emit(state, "Offline projectile QA")

	func disconnect_game(_planned_refresh := false) -> void:
		disconnects += 1
		state = "disconnected"
		connection_state_changed.emit(state, "Offline projectile QA")


var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	create_timer(60).timeout.connect(func(): quit(1))
	_run.call_deferred()


func _check(label: String, value: bool) -> void:
	_checks += 1
	if not value:
		_failures.append(label)


func _run() -> void:
	var main := MainScene.instantiate()
	main.get_node("GameConnection").set_script(ConnectionSpy)
	root.add_child(main)
	main.get("_account_flow").use_legacy_entry()
	var connection: ConnectionSpy = main.connection
	var catalog: ActorCatalog = main.get("_actor_catalog")
	var manager: Node3D = main.get("_projectiles")
	var info := {
		"map_id": "training",
		"definition_profile": ActorCatalog.PROFILE_ID,
		"definition_hash": catalog.gameplay_definition_hash(),
		"mob_catalog_hash": catalog.mob_gameplay_hash,
		"character_catalog_hash": catalog.characters.content_hash,
		"skill_catalog_hash": catalog.skills.content_hash,
		"training_target_hash": catalog.training_target_hash,
		"half_size": 32
	}
	connection.state = "loading"
	main.call("_on_world_info", info)
	await main.call("_prepare_world", info)
	_check(
		"Main prepares and enters with projectile package",
		connection.entries == 1 and connection.disconnects == 0
	)
	# Freeze wall-clock Main updates during shader compilation/captures. Advance
	# the actual Main update explicitly below for deterministic flight timing.
	main.set_process(false)
	var target_id := "1".repeat(64)
	connection.server_time_us = 10_000_000
	var target := {
		"identity": target_id,
		"online": true,
		"name": "Projectile target",
		"x": 3.0,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"health": 760,
		"max_health": 760,
		"life_sequence": 0,
		"activity": 0,
		"attack_sequence": 0,
		"attack_action_id": "",
		"action_started_at_us": 0,
		"action_ends_at_us": 0
	}
	main.call(
		"_on_appearances",
		[{"character_id": target_id, "character_class": 0, "sex": 0, "weapon_vnum": 10}]
	)
	main.call("_on_players", [target])
	await process_frame
	var player: PlayerActor = main.get("_actors")[target_id]
	_check(
		"target plays equipped idle",
		not player.get_node("Visual").animation_player.current_animation.is_empty()
	)
	var resolved: Dictionary = main.call("_resolve_projectile_target", target_id)
	_check(
		"Main resolves rendered body center", not resolved.is_empty() and resolved.position.y > 0.5
	)
	var camera := Camera3D.new()
	main.add_child(camera)
	camera.position = Vector3(0, 5, 10)
	camera.look_at(Vector3(0, 1, 0))
	camera.current = true
	var gameplay: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://candidate/gameplay.v1.json")
	)
	for vnum: int in [301, 302, 391, 398]:
		var matches: Array = gameplay.mobs.filter(func(m: Dictionary): return int(m.vnum) == vnum)
		var definition: Dictionary = matches[0]
		var attack: Dictionary = definition.attacks[0]
		var launch: Dictionary = attack.projectile_launches[0]
		var row := {
			"id": vnum,
			"definition_vnum": vnum,
			"actor_id": definition.id,
			"name": definition.name,
			"health": definition.health,
			"max_health": definition.health,
			"x": -3.0,
			"y": 0.0,
			"z": 0.0,
			"heading": -PI / 2,
			"activity": 2,
			"attack_sequence": 1,
			"life_sequence": 0,
			"attack_action_id": attack.id,
			"action_started_at_us": 10_000_000,
			"action_ends_at_us": 10_000_000 + int(attack.playback_duration_us),
			"attack_target": target_id,
			"attack_target_life_sequence": 0
		}
		main.call("_on_monsters", [row])
		var actor: PveActor = main.get("_pve")["Monster_" + str(vnum)]
		var presentation: Node3D = actor.get_node("ActorVisual/Presentation")
		presentation.animation_player.seek(float(launch.start_us) / 1e6, true)
		presentation._process(0)
		_check("real actor signal creates Main flight", manager.snapshot().size() == 1)
		if not manager.snapshot().is_empty():
			_check(
				"Main flight uses rendered target",
				manager.snapshot()[0].target_position.distance_to(resolved.position) < 0.001
			)
		presentation._process(0)
		_check("Main signal does not duplicate", manager.snapshot().size() == 1)
		for step: int in range(4):
			main.call("_process", 1.0 / 60)
		await process_frame
		await RenderingServer.frame_post_draw
		_check(
			"Main capture saved",
			root.get_texture().get_image().save_png("res://projectile-%d.png" % vnum) == OK
		)
		main.call("_on_monsters", [])
		_check("source removal leaves Main flight", manager.snapshot().size() == 1)
		for frame: int in range(600):
			if manager.snapshot().is_empty():
				break
			main.call("_process", 1.0 / 60)
		_check("Main flight and impact drain", manager.snapshot().is_empty())
		await process_frame
		if vnum == 398:
			row.attack_sequence = 2
			main.call("_on_monsters", [row])
			var next_actor: PveActor = main.get("_pve")["Monster_" + str(vnum)]
			var next_presentation: Node3D = next_actor.get_node("ActorVisual/Presentation")
			next_presentation.animation_player.seek(float(launch.start_us) / 1e6, true)
			next_presentation._process(0)
			_check("disconnect fixture has active shot", manager.snapshot().size() == 1)
			connection.disconnect_game()
			_check("disconnect signal clears active shot", manager.snapshot().is_empty())
	main.call("_on_connection_state", "disconnected", "Offline QA")
	_check("world departure clears projectile state", manager.snapshot().is_empty())
	main.call("_on_players", [])
	await process_frame
	_check(
		"removed target no longer resolves",
		main.call("_resolve_projectile_target", target_id).is_empty()
	)
	await _test_population_visibility(main, gameplay, target)
	var file := FileAccess.open("res://report.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks": _checks, "failures": _failures}))
	file.close()
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	main.queue_free()
	await process_frame
	quit(0 if _failures.is_empty() else 1)


func _test_population_visibility(main: Node3D, gameplay: Dictionary, target: Dictionary) -> void:
	main.call("_on_players", [target])
	await process_frame
	var player: PlayerActor = main.get("_actors")[str(target.identity)]
	main.set("_local_actor", player)
	main.set("_original_map", true)
	var connection: GameConnection = main.connection
	connection.state = "connected"
	var definition: Dictionary = gameplay.mobs[0]
	var rows: Array = []
	for index in 2800:
		rows.append(
			{
				"id": 910000 + index,
				"definition_vnum": definition.vnum,
				"actor_id": definition.id,
				"name": definition.name,
				"health": definition.health,
				"max_health": definition.health,
				"x": 1000.0 + index,
				"y": 0.0,
				"z": 0.0,
				"life_sequence": 0,
				"attack_sequence": 0,
				"activity": 0
			}
		)
	rows[0].x = 3.0
	connection.monsters = rows
	main.call("_on_monsters", rows)
	_check("2800 subscribed mobs instantiate only nearby actor", main.get("_pve").size() == 1)
	_check(
		"presentation filtering retains full subscribed state", connection.monsters.size() == 2800
	)
	var Policy = preload("res://scripts/world/pve_visibility.gd")
	_check(
		"original approximate-distance edge included",
		Policy.includes({"x": 57.24, "y": 0, "z": 0}, Vector3.ZERO, func(_point): return true)
	)
	_check(
		"original approximate-distance outside excluded",
		not Policy.includes({"x": 57.26, "y": 0, "z": 0}, Vector3.ZERO, func(_point): return true)
	)
	_check(
		"malformed position excluded",
		not Policy.includes({"x": NAN, "y": 0, "z": 0}, Vector3.ZERO, func(_point): return true)
	)
	var readiness_calls := [0]
	var ready_probe := func(_point):
		readiness_calls[0] += 1
		return true
	var included := 0
	for row: Dictionary in rows:
		if Policy.includes(row, Vector3.ZERO, ready_probe):
			included += 1
	_check("distant population skips terrain lookups", included == 1 and readiness_calls[0] == 1)
	_check(
		"nearby unloaded terrain still excluded",
		not Policy.includes(rows[0], Vector3.ZERO, func(_point): return false)
	)
	player.server_position = Vector3(1001, 0, 0)
	main.call("_process", 0.3)
	var visible: Dictionary = main.get("_pve")
	_check("movement admits new rows without subscription update", visible.has("Monster_910001"))
	_check("movement removes distant actor", not visible.has("Monster_910000"))
	_check("movement keeps actor population bounded", visible.size() < 65)
	var stream: WorldStream = main.get("_stream")
	stream.set_active(true)
	main.call("_process", 0.3)
	_check("unready terrain releases actors", main.get("_pve").is_empty())
	stream.set_active(false)
	player.server_position = Vector3(3, 0, 0)
	rows[0].life_sequence = 1
	main.call("_process", 0.3)
	_check(
		"reentry uses latest authoritative life",
		int(main.get("_pve")["Monster_910000"].row.life_sequence) == 1
	)
	main.call("_on_monsters", [])
	main.call("_on_players", [])
	await process_frame
