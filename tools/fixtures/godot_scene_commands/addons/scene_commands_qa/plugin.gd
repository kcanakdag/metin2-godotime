@tool
extends EditorPlugin

const SceneCommands = preload("res://addons/godot_mcp/commands/scene_commands.gd")
const RUN_ARGS := "-- --profile scene-command-qa"
const ORIGINAL_ARGS := "-- --profile prior-value"
const REPORT_PATH := "user://scene-command-qa-report.json"
const ARGS_PATH := "user://scene-command-qa-args.json"

var _failures: Array[String] = []
var _assertions := 0
var _child_args: Variant = null


class PendingSceneCommands:
	extends "res://addons/godot_mcp/commands/scene_commands.gd"

	func _wait_for_launch(_editor: EditorInterface) -> bool:
		await get_tree().create_timer(5.0).timeout
		return false


class TimedOutSceneCommands:
	extends "res://addons/godot_mcp/commands/scene_commands.gd"

	func _wait_for_launch(_editor: EditorInterface) -> bool:
		return false


func _enter_tree() -> void:
	call_deferred("_run")


func _run() -> void:
	var settings := get_editor_interface().get_editor_settings()
	var original := _setting_state(settings)
	ProjectSettings.set_setting("editor/run/main_run_args", ORIGINAL_ARGS)
	settings.set_setting("run/auto_save/save_before_running", true)
	var commands: Node = SceneCommands.new()
	commands.editor_plugin = self
	add_child(commands)
	_assert_validation_rejects_without_mutation(commands, settings)
	await _assert_actual_launch_and_restore(commands, settings)
	await _assert_timeout_restore(settings)
	await _assert_pending_restore(settings)
	_assert_absent_settings_restore(commands, settings)
	var after_tests := _setting_state(settings)
	_assert(
		after_tests.args == ORIGINAL_ARGS and after_tests.save_before_running == true,
		"final test state was not restored"
	)
	_restore_original_settings(settings, original)
	_write_report(
		{"before": original, "after_tests": after_tests, "after_restore": _setting_state(settings)}
	)
	get_tree().quit(0 if _failures.is_empty() else 1)


func _assert_validation_rejects_without_mutation(commands: Node, settings: EditorSettings) -> void:
	var baseline := _setting_state(settings)
	var requests := [
		{"mode": "unsupported", "user_args": RUN_ARGS},
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": 42},
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": "x".repeat(4097)},
		{"mode": "custom", "scene_path": "res://missing.tscn", "user_args": RUN_ARGS},
	]
	for request in requests:
		var result: Dictionary = commands._validate_play_request(request)
		_assert(not result.get("valid", false), "invalid request was accepted: %s" % request)
		_assert(_setting_state(settings) == baseline, "invalid request changed settings")
	var prior_main := ProjectSettings.get_setting("application/run/main_scene", "")
	var main_id := ResourceUID.create_id_for_path("res://qa_scene.tscn")
	ResourceUID.add_id(main_id, "res://qa_scene.tscn")
	var main_uid := ResourceUID.id_to_text(main_id)
	ProjectSettings.set_setting("application/run/main_scene", main_uid)
	var uid_main: Dictionary = commands._validate_play_request({"mode": "main"})
	_assert(uid_main.get("valid", false), "uid main scene failed validation: %s" % uid_main)
	ProjectSettings.set_setting("application/run/main_scene", prior_main)
	var valid: Dictionary = commands._validate_play_request(
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": RUN_ARGS}
	)
	_assert(valid.get("valid", false), "ordinary user_args failed validation: %s" % valid)
	_assert(_setting_state(settings) == baseline, "valid request changed settings before launch")


func _assert_actual_launch_and_restore(commands: Node, settings: EditorSettings) -> void:
	_remove_file(ARGS_PATH)
	var result: Dictionary = await commands._play_scene(
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": RUN_ARGS}
	)
	_assert(not result.has("error"), "actual custom launch failed: %s" % result)
	_assert(
		(
			_setting_state(settings).args == ORIGINAL_ARGS
			and _setting_state(settings).save_before_running == true
		),
		"actual launch did not restore settings"
	)
	var elapsed := 0.0
	while not FileAccess.file_exists(ARGS_PATH) and elapsed < 2.0:
		await get_tree().create_timer(0.05).timeout
		elapsed += 0.05
	_assert(FileAccess.file_exists(ARGS_PATH), "child scene did not record user args")
	if FileAccess.file_exists(ARGS_PATH):
		_child_args = JSON.parse_string(FileAccess.get_file_as_string(ARGS_PATH))
		_assert(
			_child_args == ["--profile", "scene-command-qa"],
			"child received wrong user args: %s" % [_child_args]
		)
	get_editor_interface().stop_playing_scene()
	await get_tree().process_frame


func _assert_timeout_restore(settings: EditorSettings) -> void:
	var timed_out: Node = TimedOutSceneCommands.new()
	timed_out.editor_plugin = self
	add_child(timed_out)
	var result: Dictionary = await timed_out._play_scene(
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": RUN_ARGS}
	)
	_assert(result.get("error", {}).get("code", 0) == -32014, "launch timeout was not reported")
	_assert(
		(
			_setting_state(settings).args == ORIGINAL_ARGS
			and _setting_state(settings).save_before_running == true
		),
		"launch timeout did not restore settings"
	)
	get_editor_interface().stop_playing_scene()
	timed_out.queue_free()


func _assert_pending_restore(settings: EditorSettings) -> void:
	var pending: Node = PendingSceneCommands.new()
	pending.editor_plugin = self
	add_child(pending)
	pending._play_scene(
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": RUN_ARGS}
	)
	await get_tree().process_frame
	var concurrent: Dictionary = await pending._play_scene(
		{"mode": "custom", "scene_path": "res://qa_scene.tscn", "user_args": RUN_ARGS}
	)
	_assert(
		concurrent.get("error", {}).get("code", 0) == -32012, "concurrent launch was not rejected"
	)
	pending.queue_free()
	await get_tree().process_frame
	_assert(
		(
			_setting_state(settings).args == ORIGINAL_ARGS
			and _setting_state(settings).save_before_running == true
		),
		"pending teardown did not restore settings"
	)
	get_editor_interface().stop_playing_scene()


func _assert_absent_settings_restore(commands: Node, settings: EditorSettings) -> void:
	ProjectSettings.set_setting("editor/run/main_run_args", null)
	settings.erase("run/auto_save/save_before_running")
	_assert(
		not ProjectSettings.has_setting("editor/run/main_run_args")
		and not settings.has_setting("run/auto_save/save_before_running"),
		"fixture could not establish absent settings"
	)
	var transient_state: Dictionary = commands._capture_launch_settings(settings, true)
	commands._apply_launch_settings(settings, transient_state, RUN_ARGS)
	commands._restore_launch_settings(settings, transient_state)
	_assert(
		not ProjectSettings.has_setting("editor/run/main_run_args")
		and not settings.has_setting("run/auto_save/save_before_running"),
		"absent settings were not restored as absent"
	)
	ProjectSettings.set_setting("editor/run/main_run_args", ORIGINAL_ARGS)
	settings.set_setting("run/auto_save/save_before_running", true)


func _setting_state(settings: EditorSettings) -> Dictionary:
	return {
		"args": ProjectSettings.get_setting("editor/run/main_run_args", ""),
		"save_before_running": settings.get_setting("run/auto_save/save_before_running")
	}


func _restore_original_settings(settings: EditorSettings, state: Dictionary) -> void:
	ProjectSettings.set_setting("editor/run/main_run_args", state.args)
	settings.set_setting("run/auto_save/save_before_running", state.save_before_running)


func _assert(condition: bool, message: String) -> void:
	_assertions += 1
	if not condition:
		_failures.append(message)


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))


func _write_report(states: Dictionary) -> void:
	var file := FileAccess.open(REPORT_PATH, FileAccess.WRITE)
	file.store_string(
		JSON.stringify(
			{
				"assertions": _assertions,
				"child_args": _child_args,
				"states": states,
				"failures": _failures
			},
			"\t"
		)
	)
	file.close()
