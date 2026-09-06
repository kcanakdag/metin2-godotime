extends Node
## Queues synthetic input events for the running game/editor.

const QUEUE_FILE := "mcp_input_queue.json"

var _last_mouse_position := Vector2.ZERO
var _has_mouse_position := false


func _ready() -> void:
	if DisplayServer.get_name() == "headless" or not OS.is_debug_build():
		set_process(false)


func queue_events(events: Array) -> void:
	var path := OS.get_user_data_dir().path_join(QUEUE_FILE)
	var existing: Array = []
	if FileAccess.file_exists(path):
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Array:
			existing = parsed
	existing.append_array(events)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(existing))
		file.close()


func _process(_delta: float) -> void:
	if Engine.is_editor_hint() or not OS.is_debug_build():
		return
	_consume_batches()
	var path := OS.get_user_data_dir().path_join(QUEUE_FILE)
	if not FileAccess.file_exists(path):
		return
	var events = JSON.parse_string(FileAccess.get_file_as_string(path))
	DirAccess.remove_absolute(path)
	if not events is Array:
		return
	for ev in events:
		_apply(ev)


func _consume_batches() -> void:
	var directory := OS.get_user_data_dir().path_join("mcp_input_batches")
	if not DirAccess.dir_exists_absolute(directory):
		return
	var files := DirAccess.get_files_at(directory)
	files.sort()
	for filename in files:
		if not filename.ends_with(".json"):
			continue
		var path := directory.path_join(filename)
		var events: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		DirAccess.remove_absolute(path)
		if events is Array:
			for event in events:
				_apply(event)


func _apply(ev: Dictionary) -> void:
	match ev.get("type", ""):
		"key":
			var e := InputEventKey.new()
			e.keycode = int(ev.get("keycode", 0))
			e.physical_keycode = int(ev.get("physical_keycode", ev.get("keycode", 0)))
			e.pressed = ev.get("pressed", true)
			Input.parse_input_event(e)
		"mouse_click":
			var e := InputEventMouseButton.new()
			e.position = Vector2(ev.get("x", 0), ev.get("y", 0))
			e.button_index = int(ev.get("button", MOUSE_BUTTON_LEFT))
			e.pressed = ev.get("pressed", true)
			Input.parse_input_event(e)
			if not ev.has("pressed"):
				# Input may queue the original RefCounted event until the next frame.
				# Mutating it would erase its press before the game receives it.
				var release := e.duplicate() as InputEventMouseButton
				release.pressed = false
				Input.parse_input_event(release)
		"mouse_move":
			var e := InputEventMouseMotion.new()
			e.position = Vector2(ev.get("x", 0), ev.get("y", 0))
			var previous := _last_mouse_position if _has_mouse_position else get_viewport().get_mouse_position()
			e.relative = e.position - previous
			e.button_mask = Input.get_mouse_button_mask()
			_last_mouse_position = e.position
			_has_mouse_position = true
			Input.parse_input_event(e)
		"action":
			if ev.get("pressed", true):
				Input.action_press(str(ev.get("action", "")))
			else:
				Input.action_release(str(ev.get("action", "")))
