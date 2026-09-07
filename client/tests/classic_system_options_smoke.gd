extends SceneTree
## Classic System Options screen-wave accessibility control checks.

const SystemOptions = preload("res://scripts/ui/classic_system_options.gd")

var _checks := 0
var _failed := false
var _changes: Array[bool] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var options := SystemOptions.new()
	root.add_child(options)
	options.screen_wave_changed.connect(func(value: bool) -> void: _changes.append(value))
	await process_frame
	var initial := options.snapshot()
	_check(
		not initial.visible and initial.screen_wave_enabled,
		"the normal System Options control defaults screen wave on while closed"
	)
	_check(
		(
			options._screen_wave_button.texture_normal != null
			and options._screen_wave_button.texture_hover != null
			and options._screen_wave_button.texture_pressed != null
		),
		"the accessibility control uses the imported original button states"
	)
	options.show()
	await process_frame
	var shown := options.snapshot()
	var center := Vector2(float(shown.screen_wave_center[0]), float(shown.screen_wave_center[1]))
	_check(
		shown.visible and Rect2(Vector2.ZERO, Vector2(root.size)).has_point(center),
		"the classic System Options control exposes a finite visible click point"
	)
	options.set_screen_wave_enabled(false)
	_check(
		(
			not options.snapshot().screen_wave_enabled
			and "Disabled" in options._screen_wave_caption.text
			and _changes.is_empty()
		),
		"restoring a persistent disabled setting updates the control without emitting"
	)
	await _click(center)
	_check(
		(
			options.snapshot().screen_wave_enabled
			and _changes == [true]
			and "Enabled" in options._screen_wave_caption.text
			and root.gui_get_focus_owner() == null
		),
		"a real pointer click changes the option without stealing keyboard focus"
	)
	var capture_path := _capture_path()
	if not capture_path.is_empty():
		if DisplayServer.get_name() == "headless":
			_check(false, "rendered capture requires a display-backed fixture")
		else:
			await RenderingServer.frame_post_draw
		_check(
			(
				DisplayServer.get_name() != "headless"
				and root.get_texture().get_image().save_png(capture_path) == OK
			),
			"the rendered System Options fixture capture is written",
		)
	options.hide()
	await process_frame
	_check(not options.snapshot().visible, "the classic options panel closes cleanly")
	options.queue_free()
	await process_frame
	if not _failed:
		print("CLASSIC_SYSTEM_OPTIONS_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _click(point: Vector2) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = point
	Input.parse_input_event(motion)
	await process_frame
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		Input.parse_input_event(event)
		await process_frame


func _capture_path() -> String:
	var arguments := OS.get_cmdline_user_args()
	for index in range(arguments.size() - 1):
		if arguments[index] == "--capture":
			return arguments[index + 1]
	return ""


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("CLASSIC_SYSTEM_OPTIONS_SMOKE FAIL " + description)
