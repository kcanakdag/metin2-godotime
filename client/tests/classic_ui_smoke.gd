extends SceneTree
## Isolated presentation checks. No database state is synthesized in the game.

const Hud = preload("res://scripts/ui/dev_hud.gd")

var _hud: CanvasLayer
var _events: Array = []
var _checks: Array[String] = []
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_hud = Hud.new()
	root.add_child(_hud)
	await process_frame
	_hud.set_connection_state("connected", "")
	_hud.set_player_info(
		{"health": 60, "max_health": 100, "gold": 123, "x": 660, "z": 575, "heading": 0}
	)
	_hud.set_inventory(
		[
			{"id": 11, "vnum": 10, "count": 1, "cell": 0, "equipped": false},
			{"id": 12, "vnum": 27001, "count": 3, "cell": 1, "equipped": false}
		]
	)
	_hud.equip_item_requested.connect(func(id: int) -> void: _events.append(["equip", id]))
	_hud.use_item_requested.connect(func(id: int) -> void: _events.append(["use", id]))
	_hud.move_item_requested.connect(
		func(id: int, cell: int) -> void: _events.append(["move", id, cell])
	)
	_check(_key(KEY_I), "I is consumed by inventory")
	await process_frame
	var snapshot: Dictionary = _hud.inventory_snapshot()
	_check(
		snapshot["visible"] and snapshot["window_rect"] == [1104.0, 198.0, 176.0, 565.0],
		"native inventory dimensions and anchor"
	)
	var sword: Array = snapshot["slot_centers"][0]
	_click(sword, MOUSE_BUTTON_RIGHT)
	await process_frame
	_check(_events == [["equip", 11]], "right click sword emits equip intent")
	_check(not _hud._inventory_rows[0]["equipped"], "equip has no optimistic item grant")
	var potion: Array = snapshot["slot_centers"][1]
	_click(potion, MOUSE_BUTTON_LEFT)
	await process_frame
	_check(_hud.inventory_snapshot()["dragging"], "left click attaches item to cursor")
	_click(snapshot["quickslot_centers"][0], MOUSE_BUTTON_LEFT)
	await process_frame
	_check(
		_hud.inventory_snapshot()["quickslot_bindings"][0] == 12, "click attachment binds quickslot"
	)
	_check(_key(KEY_1), "quickslot key is consumed")
	_check(_events.back() == ["use", 12], "quickslot sends potion use intent")
	_check(
		_hud._inventory_rows[1]["count"] == 3,
		"use keeps subscribed stack until server confirmation"
	)
	_click(potion, MOUSE_BUTTON_LEFT)
	_click(snapshot["slot_centers"][3], MOUSE_BUTTON_LEFT)
	await process_frame
	_check(_events.back() == ["move", 12, 3], "click attachment sends move intent")
	_check(_key(KEY_ESCAPE) and not _hud.inventory_snapshot()["visible"], "Escape closes inventory")
	_hud.focus_chat()
	_check(_hud.wants_keyboard() and not _key(KEY_I), "chat keeps gameplay hotkeys as text")
	_check(_key(KEY_ESCAPE) and not _hud.wants_keyboard(), "Escape releases chat focus")
	_hud.set_profile("classic-ui-test".sha256_text())
	_hud._hotbar.bind_item(0, _hud._inventory_rows[1])
	_hud._save_profile()
	_hud.set_profile("classic-ui-other".sha256_text())
	_check(_hud.inventory_snapshot()["quickslot_bindings"][0] == 0, "identity settings isolated")
	_hud.set_profile("classic-ui-test".sha256_text())
	_check(_hud.inventory_snapshot()["quickslot_bindings"][0] == 12, "quickslot binding restored")
	_key(KEY_I)
	await process_frame
	if not DisplayServer.get_name() == "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://classic-ui.png")
	if not _failed:
		print("CLASSIC_UI_SMOKE PASS ", _checks.size(), " checks")
	_hud.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _key(code: Key) -> bool:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	return _hud.handle_key(event)


func _click(point: Array, button: MouseButton) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(point[0], point[1])
	root.push_input(motion, true)
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = button
		event.pressed = pressed
		event.position = motion.position
		root.push_input(event, true)


func _check(passed: bool, description: String) -> void:
	if not passed:
		push_error("CLASSIC_UI_SMOKE FAIL " + description)
		_failed = true
		return
	_checks.append(description)
