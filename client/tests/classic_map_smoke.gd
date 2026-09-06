extends SceneTree
## Original map controls, real GUI dispatch, subscribed-coordinate presentation only.

const MapPanel = preload("res://scripts/ui/classic_map_panel.gd")

var _world_input: WorldInputProbe
var _panel: Control
var _checks: Array[String] = []
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_world_input = WorldInputProbe.new()
	root.add_child(_world_input)
	_panel = MapPanel.new()
	root.add_child(_panel)
	await process_frame
	_panel.set_world_info({"map_id": "metin2_map_a1"})
	_panel.set_player_info(
		{"identity": "local", "name": "Warrior", "x": 512, "z": 640, "heading": 0}
	)
	_panel.set_players(
		[{"identity": "local", "x": 512, "z": 640}, {"identity": "other", "x": 520, "z": 648}],
		"local"
	)
	var state: Dictionary = _panel.snapshot()
	_check(state.supported and state.minimap_visible, "original minimap opens on supported map")
	_click([1212, 69])
	_check(_world_input.clicks == 0, "clicking minimap does not issue world input")
	_click(state.minimap_close_center)
	await process_frame
	_check(not _panel.snapshot().minimap_visible, "original close button hides minimap")
	_click(state.minimap_open_center)
	await process_frame
	_check(_panel.snapshot().minimap_visible, "original reopen button restores minimap")
	_click(state.zoom_in_center)
	_check(_panel.snapshot().minimap_meters_per_pixel == 0.5, "original zoom button doubles scale")
	_click(state.zoom_out_center)
	_check(
		_panel.snapshot().minimap_meters_per_pixel == 1.0,
		"zoom returns to native one pixel per meter"
	)
	_click(state.atlas_button_center)
	await process_frame
	state = _panel.snapshot()
	_check(
		state.atlas_visible and state.atlas_rect == [878.0, 0.0, 186.0, 252.0],
		"original atlas dimensions and anchor"
	)
	_check(
		state.mapimage_rect == [885.0, 30.0, 171.0, 214.0], "native original atlas image placement"
	)
	_check(state.atlas_player == [85.5, 107.0], "subscribed world center maps to atlas center")
	_click(state.atlas_button_center)
	_check(_panel.snapshot().atlas_visible, "atlas button shows without toggling an open atlas")
	_panel.set_player_info(
		{"identity": "local", "name": "Warrior", "x": 256, "z": 320, "heading": PI / 2}
	)
	_check(
		_panel.snapshot().atlas_player == [42.75, 53.5],
		"new subscription coordinates move atlas marker"
	)
	var title: Array = state.atlas_title_center
	await _drag(title, [title[0] - 100, title[1] + 100])
	state = _panel.snapshot()
	_check(
		state.atlas_rect[0] == 778.0 and state.atlas_rect[1] == 100.0,
		"atlas title supports real GUI dragging"
	)
	_click(state.atlas_close_center)
	await process_frame
	_check(not _panel.snapshot().atlas_visible, "atlas close button hides map")
	_panel.toggle_atlas()
	_check(
		_panel.snapshot().atlas_visible and _panel.snapshot().atlas_rect[0] == 778.0,
		"M toggle preserves dragged atlas position"
	)
	_check(_panel.close_top() and not _panel.close_top(), "Escape consumes only an open atlas")
	_panel.toggle_atlas()
	_panel.set_world_info({"map_id": "training_ground"})
	_panel.toggle_atlas()
	_check(
		not _panel.snapshot().atlas_visible and not _panel.snapshot().supported,
		"unsupported training map disables atlas"
	)
	_check(
		_panel.snapshot().atlas_player.is_empty(), "unsupported map clears live marker presentation"
	)
	_panel.set_world_info({"map_id": "metin2_map_a1"})
	_panel.toggle_atlas()
	await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://classic-map.png")
	if not _failed:
		print("CLASSIC_MAP_SMOKE PASS ", _checks.size(), " checks")
	_world_input.queue_free()
	_panel.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _click(point: Array) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(point[0], point[1])
	root.push_input(motion, true)
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = motion.position
		root.push_input(event, true)


func _drag(start: Array, end: Array) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(start[0], start[1])
	Input.parse_input_event(motion)
	var button := InputEventMouseButton.new()
	button.button_index = MOUSE_BUTTON_LEFT
	button.position = motion.position
	button.pressed = true
	Input.parse_input_event(button)
	await process_frame
	motion = InputEventMouseMotion.new()
	motion.position = Vector2(end[0], end[1])
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(motion)
	await process_frame
	button = InputEventMouseButton.new()
	button.button_index = MOUSE_BUTTON_LEFT
	button.position = motion.position
	button.pressed = false
	Input.parse_input_event(button)
	await process_frame


func _check(passed: bool, description: String) -> void:
	if not passed:
		push_error("CLASSIC_MAP_SMOKE FAIL " + description)
		_failed = true
		return
	_checks.append(description)


class WorldInputProbe:
	extends Node
	var clicks := 0

	func _unhandled_input(event: InputEvent) -> void:
		if (
			event is InputEventMouseButton
			and event.button_index == MOUSE_BUTTON_LEFT
			and event.pressed
		):
			clicks += 1
