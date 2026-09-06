extends Node
## Export-test instrumentation. The release staging tool excludes this file by default.
## Exposes snapshots and a fixed list of ordinary validated client actions, never eval/tokens.

var _elapsed := 0.0
var _callback: JavaScriptObject
var _report := ""
var _commands := ""
var _sequence := -1
var _errors: Array[String] = []


func _ready() -> void:
	get_parent().connection.reducer_failed.connect(func(message: String): _errors.append(message))
	if OS.has_feature("web"):
		_callback = JavaScriptBridge.create_callback(_web_command)
		JavaScriptBridge.get_interface("window").mt2Command = _callback
	else:
		var args := OS.get_cmdline_user_args()
		for i in range(args.size() - 1):
			if args[i] == "--probe-report":
				_report = args[i + 1]
			if args[i] == "--probe-commands":
				_commands = args[i + 1]


func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < 0.2:
		return
	_elapsed = 0
	var snapshot: Dictionary = get_parent().dev_snapshot()
	snapshot["errors"] = _errors
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
	var payload := JSON.stringify(snapshot)
	if OS.has_feature("web"):
		JavaScriptBridge.get_interface("window").mt2Snapshot = payload
	elif not _report.is_empty():
		var file := FileAccess.open(_report, FileAccess.WRITE)
		if file:
			file.store_string(payload)
			file.close()
	if not _commands.is_empty() and FileAccess.file_exists(_commands):
		var command: Variant = JSON.parse_string(FileAccess.get_file_as_string(_commands))
		if command is Dictionary and int(command.get("sequence", -1)) > _sequence:
			_sequence = int(command.sequence)
			_dispatch(command)


func _web_command(args: Array) -> void:
	if args.size() == 1:
		var command: Variant = JSON.parse_string(str(args[0]))
		if command is Dictionary:
			_dispatch(command)


func _dispatch(command: Dictionary) -> void:
	var world := get_parent()
	var connection: GameConnection = world.connection
	match str(command.get("action", "")):
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
