extends Node
## Opt-in release-build evidence capture. No listener, evaluator or identity-token access.

const SETTLE_MS := 3000
const TIMEOUT_MS := 30000

var _world: Node
var _report_path := ""
var _capture_path := ""
var _quit_after := false
var _enabled := false
var _finished := false
var _started_msec := 0
var _connected_msec := -1


func configure(world: Node) -> void:
	_world = world
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		var argument := args[index]
		if argument == "--dev-quit":
			_quit_after = true
		elif argument in ["--dev-report", "--dev-capture"] and index + 1 < args.size():
			index += 1
			if argument == "--dev-report":
				_report_path = _absolute_path(args[index])
			else:
				_capture_path = _absolute_path(args[index])
		index += 1
	_enabled = _quit_after or not _report_path.is_empty() or not _capture_path.is_empty()
	_started_msec = Time.get_ticks_msec()
	if not _enabled:
		queue_free()


func _process(_delta: float) -> void:
	if not _enabled or _finished:
		return
	var snapshot: Dictionary = _world.call("dev_snapshot")
	var state := str(snapshot.get("connection_state", "disconnected"))
	var now := Time.get_ticks_msec()
	if state == "connected":
		if _connected_msec < 0:
			_connected_msec = now
		if now - _connected_msec >= SETTLE_MS:
			_finish("connected", "")
	else:
		_connected_msec = -1
		if state == "error":
			_finish(
				"error", "The client could not connect; inspect the captured connection screen."
			)
	if not _finished and now - _started_msec >= TIMEOUT_MS:
		_finish("timeout", "The client did not reach a stable connection within 30 seconds.")


func _finish(status: String, message: String) -> void:
	_finished = true
	var failures: Array[String] = []
	if not message.is_empty():
		failures.append(message)
	if not _capture_path.is_empty():
		if DisplayServer.get_name() == "headless":
			failures.append("Viewport capture needs a graphical display.")
		else:
			await RenderingServer.frame_post_draw
			_prepare_directory(_capture_path)
			var screenshot := get_viewport().get_texture().get_image()
			var capture_error := screenshot.save_png(_capture_path)
			if capture_error != OK:
				failures.append("Screenshot failed: " + error_string(capture_error))
	var snapshot: Dictionary = _world.call("dev_snapshot")
	var report := {
		"status": status if failures.is_empty() else "error",
		"errors": failures,
		"captured_at": Time.get_datetime_string_from_system(true),
		"engine": Engine.get_version_info().string,
		"platform": OS.get_name(),
		"export_template": OS.has_feature("template"),
		"screenshot": _capture_path,
		"snapshot": snapshot,
	}
	if not _report_path.is_empty():
		_prepare_directory(_report_path)
		var file := FileAccess.open(_report_path, FileAccess.WRITE)
		if file:
			file.store_string(JSON.stringify(report, "  ") + "\n")
			file.close()
		else:
			failures.append("Unable to write the requested report file.")
	print(
		(
			"DEV_CAPTURE_RESULT "
			+ (
				JSON
				. stringify(
					{
						"status": report.status if failures.is_empty() else "error",
						"report": _report_path,
						"screenshot": _capture_path,
						"players": snapshot.get("players", 0),
						"errors": failures,
					}
				)
			)
		)
	)
	if _quit_after:
		get_tree().quit(0 if failures.is_empty() else 1)


func _absolute_path(path: String) -> String:
	if path.is_absolute_path() or path.begins_with("user://"):
		return path
	return OS.get_executable_path().get_base_dir().path_join(path)


func _prepare_directory(path: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
