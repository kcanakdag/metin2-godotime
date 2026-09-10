extends SceneTree
var _checks := 0
var _failed := false


class GameplayInput:
	extends Node
	var movement_keys := 0
	var world_clicks := 0

	func _unhandled_input(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed and event.physical_keycode == KEY_W:
			movement_keys += 1
		if event is InputEventMouseButton and event.pressed:
			world_clicks += 1


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	root.gui_embed_subwindows = true
	var strip := preload("res://scripts/ui/classic_buffs.gd").new()
	root.add_child(strip)
	await process_frame
	var row := {
		"id": "owner:3",
		"character_id": "owner",
		"skill_vnum": 3,
		"paused": false,
		"remaining_ticks": 64
	}
	strip.set_state([row], "owner")
	_check(strip.position == Vector2(10, 10), "original affect origin")
	_check(strip._icons.size() == 1, "one icon per affect")
	if strip._icons.is_empty():
		quit(1)
		return
	var icon: TextureRect = strip._icons[row.id]
	_check(icon.scale == Vector2(0.7, 0.7), "original affect scale")
	_check(icon.texture != null, "original active-affect icon loads")
	_check(
		icon.texture.resource_path.ends_with("jeongwi_03.png"),
		"active icon differs from rank-one learning icon"
	)
	_check(icon.focus_mode == Control.FOCUS_NONE, "buff icon cannot steal keyboard focus")
	_check(icon.tooltip_text.is_empty(), "native boxed tooltip is disabled")
	row.remaining_ticks = 63
	strip.set_state([row, row], "owner")
	_check(
		strip._icons.size() == 1 and strip._icons[row.id] == icon,
		"duration updates reuse icon and deduplicate"
	)
	_check(strip._names[row.id] == "Berserk", "duration update preserves classic skill name")
	var state := strip.snapshot()
	_check(state["count"] == 1, "probe snapshot reports one active affect")
	_check(state["rows"][0]["id"] == row.id, "probe snapshot binds affect identity")
	_check(state["rows"][0]["name"] == "Berserk", "probe snapshot carries classic skill name")
	strip.set_state([row], "peer")
	_check(strip._icons.is_empty(), "character switch clears former icon")
	row.paused = true
	strip.set_state([row], "owner")
	_check(strip._icons.is_empty(), "paused status is not shown as active")
	_check(strip.snapshot()["count"] == 0, "probe snapshot clears inactive affects")
	row.paused = false
	strip.set_state([row], "owner")
	await process_frame
	await process_frame
	await _test_input(strip._icons[row.id])
	strip.set_state([], "owner")
	_check(strip._icons.is_empty(), "expiry or disconnect removes icon")
	_check(not strip._description.visible, "expiry removes hovered text")
	if not _failed:
		print("BUFFS_UI_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _test_input(icon: TextureRect) -> void:
	var observer := GameplayInput.new()
	root.add_child(observer)
	var motion := InputEventMouseMotion.new()
	motion.position = icon.get_global_rect().get_center()
	motion.global_position = motion.position
	root.push_input(motion, true)
	await process_frame
	_check(root.gui_get_hovered_control() == icon, "real mouse hover reaches icon")
	await process_frame
	_check(_tooltip_visible(root), "hover displays original skill-name text")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://buffs-ui-component.png")
	var click := InputEventMouseButton.new()
	click.position = motion.position
	click.global_position = motion.position
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	root.push_input(click, true)
	click = click.duplicate()
	click.pressed = false
	root.push_input(click, true)
	var key := InputEventKey.new()
	key.physical_keycode = KEY_W
	key.pressed = true
	root.push_input(key, true)
	key = key.duplicate()
	key.pressed = false
	root.push_input(key, true)
	await process_frame
	_check(observer.movement_keys == 1, "movement key survives icon interaction")
	_check(observer.world_clicks == 1, "icon does not consume world click")
	_check(root.gui_get_focus_owner() == null, "icon interaction leaves keyboard focus free")
	observer.queue_free()


func _tooltip_visible(node: Node) -> bool:
	if node is Label and node.is_visible_in_tree() and node.text == "Berserk":
		return true
	for child: Node in node.get_children(true):
		if _tooltip_visible(child):
			return true
	return false


func _check(passed: bool, label: String) -> void:
	_checks += 1
	if not passed:
		_failed = true
		push_error("BUFFS_UI_SMOKE FAIL " + label)
