@tool
extends "res://addons/godot_mcp/commands/base_commands.gd"

const MAIN_RUN_ARGS_KEY := "editor/run/main_run_args"
const SAVE_BEFORE_RUNNING_KEY := "run/auto_save/save_before_running"
const MAX_USER_ARGS_LENGTH := 4096
const LAUNCH_WAIT_FRAMES := 120

var _launch_in_progress := false
var _active_launch_settings: Dictionary = {}
var _active_editor_settings: EditorSettings

func get_commands() -> Dictionary:
	return {
		"get_scene_tree": _get_scene_tree,
		"get_scene_file_content": _get_scene_file_content,
		"open_scene": _open_scene,
		"save_scene": _save_scene,
		"create_scene": _create_scene,
		"play_scene": _play_scene,
		"stop_scene": _stop_scene,
		"delete_scene": _delete_scene,
		"add_scene_instance": _add_scene_instance,
		"get_scene_exports": _get_scene_exports,
	}


func _get_scene_tree(_params: Dictionary) -> Dictionary:
	var root := _edited_root()
	if root == null:
		return _ok({"scene": null, "message": "No scene is currently open"})
	return _ok({
		"scene_path": root.scene_file_path,
		"root": _node_to_dict(root),
	})


func _get_scene_file_content(params: Dictionary) -> Dictionary:
	var scene_path: String = params.get("scene_path", "")
	if scene_path.is_empty():
		var root := _edited_root()
		if root == null:
			return _err("No scene open and no scene_path provided")
		scene_path = root.scene_file_path
	if not scene_path.begins_with("res://"):
		scene_path = "res://" + scene_path.trim_prefix("/")
	if not FileAccess.file_exists(scene_path):
		return _err("Scene file not found: %s" % scene_path, -32001)
	return _ok({"scene_path": scene_path, "content": FileAccess.get_file_as_string(scene_path)})


func _open_scene(params: Dictionary) -> Dictionary:
	var scene_path: String = params.get("scene_path", "")
	if scene_path.is_empty():
		return _err("Missing 'scene_path'")
	if not scene_path.begins_with("res://"):
		scene_path = "res://" + scene_path.trim_prefix("/")
	if not FileAccess.file_exists(scene_path):
		return _err("Scene file not found: %s" % scene_path, -32001)
	editor_plugin.get_editor_interface().open_scene_from_path(scene_path)
	return _ok({"scene_path": scene_path, "opened": true})


func _save_scene(_params: Dictionary) -> Dictionary:
	var root := _edited_root()
	if root == null:
		return _err("No scene is open")
	var path := root.scene_file_path
	if path.is_empty():
		return _err("Scene has no file path — save manually first or use create_scene")
	editor_plugin.get_editor_interface().save_scene()
	return _ok({"scene_path": path, "saved": true})


func _create_scene(params: Dictionary) -> Dictionary:
	var scene_path: String = params.get("scene_path", "")
	var root_type: String = params.get("root_type", "Node2D")
	if scene_path.is_empty():
		return _err("Missing 'scene_path'")
	if not scene_path.begins_with("res://"):
		scene_path = "res://" + scene_path.trim_prefix("/")
	if FileAccess.file_exists(scene_path) and not params.get("overwrite", false):
		return _err(
			"Scene already exists: %s" % scene_path,
			-32002,
			{"suggestion": "Set overwrite=true to replace"}
		)

	if not ClassDB.class_exists(root_type):
		return _err("Unknown node type: %s" % root_type)

	var root: Node = ClassDB.instantiate(root_type)
	root.name = scene_path.get_file().get_basename()
	var packed := PackedScene.new()
	packed.pack(root)
	var err := ResourceSaver.save(packed, scene_path)
	root.free()
	if err != OK:
		return _err("Failed to create scene: error %d" % err)
	editor_plugin.get_editor_interface().open_scene_from_path(scene_path)
	return _ok({"scene_path": scene_path, "root_type": root_type, "created": true})


func _play_scene(params: Dictionary) -> Dictionary:
	var editor := editor_plugin.get_editor_interface()
	if _launch_in_progress:
		return _err("A scene launch is already in progress; wait for it to finish", -32012)
	if editor.is_playing_scene():
		return _err("A scene is already running; stop it before starting another one", -32012)

	var request := _validate_play_request(params)
	if not request.get("valid", false):
		return _err(request.get("error", "Invalid play request"), -32013)

	var editor_settings := editor.get_editor_settings()
	var transient_state := _capture_launch_settings(editor_settings, request["has_user_args"])
	_launch_in_progress = true
	_active_launch_settings = transient_state
	_active_editor_settings = editor_settings
	_apply_launch_settings(editor_settings, transient_state, request.get("user_args", ""))
	# Run Instances mirrors ProjectSettings into its argument field through the
	# settings_changed signal. Let that editor-side update happen before the run
	# bar reads the field to start the child process.
	await editor_plugin.get_tree().process_frame
	if editor.is_playing_scene():
		_restore_active_launch_settings()
		return _err("A scene started while this launch was being prepared", -32012)

	match request["mode"]:
		"main":
			editor.play_main_scene()
		"current":
			editor.play_current_scene()
		"custom":
			editor.play_custom_scene(request["scene_path"])

	# Godot's play_* methods have no completion result. Wait for the editor to
	# register the running scene, then restore on the following editor frame.
	# This keeps the launch arguments live until the launch has consumed them.
	var launch_observed := await _wait_for_launch(editor)
	_restore_active_launch_settings()
	if not launch_observed:
		return _err("Editor did not start the requested scene; transient settings were restored", -32014)
	return _ok({
		"playing": true,
		"mode": request["mode"],
		"transient_user_args": request["has_user_args"],
		"settings_saved": false,
		"scene_saved": false,
	})


func _validate_play_request(params: Dictionary) -> Dictionary:
	var mode_value: Variant = params.get("mode", "current")
	if not mode_value is String or mode_value not in ["main", "current", "custom"]:
		return {"valid": false, "error": "mode must be main, current, or custom"}
	var mode: String = mode_value
	var mode_error := _play_mode_error(mode)
	if not mode_error.is_empty():
		return {"valid": false, "error": mode_error}

	var request := {"valid": true, "mode": mode, "has_user_args": params.has("user_args")}
	var user_args := _validated_user_args(params)
	if not user_args["valid"]:
		return user_args
	if request["has_user_args"]:
		request["user_args"] = user_args["value"]
	if mode == "custom":
		var custom_scene := _validated_custom_scene(params)
		if not custom_scene["valid"]:
			return custom_scene
		request["scene_path"] = custom_scene["path"]
	return request


func _play_mode_error(mode: String) -> String:
	if mode == "current":
		var current_scene := _edited_root()
		if current_scene == null:
			return "No current scene is open"
		if current_scene.scene_file_path.is_empty():
			return "Current scene must be saved before it can be played"
		if not FileAccess.file_exists(current_scene.scene_file_path):
			return "Current scene file is missing"
	if mode == "main":
		var main_scene: String = ProjectSettings.get_setting("application/run/main_scene", "")
		if main_scene.is_empty() or not ResourceLoader.exists(main_scene, "PackedScene"):
			return "Configured main scene is missing"
	return ""


func _validated_user_args(params: Dictionary) -> Dictionary:
	if not params.has("user_args"):
		return {"valid": true}
	if not params["user_args"] is String:
		return {"valid": false, "error": "user_args must be a string"}
	var user_args: String = params["user_args"]
	if user_args.length() > MAX_USER_ARGS_LENGTH or _contains_nul(user_args):
		return {"valid": false, "error": "user_args is too long or contains a NUL byte"}
	return {"valid": true, "value": user_args}


func _validated_custom_scene(params: Dictionary) -> Dictionary:
	if not params.has("scene_path") or not params["scene_path"] is String:
		return {"valid": false, "error": "Custom play mode requires scene_path"}
	var scene_path := _norm_res(params["scene_path"])
	if scene_path.is_empty() or not FileAccess.file_exists(scene_path):
		return {"valid": false, "error": "Custom scene file is missing"}
	if scene_path.get_extension() not in ["tscn", "scn"]:
		return {"valid": false, "error": "Custom scene_path must name a scene file"}
	return {"valid": true, "path": scene_path}


func _contains_nul(text: String) -> bool:
	for index in text.length():
		if text.unicode_at(index) == 0:
			return true
	return false


func _capture_launch_settings(editor_settings: EditorSettings, replace_args: bool) -> Dictionary:
	return {
		"replace_args": replace_args,
		"args_present": ProjectSettings.has_setting(MAIN_RUN_ARGS_KEY),
		"args_value": ProjectSettings.get_setting(MAIN_RUN_ARGS_KEY, ""),
		"save_before_present": editor_settings.has_setting(SAVE_BEFORE_RUNNING_KEY),
		"save_before_value": editor_settings.get_setting(SAVE_BEFORE_RUNNING_KEY)
		if editor_settings.has_setting(SAVE_BEFORE_RUNNING_KEY)
		else true,
	}


func _apply_launch_settings(
	editor_settings: EditorSettings, transient_state: Dictionary, user_args: String
) -> void:
	if transient_state["replace_args"]:
		ProjectSettings.set_setting(MAIN_RUN_ARGS_KEY, user_args)
	editor_settings.set_setting(SAVE_BEFORE_RUNNING_KEY, false)


func _restore_launch_settings(editor_settings: EditorSettings, transient_state: Dictionary) -> void:
	if transient_state["replace_args"]:
		if transient_state["args_present"]:
			ProjectSettings.set_setting(MAIN_RUN_ARGS_KEY, transient_state["args_value"])
		else:
			ProjectSettings.set_setting(MAIN_RUN_ARGS_KEY, null)
	if transient_state["save_before_present"]:
		editor_settings.set_setting(SAVE_BEFORE_RUNNING_KEY, transient_state["save_before_value"])
	else:
		editor_settings.erase(SAVE_BEFORE_RUNNING_KEY)


func _restore_active_launch_settings() -> void:
	if not _launch_in_progress:
		return
	_restore_launch_settings(_active_editor_settings, _active_launch_settings)
	_active_launch_settings = {}
	_active_editor_settings = null
	_launch_in_progress = false


func _wait_for_launch(editor: EditorInterface) -> bool:
	for _frame in LAUNCH_WAIT_FRAMES:
		await editor_plugin.get_tree().process_frame
		if editor.is_playing_scene():
			await editor_plugin.get_tree().process_frame
			return true
	return false


func _exit_tree() -> void:
	# A plugin reload or editor shutdown can free this command while its await is
	# pending. Restore synchronously because the deferred command will not resume.
	_restore_active_launch_settings()


func _stop_scene(_params: Dictionary) -> Dictionary:
	editor_plugin.get_editor_interface().stop_playing_scene()
	return _ok({"playing": false})


func _delete_scene(params: Dictionary) -> Dictionary:
	var scene_path := _norm_res(params.get("scene_path", ""))
	if scene_path.is_empty():
		return _err("Missing scene_path")
	if not FileAccess.file_exists(scene_path):
		return _err("Scene not found: %s" % scene_path)
	var err := DirAccess.remove_absolute(ProjectSettings.globalize_path(scene_path))
	if err != OK:
		return _err("Failed to delete scene")
	editor_plugin.get_editor_interface().get_resource_filesystem().scan()
	return _ok({"deleted": scene_path})


func _add_scene_instance(params: Dictionary) -> Dictionary:
	var scene_path := _norm_res(params.get("scene_path", ""))
	var parent_path: String = params.get("parent_path", ".")
	var instance_name: String = params.get("name", "")
	if scene_path.is_empty():
		return _err("Missing scene_path")
	var packed: PackedScene = load(scene_path)
	if packed == null:
		return _err("Failed to load scene: %s" % scene_path)
	var parent := _resolve_node(parent_path)
	if parent == null:
		return _err("Parent not found")
	var inst := packed.instantiate()
	if not instance_name.is_empty():
		inst.name = instance_name
	var root := _edited_root()
	editor_plugin.get_undo_redo().create_action("MCP Instance Scene")
	editor_plugin.get_undo_redo().add_do_method(parent, "add_child", inst, true)
	editor_plugin.get_undo_redo().add_do_method(inst, "set_owner", root)
	editor_plugin.get_undo_redo().add_undo_method(parent, "remove_child", inst)
	editor_plugin.get_undo_redo().commit_action()
	return _ok({"path": str(inst.get_path()), "scene": scene_path})


func _get_scene_exports(p: Dictionary) -> Dictionary:
	var path := _norm_res(p.get("path", p.get("scene_path", "")))
	if path.is_empty() and _edited_root():
		path = _edited_root().scene_file_path
	if path.is_empty():
		return _err("Missing scene path")
	if not FileAccess.file_exists(path):
		return _err("Scene not found: %s" % path)
	var packed: PackedScene = load(path)
	if packed == null:
		return _err("Failed to load scene")
	var instance := packed.instantiate()
	var nodes_data: Array = []
	_collect_exports(instance, instance, nodes_data)
	instance.free()
	return _ok({"path": path, "nodes": nodes_data, "count": nodes_data.size()})


func _collect_exports(node: Node, root: Node, out: Array) -> void:
	var script: Script = node.get_script()
	if script:
		var exports := {}
		for info in script.get_script_property_list():
			if (info.usage & PROPERTY_USAGE_EDITOR) and (info.usage & PROPERTY_USAGE_SCRIPT_VARIABLE):
				exports[info.name] = _serialize_value(node.get(info.name))
		if not exports.is_empty():
			out.append({
				"node_path": "." if node == root else str(root.get_path_to(node)),
				"node_name": node.name,
				"node_type": node.get_class(),
				"script_path": script.resource_path,
				"exports": exports,
			})
	for child in node.get_children():
		_collect_exports(child, root, out)
