extends Node3D
## Shared development world. Gameplay authority lives in SpacetimeDB.

const DEFAULT_SERVER := "http://127.0.0.1:3210"
const DEFAULT_DATABASE := "mt2-yongan-v2"
const LEGACY_SETTINGS_PATH := "user://client_settings.json"

var _actors: Dictionary = {}
var _local_actor: PlayerActor
var _profile := "default"
var _settings: Dictionary = {}
var _settings_path := ""
var _input_elapsed := 0.0
var _diagnostic_elapsed := 0.0
var _held_movement := false
var _marker: MeshInstance3D
var _marker_time := 0.0
var _stream: WorldStream
var _pve: Dictionary = {}
var _original_map := false
var _content_generation := 0

@onready var connection: GameConnection = $GameConnection
@onready var world: DevMap = $DevMap
@onready var camera_rig: OrbitCamera = $OrbitCamera
@onready var hud: DevHud = $DevHud


func _ready() -> void:
	_stream = WorldStream.new()
	_stream.name = "WorldStream"
	add_child(_stream)
	_stream.progress.connect(
		func(message: String):
			if not message.is_empty():
				hud.show_notice(message)
	)
	connection.require_content = true
	connection.content_load_requested.connect(_prepare_world)
	connection.monsters_changed.connect(_on_monsters)
	connection.loot_changed.connect(_on_loot)
	connection.item_drops_changed.connect(_on_item_drops)
	connection.inventory_changed.connect(hud.set_inventory)
	connection.connection_state_changed.connect(_on_connection_state)
	connection.players_changed.connect(_on_players)
	connection.obstacles_changed.connect(world.set_obstacles)
	connection.chat_changed.connect(hud.set_chat)
	connection.world_info_changed.connect(_on_world_info)
	connection.reducer_failed.connect(hud.show_notice)
	hud.connect_requested.connect(_connect_game)
	hud.disconnect_requested.connect(connection.disconnect_game)
	hud.reconnect_requested.connect(connection.reconnect_game)
	hud.reset_identity_requested.connect(connection.reset_identity)
	hud.attack_requested.connect(connection.perform_attack)
	hud.pickup_requested.connect(_pickup)
	hud.move_item_requested.connect(connection.move_item)
	hud.equip_item_requested.connect(connection.equip_item)
	hud.unequip_item_requested.connect(connection.unequip_item)
	hud.use_item_requested.connect(connection.use_item)
	hud.chat_submitted.connect(connection.send_chat)
	hud.debug_option_changed.connect(_on_debug_option)
	hud.screenshot_requested.connect(_save_screenshot)
	hud.copy_diagnostics_requested.connect(_copy_diagnostics)
	_load_settings()
	hud.set_connection_defaults(
		_settings.server_url, _settings.database, _settings.player_name, _profile
	)
	hud.set_connection_state("disconnected", "Choose a name and enter the shared map.")
	_create_marker()
	var dev_capture := preload("res://scripts/dev_capture.gd").new()
	dev_capture.name = "DevCapture"
	add_child(dev_capture)
	dev_capture.configure(self)
	if bool(_settings.get("auto_connect", false)):
		_connect_game(_settings.server_url, _settings.database, _settings.player_name)


func _process(delta: float) -> void:
	if is_instance_valid(_local_actor):
		_stream.focus(_local_actor.server_position)
	if _original_map:
		for actor: PlayerActor in _actors.values():
			actor.visible = _stream.ready_at(actor.server_position)
		for actor: PveActor in _pve.values():
			actor.visible = _stream.ready_at(actor.position)
	_diagnostic_elapsed += delta
	if _diagnostic_elapsed >= 0.25:
		_diagnostic_elapsed = 0.0
		hud.set_diagnostics(dev_snapshot())
	_marker_time = maxf(0.0, _marker_time - delta)
	_marker.visible = _marker_time > 0.0 and connection.state == "connected"
	if _marker.visible:
		_marker.rotation.y += delta


func _physics_process(delta: float) -> void:
	_input_elapsed += delta
	if _input_elapsed < 0.1:
		return
	_input_elapsed = 0.0
	if connection.state != "connected":
		_held_movement = false
		return
	var input := Vector2.ZERO
	if not hud.wants_keyboard() and get_window().has_focus():
		input.x = float(_key_down(KEY_D, KEY_RIGHT)) - float(_key_down(KEY_A, KEY_LEFT))
		input.y = float(_key_down(KEY_S, KEY_DOWN)) - float(_key_down(KEY_W, KEY_UP))
	if input.length_squared() > 0:
		var direction := camera_rig.move_direction(input.normalized())
		if (
			is_instance_valid(_local_actor)
			and not _stream.ready_at(
				_local_actor.server_position + Vector3(direction.x, 0, direction.y) * 2
			)
		):
			connection.stop_moving()
			return
		connection.set_move_input(direction.x, direction.y)
		_held_movement = true
		_marker_time = 0.0
	elif _held_movement:
		connection.stop_moving()
		_held_movement = false


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F3 and event.ctrl_pressed:
			hud.toggle_debug()
			get_viewport().set_input_as_handled()
			return
		if hud.handle_key(event):
			get_viewport().set_input_as_handled()
			return
		match event.keycode:
			KEY_ENTER:
				hud.focus_chat()
			KEY_SPACE:
				connection.perform_attack()
			KEY_E, KEY_Z:
				_pickup()
			KEY_ESCAPE:
				get_viewport().gui_release_focus()
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		camera_rig.orbit(event.relative)
	if event is InputEventMouseButton and event.pressed:
		match event.button_index:
			MOUSE_BUTTON_WHEEL_UP:
				camera_rig.zoom(-0.7)
			MOUSE_BUTTON_WHEEL_DOWN:
				camera_rig.zoom(0.7)
			MOUSE_BUTTON_LEFT:
				if connection.state == "connected":
					_click_move(event.position)


func dev_snapshot() -> Dictionary:
	var local_row: Dictionary = _local_actor.row if is_instance_valid(_local_actor) else {}
	var rendered := _local_actor.position if is_instance_valid(_local_actor) else Vector3.ZERO
	var authoritative := Vector3(
		float(local_row.get("x", 0)), float(local_row.get("y", 0)), float(local_row.get("z", 0))
	)
	return {
		"connection_state": connection.state,
		"fps": Engine.get_frames_per_second(),
		"server_url":
		connection.endpoint if not connection.endpoint.is_empty() else _settings.server_url,
		"database":
		connection.database if not connection.database.is_empty() else _settings.database,
		"profile": _profile,
		"identity": connection.local_identity,
		"players": connection.players.size(),
		"player_rows": connection.players.duplicate(true),
		"rx_messages": connection.rx_messages,
		"tx_messages": connection.tx_messages,
		"snapshot_age_ms":
		(
			Time.get_ticks_msec() - connection.last_snapshot_msec
			if connection.last_snapshot_msec > 0
			else -1
		),
		"last_reducer_rtt_ms": connection.last_reducer_rtt_ms,
		"position": [rendered.x, rendered.y, rendered.z],
		"server_position": [authoritative.x, authoritative.y, authoritative.z],
		"activity": int(local_row.get("activity", 0)),
		"world_tick_ms": int(connection.world_info.get("tick_ms", 50)),
		"debug_visible": hud.is_debug_visible(),
		"camera_distance": camera_rig.distance,
		"obstacles": connection.obstacles.size(),
		"monsters": connection.monsters.duplicate(true),
		"loot": connection.loot.duplicate(true),
		"inventory": connection.own_inventory().duplicate(true),
		"item_drops": connection.item_drops.duplicate(true),
		"ui": hud.inventory_snapshot(),
		"map_chunks": _stream.loaded.keys(),
		"content_error": _stream.last_error,
	}


func _key_down(primary: Key, alternate: Key) -> bool:
	return Input.is_physical_key_pressed(primary) or Input.is_physical_key_pressed(alternate)


func _connect_game(server_url: String, database: String, player_name: String) -> void:
	_settings.server_url = server_url.strip_edges()
	_settings.database = database.strip_edges()
	_settings.player_name = player_name.strip_edges()
	DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path(_settings_path.get_base_dir())
	)
	var file := FileAccess.open(_settings_path, FileAccess.WRITE)
	if file:
		(
			file
			. store_string(
				(
					JSON
					. stringify(
						{
							"server_url": _settings.server_url,
							"database": _settings.database,
							"player_name": _settings.player_name,
						}
					)
				)
			)
		)
	connection.connect_game(server_url, database, player_name, _profile)


func _on_connection_state(state: String, message: String) -> void:
	if state == "connected":
		hud.set_profile(
			(
				(connection.endpoint + "/" + connection.database + "/" + connection.local_identity)
				. sha256_text()
			)
		)
	hud.set_connection_state(state, message)
	if state in ["connecting", "disconnected", "error"]:
		_content_generation += 1
		_stream.set_active(false)
	if state != "connected":
		_held_movement = false


func _on_players(rows: Array) -> void:
	var present: Dictionary = {}
	for row: Dictionary in rows:
		if not bool(row.get("online", false)):
			continue
		var identity := str(row.identity)
		present[identity] = true
		if not _actors.has(identity):
			var actor := PlayerActor.new()
			actor.name = "Player_" + identity.left(12)
			$Players.add_child(actor)
			_actors[identity] = actor
		var player: PlayerActor = _actors[identity]
		var is_local := identity == connection.local_identity
		player.apply_state(row, is_local)
		if is_local:
			_local_actor = player
			camera_rig.target = player
			hud.set_player_info(row)
	for identity: String in _actors.keys():
		if not present.has(identity):
			_actors[identity].queue_free()
			_actors.erase(identity)
	if not present.has(connection.local_identity):
		_local_actor = null
		camera_rig.target = null
		hud.set_player_info({})
	hud.set_players(rows, connection.local_identity)


func _on_world_info(info: Dictionary) -> void:
	world.half_size = float(info.get("half_size", 32))
	hud.set_world_info(info)
	if not info.is_empty():
		_original_map = str(info.get("map_id", "training")) == "metin2_map_a1"
		world.visible = not _original_map
		_stream.visible = _original_map


func _prepare_world(info: Dictionary) -> void:
	var generation := _content_generation
	if str(info.get("map_id", "training")) == "metin2_map_a1":
		var ready := await _stream.prepare(str(info.get("content_hash", "")))
		if generation != _content_generation or connection.state != "loading":
			return
		if not ready:
			connection.disconnect_game()
			hud.show_notice(_stream.failure_message)
			return
		_stream.set_active(true)
	connection.enter_loaded_world()


func _on_monsters(rows: Array) -> void:
	_sync_pve(rows, false)


func _on_loot(rows: Array) -> void:
	_sync_pve(rows, true)


func _on_item_drops(rows: Array) -> void:
	_sync_pve(rows, true, true)


func _sync_pve(rows: Array, loot_mode: bool, item_mode: bool = false) -> void:
	var prefix := "Item_" if item_mode else ("Loot_" if loot_mode else "Monster_")
	var present: Dictionary = {}
	for row: Dictionary in rows:
		var id := prefix + str(row.id)
		present[id] = true
		if not _pve.has(id):
			var actor := PveActor.new()
			actor.name = id
			actor.loot_mode = loot_mode
			actor.item_mode = item_mode
			add_child(actor)
			_pve[id] = actor
		_pve[id].apply_state(row)
	for id: String in _pve.keys():
		if id.begins_with(prefix) and not present.has(id):
			_pve[id].queue_free()
			_pve.erase(id)


func _pickup() -> void:
	if not is_instance_valid(_local_actor):
		return
	var nearest: Dictionary = {}
	var nearest_distance := INF
	var item_mode := false
	for drops: Array in [connection.loot, connection.item_drops]:
		for row: Dictionary in drops:
			var d := Vector3(float(row.x), float(row.y), float(row.z)).distance_to(
				_local_actor.position
			)
			if d < nearest_distance:
				nearest = row
				nearest_distance = d
				item_mode = row.has("vnum")
	if not nearest.is_empty():
		if item_mode:
			connection.pickup_item_drop(int(nearest.id))
		else:
			connection.pickup_loot(int(nearest.id))


func _click_move(screen_position: Vector2) -> void:
	var hit: Variant = camera_rig.ground_point(screen_position)
	if _original_map:
		var camera := camera_rig.camera
		var origin := camera.project_ray_origin(screen_position)
		var query := PhysicsRayQueryParameters3D.create(
			origin, origin + camera.project_ray_normal(screen_position) * 500
		)
		var result := get_world_3d().direct_space_state.intersect_ray(query)
		hit = result.get("position")
	if hit == null:
		return
	var point: Vector3 = hit
	if not _original_map:
		point.x = clampf(point.x, -world.half_size + 0.45, world.half_size - 0.45)
		point.z = clampf(point.z, -world.half_size + 0.45, world.half_size - 0.45)
	if not _stream.ready_at(point):
		return
	connection.move_to(point.x, point.z)
	_marker.position = point + Vector3.UP * 0.1
	_marker_time = 1.5


func _create_marker() -> void:
	_marker = MeshInstance3D.new()
	_marker.name = "MoveTarget"
	var ring := TorusMesh.new()
	ring.inner_radius = 0.33
	ring.outer_radius = 0.4
	ring.rings = 24
	ring.ring_segments = 8
	_marker.mesh = ring
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("f4d578")
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_marker.material_override = material
	_marker.visible = false
	add_child(_marker)


func _on_debug_option(option: String, value: Variant) -> void:
	match option:
		"show_collision":
			world.show_collision(bool(value))
		"shadows":
			$Sun.shadow_enabled = bool(value)
		"camera_distance":
			camera_rig.distance = float(value)


func _save_screenshot() -> void:
	await RenderingServer.frame_post_draw
	var directory := "user://screenshots"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var path := directory + "/world-%d.png" % Time.get_unix_time_from_system()
	var error := get_viewport().get_texture().get_image().save_png(path)
	hud.show_notice(
		"Saved " + ProjectSettings.globalize_path(path) if error == OK else "Screenshot failed."
	)


func _copy_diagnostics() -> void:
	DisplayServer.clipboard_set(JSON.stringify(dev_snapshot(), "  "))
	hud.show_notice("Diagnostics copied. Identity tokens are excluded.")


func _load_settings() -> void:
	_settings = {
		"server_url": DEFAULT_SERVER, "database": DEFAULT_DATABASE, "player_name": "Warrior"
	}
	var overrides: Dictionary = {}
	var arguments := OS.get_cmdline_user_args()
	var index := 0
	while index < arguments.size():
		var argument := arguments[index]
		if argument == "--auto-connect":
			overrides.auto_connect = true
		elif (
			argument in ["--server", "--database", "--name", "--profile"]
			and index + 1 < arguments.size()
		):
			index += 1
			match argument:
				"--server":
					overrides.server_url = arguments[index]
				"--database":
					overrides.database = arguments[index]
				"--name":
					overrides.player_name = arguments[index]
				"--profile":
					_profile = arguments[index]
		index += 1
	var profile_pattern := RegEx.create_from_string("[^a-z0-9_-]")
	_profile = profile_pattern.sub(_profile.to_lower(), "", true).left(40)
	if _profile.is_empty():
		_profile = "default"
	_settings_path = "user://profiles/%s/client_settings.json" % _profile
	# Precedence: built-in defaults, packaged defaults, saved profile, CLI overrides.
	var config_path := "res://client_config.json"
	if OS.has_feature("template") and not OS.has_feature("web"):
		config_path = OS.get_executable_path().get_base_dir().path_join("client_config.json")
	if FileAccess.file_exists(config_path):
		_merge_config(config_path)
	var packaged_database := str(_settings.database)
	if FileAccess.file_exists(_settings_path):
		_merge_config(_settings_path)
	elif _profile == "default" and FileAccess.file_exists(LEGACY_SETTINGS_PATH):
		_merge_config(LEGACY_SETTINGS_PATH)
	_settings.merge(overrides, true)
	if OS.has_feature("web"):
		# Browser and game API share an origin; avoid stale saved deployment addresses.
		_settings.server_url = str(JavaScriptBridge.eval("window.location.origin"))
		_settings.database = packaged_database


func _merge_config(path: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		return
	for key: String in ["server_url", "database", "player_name"]:
		if parsed.get(key) is String and not str(parsed[key]).is_empty():
			_settings[key] = parsed[key]
	if (
		parsed.get("default_player_name") is String
		and not str(parsed.default_player_name).is_empty()
	):
		_settings.player_name = parsed.default_player_name
