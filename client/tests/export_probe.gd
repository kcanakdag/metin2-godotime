extends Node
## Export-test instrumentation. The release staging tool excludes this file by default.
## Exposes snapshots and a fixed list of ordinary validated client actions, never eval/tokens.

var _elapsed := 0.0
var _profile_started_us := 0
var _profile_frames := 0
var _performance_profile: Dictionary = {}
var _callback: JavaScriptObject
var _report := ""
var _commands := ""
var _sequence := -1
var _errors: Array[String] = []
var _attack_ack_sequence := 0
var _perform_attack_acks: Array[Dictionary] = []
var _target_ack_sequence := 0
var _select_combat_target_acks: Array[Dictionary] = []
var _public_action_history: Array[Dictionary] = []
var _last_public_actions: Dictionary = {}
var _last_own_action_fingerprint := ""
var _monster_health_history: Array[Dictionary] = []
var _last_monster_health: Dictionary = {}
var _monster_action_history: Array[Dictionary] = []
var _last_monster_actions: Dictionary = {}
var _screen_wave_history: Array[Dictionary] = []
var _last_screen_wave_fingerprint := ""


func _ready() -> void:
	get_parent().connection.reducer_failed.connect(_on_reducer_failed)
	get_parent().connection.reducer_completed.connect(_on_reducer_completed)
	get_parent().connection.players_changed.connect(_on_players_changed)
	get_parent().connection.monsters_changed.connect(_on_monsters_changed)
	get_parent().connection.connection_state_changed.connect(_on_connection_state_changed)
	if OS.has_feature("web"):
		_callback = JavaScriptBridge.create_callback(_web_command)
		JavaScriptBridge.get_interface("window").mt2Command = _callback
		_publish_ack_views()
		_publish_error_view()
		_publish_own_action_view()
		_publish_monster_health_view()
	else:
		var args := OS.get_cmdline_user_args()
		for i in range(args.size() - 1):
			if args[i] == "--probe-report":
				_report = args[i + 1]
			if args[i] == "--probe-commands":
				_commands = args[i + 1]


func _process(delta: float) -> void:
	_poll_native_command()
	if _profile_started_us > 0:
		_profile_frames += 1
		var duration := Time.get_ticks_usec() - _profile_started_us
		if duration < 5_000_000:
			return
		_performance_profile = {
			"duration_us": duration,
			"frames": _profile_frames,
			"mean_fps": float(_profile_frames) * 1_000_000.0 / float(duration),
			"snapshot_sampling": false,
		}
		_profile_started_us = 0
	_capture_screen_wave()
	_elapsed += delta
	if _elapsed < 0.2:
		return
	_elapsed = 0
	var snapshot: Dictionary = get_parent().dev_snapshot()
	snapshot["drop_presentations"] = []
	for actor: PveActor in get_parent().get("_pve").values():
		if actor.loot_mode:
			snapshot.drop_presentations.append(actor.presentation_snapshot())
	snapshot["progression"] = _project_rows(
		snapshot.get("progression", []),
		[
			"character_id",
			"level",
			"experience",
			"next_exp",
			"level_step",
			"unspent_stat_points",
			"strength",
			"vitality",
			"dexterity",
			"intelligence",
			"current_sp",
			"max_sp",
			"display_attack_min",
			"display_attack_max",
			"display_defense",
		]
	)
	snapshot["command_feedback"] = _project_rows(
		snapshot.get("command_feedback", []),
		["id", "request_id", "severity", "message", "created_at"]
	)
	snapshot["performance_profile"] = _performance_profile
	snapshot["errors"] = _errors
	snapshot["perform_attack_acks"] = _perform_attack_acks.duplicate(true)
	snapshot["select_combat_target_acks"] = _select_combat_target_acks.duplicate(true)
	snapshot["public_action_history"] = _public_action_history.duplicate(true)
	snapshot["monster_health_history"] = _monster_health_history.duplicate(true)
	snapshot["monster_action_history"] = _monster_action_history.duplicate(true)
	snapshot["screen_wave_history"] = _screen_wave_history.duplicate(true)
	snapshot["state_message"] = get_parent().connection.state_message
	var actors: Array = []
	for actor in get_parent().get_node("Players").get_children():
		if not actor.is_visible_in_tree():
			continue
		var actor_state: Dictionary = actor.presentation_snapshot()
		actor_state["position"] = [actor.position.x, actor.position.y, actor.position.z]
		actors.append(actor_state)
	snapshot["rendered_actors"] = actors
	var monsters: Array = []
	for actor: PveActor in get_parent()._pve.values():
		if actor.loot_mode or not actor.is_visible_in_tree():
			continue
		var actor_state := actor.presentation_snapshot()
		actor_state["position"] = [actor.position.x, actor.position.y, actor.position.z]
		monsters.append(actor_state)
	snapshot["rendered_monsters"] = monsters
	snapshot["rendered_npcs"] = _npc_snapshot()
	snapshot["npc_interaction"] = get_parent().connection.npc_interaction.duplicate(true)
	snapshot["npc_panel"] = get_parent().hud.npc_panel.snapshot()
	snapshot["hover_npc"] = (
		get_parent()._hovered_npc.spawn_id if is_instance_valid(get_parent()._hovered_npc) else ""
	)
	snapshot["world_info"] = {
		"map_id": str(get_parent().connection.world_info.get("map_id", "")),
		"content_hash": str(get_parent().connection.world_info.get("content_hash", "")),
	}
	var payload := JSON.stringify(snapshot)
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2Snapshot = payload
	elif not _report.is_empty():
		var result := _publish_native_snapshot(payload)
		if result != OK:
			push_error("Export probe snapshot publication failed: %s" % error_string(result))


func _npc_snapshot() -> Array[Dictionary]:
	var rows: Array[Dictionary] = []
	var layer := get_parent().get_node_or_null("WorldNpcs")
	if layer == null:
		return rows
	var camera := get_viewport().get_camera_3d()
	for actor: Node3D in layer.get_children():
		if not actor.is_visible_in_tree():
			continue
		var label := actor.get_node_or_null("NameLabel") as Label3D
		var animations := actor.find_children("*", "AnimationPlayer", true, false)
		var player: AnimationPlayer = animations[0] if animations.size() == 1 else null
		var point := actor.global_position + Vector3.UP
		var screen := Vector2.ZERO
		var in_view := camera != null and not camera.is_position_behind(point)
		if in_view:
			screen = camera.unproject_position(point)
			in_view = get_viewport().get_visible_rect().has_point(screen)
		(
			rows
			. append(
				{
					"spawn_id": str(actor.get("spawn_id")),
					"name": label.text if label != null else "",
					"position": [actor.position.x, actor.position.y, actor.position.z],
					"yaw": actor.rotation.y,
					"idle": str(player.current_animation) if player != null else "",
					"playing": player != null and player.is_playing(),
					"in_view": in_view,
					"screen": [screen.x, screen.y],
				}
			)
		)
	return rows


func _publish_native_snapshot(payload: String) -> Error:
	# Readers keep the previous complete snapshot until the replacement is ready.
	var pending := _report + ".tmp"
	var file := FileAccess.open(pending, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(payload)
	var result := file.get_error()
	file.close()
	if result != OK:
		DirAccess.remove_absolute(pending)
		return result
	return DirAccess.rename_absolute(pending, _report)


func _poll_native_command() -> void:
	if _commands.is_empty() or not FileAccess.file_exists(_commands):
		return
	var command: Variant = JSON.parse_string(FileAccess.get_file_as_string(_commands))
	if command is Dictionary and int(command.get("sequence", -1)) > _sequence:
		_sequence = int(command.sequence)
		_dispatch(command)


func _project_rows(values: Variant, fields: Array[String]) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not values is Array:
		return result
	for value: Variant in values:
		if not value is Dictionary:
			continue
		var row: Dictionary = {}
		for field: String in fields:
			row[field] = value.get(field)
		result.append(row)
	return result


func _capture_screen_wave() -> void:
	var rig := get_parent().get_node_or_null("OrbitCamera")
	if not is_instance_valid(rig) or not rig.has_method("screen_wave_snapshot"):
		return
	var value: Variant = rig.call("screen_wave_snapshot")
	if not value is Dictionary:
		return
	var wave: Dictionary = value
	var fingerprint := (
		JSON
		. stringify(
			[
				wave.get("active"),
				wave.get("fingerprint"),
				wave.get("sample_index"),
				wave.get("trigger_count"),
				wave.get("last_outcome"),
			]
		)
	)
	if fingerprint == _last_screen_wave_fingerprint:
		return
	_last_screen_wave_fingerprint = fingerprint
	var camera := rig.get_node_or_null("Camera3D")
	var camera_position: Array = []
	var base_position: Array = []
	if camera is Camera3D:
		camera_position = [camera.position.x, camera.position.y, camera.position.z]
		var yaw := float(rig.get("yaw"))
		var pitch := float(rig.get("pitch"))
		var distance := float(rig.get("distance"))
		var base := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
		base_position = [base.x, base.y, base.z]
	(
		_screen_wave_history
		. append(
			{
				"observed_at_ticks_ms": Time.get_ticks_msec(),
				"active": bool(wave.get("active", false)),
				"fingerprint": str(wave.get("fingerprint", "")),
				"action_id": str(wave.get("action_id", "")),
				"attack_sequence": int(wave.get("attack_sequence", -1)),
				"action_started_at_us": int(wave.get("action_started_at_us", 0)),
				"activation_us": int(wave.get("activation_us", 0)),
				"duration_us": int(wave.get("duration_us", 0)),
				"elapsed_us": int(wave.get("elapsed_us", 0)),
				"sample_index": int(wave.get("sample_index", -1)),
				"offset": wave.get("offset", []).duplicate(),
				"trigger_count": int(wave.get("trigger_count", 0)),
				"last_outcome": str(wave.get("last_outcome", "")),
				"policy": str(wave.get("policy", "")),
				"camera_local_position": camera_position,
				"base_camera_local_position": base_position,
			}
		)
	)
	while _screen_wave_history.size() > 128:
		_screen_wave_history.pop_front()
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2ScreenWaveHistory = JSON.stringify(
			_screen_wave_history
		)


func _web_command(args: Array) -> void:
	if args.size() == 1:
		var command: Variant = JSON.parse_string(str(args[0]))
		if command is Dictionary:
			_dispatch(command)


func _dispatch(command: Dictionary) -> void:
	var world := get_parent()
	var connection: GameConnection = world.connection
	match str(command.get("action", "")):
		"profile_performance":
			_profile_frames = 0
			_performance_profile = {}
			_profile_started_us = Time.get_ticks_usec()
		"login":
			world._account_flow._login(
				str(command.get("username", "")), str(command.get("password", ""))
			)
		"register":
			world._account_flow._register(
				str(command.get("username", "")),
				str(command.get("email", "")),
				str(command.get("password", ""))
			)
		"create":
			connection.create_character(int(command.get("slot", 0)), str(command.get("name", "")))
		"select":
			connection.select_character(str(command.get("character_id", "")))
		"enter":
			connection.enter_selected()
		"leave":
			world._account_flow.change_character()
		"logout":
			world._account_flow.logout()
		"connect":
			world._connect_game(
				world._settings.server_url,
				world._settings.database,
				str(command.get("name", "BrowserTest"))
			)
		"move":
			connection.set_move_input(float(command.get("x", 0)), float(command.get("z", 0)))
		"target":
			connection.move_to(float(command.get("x", 0)), float(command.get("z", 0)))
		"stop":
			connection.stop_moving()
		"pointer_move":
			_inject_pointer(command, false)
		"pointer_click":
			_inject_pointer(command, true)
		"pointer_right_click":
			_inject_pointer(command, true, MOUSE_BUTTON_RIGHT)
		"inventory":
			_inject_inventory()
		"space":
			_inject_space()
		"attack":
			connection.perform_attack()
		"disconnect":
			connection.disconnect_game()
		"reconnect":
			connection.reconnect_game()
		"capture":
			if not _report.is_empty():
				await RenderingServer.frame_post_draw
				get_viewport().get_texture().get_image().save_png(
					_report.get_base_dir().path_join("desktop.png")
				)


func _inject_pointer(
	command: Dictionary, click: bool, button_index: MouseButton = MOUSE_BUTTON_LEFT
) -> void:
	var x_value: Variant = command.get("x")
	var y_value: Variant = command.get("y")
	if not x_value is float and not x_value is int:
		_errors.append("Test pointer input requires a finite in-viewport point.")
		return
	if not y_value is float and not y_value is int:
		_errors.append("Test pointer input requires a finite in-viewport point.")
		return
	var point := Vector2(float(x_value), float(y_value))
	if not point.is_finite() or not get_viewport().get_visible_rect().has_point(point):
		_errors.append("Test pointer input requires a finite in-viewport point.")
		return
	# A pushed motion reaches input handlers but does not move the native OS cursor.
	# Keep the fixed native probe route aligned with production's periodic pointer poll.
	if not OS.has_feature("web"):
		get_viewport().warp_mouse(point)
	var motion := InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	get_viewport().push_input(motion, true)
	if not click:
		return
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = button_index
		event.pressed = pressed
		event.position = point
		event.global_position = point
		get_viewport().push_input(event, true)


func _inject_space() -> void:
	_inject_key(KEY_SPACE)


func _inject_inventory() -> void:
	_inject_key(KEY_I)


func _inject_key(keycode: Key) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.physical_keycode = keycode
		event.pressed = pressed
		get_viewport().push_input(event, true)


func _on_reducer_completed(
	reducer_name: String, succeeded: bool, reducer_timestamp_us: int
) -> void:
	if reducer_name not in ["perform_attack", "select_combat_target"]:
		return
	var world := get_parent()
	var connection: GameConnection = world.connection
	var record := {
		"succeeded": succeeded,
		"observed_at_ticks_ms": Time.get_ticks_msec(),
		"reducer_timestamp_us": reducer_timestamp_us,
		"server_time_us": connection.server_time_us,
		"public_action": _own_public_action(connection),
	}
	if reducer_name == "perform_attack":
		_attack_ack_sequence += 1
		record["sequence"] = _attack_ack_sequence
		_perform_attack_acks.append(record)
		while _perform_attack_acks.size() > 32:
			_perform_attack_acks.pop_front()
	else:
		_target_ack_sequence += 1
		record["sequence"] = _target_ack_sequence
		record["combat_target"] = connection.selected_combat_target()
		_select_combat_target_acks.append(record)
		while _select_combat_target_acks.size() > 32:
			_select_combat_target_acks.pop_front()
	_publish_ack_views()


func _on_players_changed(rows: Array) -> void:
	var players := get_parent().get_node_or_null("Players")
	for value: Variant in rows:
		if not value is Dictionary:
			continue
		var player: Dictionary = value
		var identity := str(player.get("identity", ""))
		if identity.is_empty():
			continue
		var public_action := _public_action(player)
		var fingerprint := JSON.stringify(public_action)
		if str(_last_public_actions.get(identity, "")) == fingerprint:
			continue
		_last_public_actions[identity] = fingerprint
		var actor: Node3D
		if is_instance_valid(players):
			for candidate: Node in players.get_children():
				if candidate is Node3D and str(candidate.get("identity")) == identity:
					actor = candidate
					break
		var rendered_position: Array = []
		var presentation: Dictionary = {}
		if is_instance_valid(actor):
			rendered_position = [actor.position.x, actor.position.y, actor.position.z]
			if actor.has_method("presentation_snapshot"):
				var snapshot: Variant = actor.call("presentation_snapshot")
				if snapshot is Dictionary:
					presentation = snapshot
		(
			_public_action_history
			. append(
				{
					"identity": identity,
					"observed_at_ticks_ms": Time.get_ticks_msec(),
					"server_time_us": get_parent().connection.server_time_us,
					"public_action": public_action,
					"rendered_position": rendered_position,
					"presentation": _project_presentation(presentation),
				}
			)
		)
		while _public_action_history.size() > 256:
			_public_action_history.pop_front()
	_publish_own_action_view()


func _on_reducer_failed(message: String) -> void:
	_errors.append(message)
	_publish_error_view()


func _on_monsters_changed(rows: Array) -> void:
	var present: Dictionary = {}
	var changed := false
	for value: Variant in rows:
		if not value is Dictionary:
			continue
		var monster: Dictionary = value
		var row_id := int(monster.get("id", 0))
		if row_id <= 0:
			continue
		present[row_id] = true
		_capture_monster_action(monster)
		var fingerprint := JSON.stringify([monster.get("life_sequence"), monster.get("health")])
		if str(_last_monster_health.get(row_id, "")) == fingerprint:
			continue
		_last_monster_health[row_id] = fingerprint
		(
			_monster_health_history
			. append(
				{
					"id": row_id,
					"life_sequence": monster.get("life_sequence"),
					"health": monster.get("health"),
					"observed_at_ticks_ms": Time.get_ticks_msec(),
				}
			)
		)
		changed = true
	while _monster_health_history.size() > 128:
		_monster_health_history.pop_front()
	for row_id: Variant in _last_monster_health.keys():
		if not present.has(row_id):
			_last_monster_health.erase(row_id)
			_last_monster_actions.erase(row_id)
	if changed:
		_publish_monster_health_view()


func _capture_monster_action(monster: Dictionary) -> void:
	var row_id := int(monster.get("id", 0))
	var fingerprint := (
		JSON
		. stringify(
			[
				monster.get("life_sequence"),
				monster.get("health"),
				monster.get("activity"),
				monster.get("attack_action_id"),
				monster.get("attack_sequence"),
				monster.get("action_started_at_us"),
				monster.get("action_ends_at_us"),
				monster.get("x"),
				monster.get("y"),
				monster.get("z"),
			]
		)
	)
	if str(_last_monster_actions.get(row_id, "")) == fingerprint:
		return
	_last_monster_actions[row_id] = fingerprint
	(
		_monster_action_history
		. append(
			{
				"observed_at_ticks_ms": Time.get_ticks_msec(),
				"id": row_id,
				"life_sequence": monster.get("life_sequence"),
				"health": monster.get("health"),
				"activity": monster.get("activity"),
				"attack_action_id": monster.get("attack_action_id"),
				"attack_sequence": monster.get("attack_sequence"),
				"action_started_at_us": monster.get("action_started_at_us"),
				"action_ends_at_us": monster.get("action_ends_at_us"),
				"x": monster.get("x"),
				"y": monster.get("y"),
				"z": monster.get("z"),
			}
		)
	)
	while _monster_action_history.size() > 256:
		_monster_action_history.pop_front()
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2MonsterActionHistory = JSON.stringify(
			_monster_action_history
		)


func _on_connection_state_changed(_state: String, _message: String) -> void:
	_last_public_actions.clear()
	_last_own_action_fingerprint = ""
	_last_monster_health.clear()
	_last_monster_actions.clear()
	_publish_own_action_view()


func _own_public_action(connection: GameConnection) -> Dictionary:
	var player: Dictionary = {}
	for row: Dictionary in connection.players:
		if str(row.get("identity", "")) == connection.local_identity:
			player = row
			break
	return _public_action(player)


func _public_action(player: Dictionary) -> Dictionary:
	return {
		"activity": player.get("activity"),
		"attack_action_id": player.get("attack_action_id"),
		"attack_sequence": player.get("attack_sequence"),
		"action_started_at_us": player.get("action_started_at_us"),
		"action_ends_at_us": player.get("action_ends_at_us"),
		"x": player.get("x"),
		"y": player.get("y"),
		"z": player.get("z"),
		"heading": player.get("heading"),
	}


func _project_presentation(value: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for field: String in [
		"action_id",
		"sequence",
		"attack_sequence",
		"server_position",
		"presentation_local_position",
		"model_local_position",
	]:
		result[field] = value.get(field)
	return result


func _publish_ack_views() -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2AttackAcks = JSON.stringify(
			_perform_attack_acks
		)
		JavaScriptBridge.get_interface("window").mt2SelectTargetAcks = JSON.stringify(
			_select_combat_target_acks
		)
	else:
		# The native runner reads the same full snapshot, but ACK evidence must not
		# wait for the ordinary 200 ms reporting cadence.
		_elapsed = 0.2


func _publish_error_view() -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2ProbeErrors = JSON.stringify(_errors)
	else:
		_elapsed = 0.2


func _publish_own_action_view() -> void:
	var action := _own_public_action(get_parent().connection)
	var fingerprint := (
		JSON
		. stringify(
			[
				action.get("activity"),
				action.get("attack_action_id"),
				action.get("attack_sequence"),
				action.get("action_started_at_us"),
				action.get("action_ends_at_us"),
			]
		)
	)
	if fingerprint == _last_own_action_fingerprint:
		return
	_last_own_action_fingerprint = fingerprint
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2OwnPublicAction = JSON.stringify(action)
	else:
		# Native action transitions schedule one prompt full snapshot; position-only
		# root ticks retain the ordinary 200 ms reporting cadence.
		_elapsed = 0.2


func _publish_monster_health_view() -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2MonsterHealthHistory = JSON.stringify(
			_monster_health_history
		)
	else:
		# Public health changes schedule one prompt full snapshot so a later action
		# cannot erase the intermediate subscribed value from exported QA evidence.
		_elapsed = 0.2
