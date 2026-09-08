extends SceneTree
## Real Main/map/content lifecycle with an explicit offline connection spy.

const MainScene := preload("res://scenes/main.tscn")
const Catalog := preload("res://scripts/content/npc_catalog.gd")


class ConnectionSpy:
	extends GameConnection
	var entries := 0
	var disconnects := 0

	func _ready() -> void:
		pass

	func enter_loaded_world() -> void:
		entries += 1
		state = "connected"
		connection_state_changed.emit(state, "Offline NPC component QA")

	func disconnect_game() -> void:
		disconnects += 1
		state = "disconnected"
		connection_state_changed.emit(state, "Offline NPC component QA")


var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	create_timer(60).timeout.connect(func(): quit(1))
	_run.call_deferred()


func _run() -> void:
	var main := MainScene.instantiate()
	main.get_node("GameConnection").set_script(ConnectionSpy)
	root.add_child(main)
	main.get("_account_flow").use_legacy_entry()
	var connection: ConnectionSpy = main.connection
	var layer: WorldNpcs = main.get("_npcs")
	var stream: WorldStream = main.get("_stream")
	var catalog := Catalog.new()
	_check(catalog.load_required(), "installed catalog loads")
	if catalog.maps.is_empty():
		_finish(main)
		return
	var map_id: String = catalog.maps.keys()[0]
	var definition: Dictionary = catalog.maps[map_id]
	var actor_catalog: ActorCatalog = main.get("_actor_catalog")
	var info := {
		"map_id": map_id,
		"npc_catalog_hash": FileAccess.get_sha256(Catalog.PATH),
		"content_hash": definition.content_hash,
		"definition_profile": ActorCatalog.PROFILE_ID,
		"definition_hash": actor_catalog.gameplay_definition_hash(),
		"character_catalog_hash": actor_catalog.characters.content_hash,
		"skill_catalog_hash": actor_catalog.skills.content_hash,
		"training_target_hash": actor_catalog.training_target_hash,
		"half_size": 640,
	}
	connection.state = "loading"
	main.call("_on_world_info", info)
	await main.call("_prepare_world", info)
	_check(connection.entries == 1 and connection.disconnects == 0, "Main content gate enters")
	_check(
		layer.actors.size() == _expected_count(definition, stream),
		"Main connection activates all NPCs on loaded chunks"
	)
	if layer.actors.is_empty():
		_finish(main)
		return
	# Keep the real stream but stop background neighbor loading during this bounded fixture.
	stream.set_process(false)
	var guards: Array = definition.placements.filter(
		func(row: Dictionary) -> bool: return row.id == "spawn.yongan.city-guard-20354"
	)
	_check(guards.size() == 1, "fixture resolves the exact original guard")
	if guards.size() != 1:
		_finish(main)
		return
	var spawn: Dictionary = guards[0]
	var actor: NpcActor = layer.actors[spawn.id]
	_check(
		actor.position.is_equal_approx(Vector3(605, 198.515, 663)),
		"original point and baked height"
	)
	_check(is_equal_approx(actor.rotation.y, float(spawn.yaw)), "catalog heading applied once")
	var label := actor.get_node("NameLabel") as Label3D
	_check(
		label.text == "City Guard" and label.modulate == Color8(122, 231, 93),
		"original NPC name color"
	)
	_check(
		actor.find_children("*", "CollisionObject3D", true, false).all(_is_picking_only),
		"presentation adds no invisible obstacles"
	)
	var animation: AnimationPlayer = actor.get("_animation")
	var played: Dictionary = {}
	for iteration in range(24):
		actor.call("_next_idle")
		played[animation.current_animation] = true
	_check(played.size() == 2, "both source-weighted idle variants selected")
	_check(animation.is_playing(), "native imported idle animates")
	for mesh: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		_check(
			mesh.skin != null and mesh.get_node_or_null(mesh.skeleton) is Skeleton3D,
			"body and rigid weapon deform on skeleton"
		)
	layer.refresh()
	layer.refresh()
	_check(
		(
			layer.actors.size() == _expected_count(definition, stream)
			and layer.actors[spawn.id] == actor
		),
		"refresh preserves stable instance"
	)
	var chunk: Node = stream.loaded["002002"]
	stream.loaded.erase("002002")
	stream.remove_child(chunk)
	chunk.queue_free()
	layer.refresh()
	_check(
		layer.actors.is_empty() and layer.get_child_count() == 0,
		"unloaded terrain removes NPC immediately"
	)
	_check(await stream.call("_load_chunk", "002002"), "real map chunk reloads")
	layer.refresh()
	_check(
		layer.actors.size() == _expected_count(definition, stream),
		"chunk reload recreates the loaded population"
	)
	for state: String in ["leaving", "lobby", "disconnected", "error", "connecting"]:
		connection.state = state
		main.call("_on_connection_state", state, "Offline lifecycle QA")
		_check(
			layer.actors.is_empty() and layer.get_child_count() == 0, state + " clears NPC layer"
		)
		connection.state = "loading"
		await main.call("_prepare_world", info)
		_check(
			layer.actors.size() == _expected_count(definition, stream),
			state + " reentry restores the loaded population"
		)
	var wrong := info.duplicate(true)
	wrong.content_hash = "0".repeat(64)
	_check(not layer.prepare(wrong, stream.ready_at), "wrong terrain version rejects NPC layout")
	_check(layer.actors.is_empty(), "failed prepare clears previous map actors")
	_check(
		layer.prepare({"map_id": "training"}, stream.ready_at),
		"training map needs no original NPCs"
	)
	layer.set_active(true)
	_check(layer.actors.is_empty(), "switching maps does not retain Yongan NPCs")
	connection.state = "loading"
	await main.call("_prepare_world", info)
	actor = layer.actors[spawn.id]
	main.camera_rig.target = actor
	main.camera_rig.distance = 7.5
	main.camera_rig.pitch = deg_to_rad(30)
	main.camera_rig.yaw = actor.rotation.y + PI
	await create_timer(0.4).timeout
	var camera: Camera3D = main.camera_rig.camera
	var screen := camera.unproject_position(actor.global_position + Vector3.UP)
	var pick := WorldPicker.new().pick(camera, main.get_world_3d().direct_space_state, screen)
	_check(
		pick.get("kind") == "npc" and pick.get("actor") == actor,
		"real ray picks guard separately from combat"
	)
	var dialogue: Control = main.hud.npc_panel
	dialogue.set_interaction(
		{
			"session_id": 1,
			"title": "City Guard",
			"body": "Welcome to Yongan. Stay alert when you leave the village."
		}
	)
	_check(
		dialogue.snapshot().visible and not main.hud.wants_keyboard(),
		"dialogue does not capture movement focus"
	)
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://world-npc.png")
	_check(
		layer.actors.size() == _expected_count(definition, stream),
		"final Main scene holds the loaded population after transitions"
	)
	_check_catalog_failures()
	await _check_static_landmarks(main, catalog, definition, layer, stream)
	await _check_area_spawns(main, catalog, definition, layer, stream)
	_finish(main)


func _check_area_spawns(
	main: Node3D, catalog: NpcCatalog, definition: Dictionary, layer: WorldNpcs, stream: WorldStream
) -> void:
	if not FileAccess.file_exists("res://tests/npc-spawn-rows.json"):
		return
	var rows: Array = JSON.parse_string(
		FileAccess.get_file_as_string("res://tests/npc-spawn-rows.json")
	)
	_check(rows.size() == definition.get("areas", []).size(), "snapshot covers every NPC area")
	for row: Dictionary in rows:
		# JSON numbers are floats; the real typed SDK delivers these columns as integers.
		for field: String in ["x_cm", "z_cm", "heading_degrees"]:
			_check(float(row[field]) == int(row[field]), "snapshot integer column is exact")
			row[field] = int(row[field])
		var point := Vector3(float(row.x_cm) / 100, row.height_m, float(row.z_cm) / 100)
		var chunk := "%03d%03d" % [int(point.x / 256), int(point.z / 256)]
		_check(await stream.call("_load_chunk", chunk), "area NPC terrain loads")
	main.connection.npc_spawns_changed.emit(rows)
	for row: Dictionary in rows:
		_check(layer.actors.has(row.spawn_id), "area NPC appears from replicated-row signal")
		if not layer.actors.has(row.spawn_id):
			continue
		var actor: NpcActor = layer.actors[row.spawn_id]
		var data: Dictionary = catalog.actors[row.actor_id]
		_check(
			actor.position.is_equal_approx(
				Vector3(float(row.x_cm) / 100, row.height_m, float(row.z_cm) / 100)
			),
			"area NPC uses captured server position and terrain height"
		)
		_check(absf(actor.rotation.y - float(row.yaw)) < 0.00001, "area NPC uses server heading")
		_check(actor.get_node("NameLabel").text == data.name, "area NPC has original name")
		var animation: AnimationPlayer = actor.get("_animation")
		_check(animation != null and animation.is_playing(), "area NPC plays original idle")
		_check(
			actor.find_children("*", "CollisionObject3D", true, false).all(_is_picking_only),
			"area NPC introduces no invisible movement obstacle"
		)
		var camera: Camera3D = main.camera_rig.camera
		var center := actor.global_position + Vector3.UP * float(data.label_height) * 0.5
		camera.global_position = center + Vector3(0.3, 0.45, -1).normalized() * 8.0
		camera.look_at(center)
		await create_timer(0.3).timeout
		if DisplayServer.get_name() != "headless":
			await RenderingServer.frame_post_draw
			_check(
				(
					root.get_texture().get_image().save_png(
						"user://world-npc-area-%s.png" % str(int(data.vnum))
					)
					== OK
				),
				"area NPC screenshot saved"
			)
	main.connection.npc_spawns_changed.emit([])
	_check(
		rows.all(func(row: Dictionary): return not layer.actors.has(row.spawn_id)),
		"removing subscribed rows removes area NPC actors"
	)
	main.connection.npc_spawns_changed.emit(rows)
	_check(
		rows.all(func(row: Dictionary): return layer.actors.has(row.spawn_id)),
		"restored rows recreate area NPC actors"
	)


func _check_static_landmarks(
	main: Node3D, catalog: NpcCatalog, definition: Dictionary, layer: WorldNpcs, stream: WorldStream
) -> void:
	main.hud.npc_panel.hide()
	main.camera_rig.set_process(false)
	for spawn: Dictionary in definition.placements:
		var data: Dictionary = catalog.actors[spawn.actor_id]
		if data.get("presentation", "animated") != "static":
			continue
		var chunk := "%03d%03d" % [int(spawn.position[0] / 256), int(spawn.position[2] / 256)]
		_check(await stream.call("_load_chunk", chunk), "landmark terrain loads")
		layer.refresh()
		_check(layer.actors.has(spawn.id), "landmark appears on its original terrain chunk")
		if not layer.actors.has(spawn.id):
			continue
		var actor: NpcActor = layer.actors[spawn.id]
		_check(actor.get("_animation") == null, "static landmark has no fabricated animation")
		_check(actor.get_node("NameLabel").text == data.name, "original landmark name")
		_check(
			actor.position.is_equal_approx(
				Vector3(spawn.position[0], spawn.position[1], spawn.position[2])
			),
			"landmark uses catalog terrain height and position"
		)
		_check(
			actor.find_children("*", "CollisionObject3D", true, false).all(_is_picking_only),
			"landmark introduces no invisible movement obstacle"
		)
		var camera: Camera3D = main.camera_rig.camera
		var center := actor.global_position + Vector3.UP * float(data.label_height) * 0.5
		var distance := maxf(float(data.label_height) * 3.0, 8.0)
		camera.global_position = center + Vector3(0.3, 0.45, -1).normalized() * distance
		camera.look_at(center)
		await create_timer(0.4).timeout
		if DisplayServer.get_name() != "headless":
			await RenderingServer.frame_post_draw
			_check(
				(
					root.get_texture().get_image().save_png(
						"user://world-npc-static-%s.png" % str(int(data.vnum))
					)
					== OK
				),
				"landmark screenshot saved"
			)


func _expected_count(definition: Dictionary, stream: WorldStream) -> int:
	var result := 0
	for spawn: Dictionary in definition.placements:
		var chunk := "%03d%03d" % [int(spawn.position[0] / 256), int(spawn.position[2] / 256)]
		if stream.loaded.has(chunk):
			result += 1
	return result


func _check_catalog_failures() -> void:
	var document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(Catalog.PATH))
	for field: String in ["actor_id", "position", "yaw"]:
		var broken := document.duplicate(true)
		match field:
			"actor_id":
				broken.maps[0].placements[0][field] = "unknown"
			"position":
				broken.maps[0].placements[0][field] = [NAN, 0, 0]
			"yaw":
				broken.maps[0].placements[0][field] = INF
		var catalog := Catalog.new()
		_check(not catalog.load_document(broken), "invalid " + field + " rejected")
		_check(
			catalog.actors.is_empty() and catalog.maps.is_empty(),
			"invalid catalog leaves no partial state"
		)


func _finish(main: Node) -> void:
	var report := {
		"passed": _failures.is_empty(),
		"checks": _checks,
		"failures": _failures,
		"connection": "offline spy; no multiplayer claim"
	}
	var file := FileAccess.open("user://world-npc.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	file.close()
	main.queue_free()
	await process_frame
	print("WORLD_NPC_SMOKE ", "PASS" if _failures.is_empty() else "FAIL", " ", _checks, " checks")
	quit(0 if _failures.is_empty() else 1)


func _check(value: bool, message: String) -> void:
	if value:
		_checks += 1
	else:
		_failures.append(message)
		push_error("WORLD_NPC_SMOKE FAIL " + message)


func _is_picking_only(body: CollisionObject3D) -> bool:
	return body.collision_layer == 2 and body.collision_mask == 0
