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
		"half_size": 640,
	}
	connection.state = "loading"
	main.call("_on_world_info", info)
	await main.call("_prepare_world", info)
	_check(connection.entries == 1 and connection.disconnects == 0, "Main content gate enters")
	_check(layer.actors.size() == 1, "Main connection activates exactly one original guard")
	if layer.actors.is_empty():
		_finish(main)
		return
	# Keep the real stream but stop background neighbor loading during this bounded fixture.
	stream.set_process(false)
	var spawn: Dictionary = definition.placements[0]
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
		layer.actors.size() == 1 and layer.actors[spawn.id] == actor,
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
	_check(layer.actors.size() == 1, "chunk reload recreates one NPC")
	for state: String in ["leaving", "lobby", "disconnected", "error", "connecting"]:
		connection.state = state
		main.call("_on_connection_state", state, "Offline lifecycle QA")
		_check(
			layer.actors.is_empty() and layer.get_child_count() == 0, state + " clears NPC layer"
		)
		connection.state = "loading"
		await main.call("_prepare_world", info)
		_check(layer.actors.size() == 1, state + " reentry restores one NPC")
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
	_check(layer.actors.size() == 1, "final Main scene holds one NPC after repeated transitions")
	_check_catalog_failures()
	_finish(main)


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
