extends SceneTree
## Exercise authoritative Status/taskbar/Info behavior without a server or editor bridge.

const Hud = preload("res://scripts/ui/dev_hud.gd")
const Art = preload("res://scripts/ui/classic_art.gd")
const Tooltip = preload("res://scripts/ui/classic_tooltip.gd")

var _hud: DevHud
var _events: Array = []
var _chat_events: Array[String] = []
var _command_events: Array = []
var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 720)
	_hud = Hud.new()
	root.add_child(_hud)
	await process_frame
	_hud.stat_allocation_requested.connect(
		func(character_id: String, stat_code: String): _events.append([character_id, stat_code])
	)
	_hud.chat_submitted.connect(func(message: String): _chat_events.append(message))
	_hud.command_requested.connect(
		func(command: String, request_id: String, argument: String):
			_command_events.append([command, request_id, argument])
	)
	_hud.set_connection_state("connected", "Connected")
	_hud.set_player_info({"name": "Warrior", "health": 380, "max_health": 760, "gold": 0})
	_hud.set_progression(_progression(75, 300, 1, 89, 90))
	_check(_key(KEY_C), "C is handled while the world owns keyboard input")
	var snapshot: Dictionary = _hud.inventory_snapshot()
	_check(snapshot.status.visible, "C opens Status")
	_check(snapshot.status.rect == [24.0, 161.0, 253.0, 361.0], "native Status bounds")
	_check(
		(
			snapshot.status.tab_rects
			== [
				[30.0, 494.0, 53.0, 27.0],
				[85.0, 494.0, 67.0, 27.0],
				[154.0, 494.0, 61.0, 27.0],
				[216.0, 494.0, 55.0, 27.0],
			]
		),
		"original tab hit rectangles"
	)
	_check(snapshot.status.bars[0].rect == [39.0, 269.0, 223.0, 17.0], "standard bar bounds")
	_check(snapshot.status.bars[0].right[0] == 230.0, "standard bar right cap starts at width - 32")
	_check(snapshot.status.bars[0].right[0] + 32.0 == 262.0, "standard bar ends at source edge")
	_check(snapshot.status.values.name == "Warrior", "subscribed player name is rendered")
	_check(snapshot.status.values.level == "1", "subscribed level is rendered")
	_check(snapshot.status.values.experience == "75", "subscribed EXP is rendered")
	_check(snapshot.status.values.remaining_exp == "225", "remaining EXP uses server next_exp")
	_check(snapshot.status.values.health == "380/760", "public combat HP projection is rendered")
	_check(snapshot.status.values.sp == "130/260", "private SP projection is rendered")
	_check(snapshot.status.values.vitality == "89", "canonical VIT is rendered")
	_check(snapshot.status.values.unspent_stat_points == "1", "available points are rendered")
	_check(not snapshot.status.plus.ht.disabled, "point and stat 89 enable VIT allocation")
	_check(snapshot.status.plus.ht.visible, "allocatable VIT plus is visible")
	_check(not snapshot.status.plus.st.visible, "capped STR plus is hidden")
	_check(snapshot.status.plus.st.tooltip == "Maximum 90 reached.", "stat cap is explained")
	_check(is_equal_approx(float(snapshot.taskbar.hp_width), 47.5), "taskbar HP clips to one half")
	_check(is_equal_approx(float(snapshot.taskbar.sp_width), 47.5), "taskbar SP clips to one half")
	_check(_xp_heights(snapshot) == [19.0, 0.0, 0.0, 0.0], "one full EXP quarter")
	_click(snapshot.status.plus.ht.center)
	await process_frame
	_check(_events == [["a".repeat(64), "ht"]], "plus emits one exact allocation intent")
	_check(
		_hud.inventory_snapshot().status.values.vitality == "89",
		"allocation does not optimistically mutate the stat"
	)
	_hud.set_progression(_progression(150, 300, 0, 90, 90))
	snapshot = _hud.inventory_snapshot()
	_check(snapshot.status.values.vitality == "90", "subscribed allocation update is rendered")
	_check(not snapshot.status.plus.ht.visible, "zero points hide VIT allocation")
	_check(not snapshot.status.points_visible, "zero points hide the points label")
	_check(_xp_heights(snapshot) == [19.0, 19.0, 0.0, 0.0], "two full EXP quarters")
	_hud.set_progression(_progression(37, 300, 0, 90, 90))
	snapshot = _hud.inventory_snapshot()
	var partial := float(snapshot.taskbar.xp_fills[0].height)
	_check(partial > 9.3 and partial < 9.5, "fractional EXP clips one partial orb")
	_check(
		is_equal_approx(float(snapshot.taskbar.xp_fills[0].top), 28.0 - partial),
		"partial EXP orb is bottom anchored"
	)
	_check(snapshot.taskbar.xp_fills[0].width == 19.0, "partial EXP orb keeps its width")
	_check(snapshot.taskbar.xp_tooltip.ends_with("(12.33%)"), "XP tooltip keeps two decimals")
	_hud.set_progression(_progression(0, 0, 0, 90, 90, 99))
	snapshot = _hud.inventory_snapshot()
	_check(_xp_heights(snapshot) == [0.0, 0.0, 0.0, 0.0], "cap hides all EXP orbs")
	_check(snapshot.taskbar.xp_tooltip == "XP: Maximum level", "cap avoids division by zero")
	_hover(snapshot.taskbar.xp_hover_center)
	await process_frame
	var hovered := _hud.get_viewport().gui_get_hovered_control()
	_check(
		hovered != null and hovered.tooltip_text == "XP: Maximum level",
		"empty cap board remains hoverable"
	)
	_hud.focus_chat()
	_check(_hud.wants_keyboard(), "chat owns keyboard focus")
	_check(not _key(KEY_C) and _hud.inventory_snapshot().status.visible, "chat focus blocks C")
	_check(_key(KEY_ESCAPE) and not _hud.wants_keyboard(), "first Escape releases chat focus")
	_check(_hud.inventory_snapshot().status.visible, "chat Escape preserves Status")
	_check(
		_key(KEY_ESCAPE) and not _hud.inventory_snapshot().status.visible,
		"next Escape closes Status"
	)
	_click(snapshot.taskbar.character_center)
	await process_frame
	_check(_hud.inventory_snapshot().status.visible, "taskbar Character opens the same Status")
	await _submit_chat("Normal message")
	_check(_chat_events == ["Normal message"], "normal text retains public chat routing")
	await _submit_chat("/help")
	_check(
		_command_events.size() == 1 and _command_events[0][0] == "help",
		"slash help uses the typed private route"
	)
	var request_id := str(_command_events[0][1])
	_check(
		request_id.length() == 32 and request_id.is_valid_hex_number(false),
		"command request id is 16 random bytes encoded as lowercase hex"
	)
	await _submit_chat("/xp  1")
	_check(
		_command_events.back()[0] == "xp" and _command_events.back()[2] == " 1",
		"XP text reaches authoritative parser unchanged"
	)
	var before_commands := _command_events.size()
	await _submit_chat("/unknown secret")
	_check(_command_events.size() == before_commands, "unknown slash text calls no reducer route")
	_check(_chat_events == ["Normal message"], "slash text never enters public chat")
	_check(
		_hud.inventory_snapshot().chat.local_info_count == 1,
		"unknown command is private local Info"
	)
	_hud.set_command_feedback([_feedback(7, "First"), _feedback(7, "Updated")])
	snapshot = _hud.inventory_snapshot()
	_check(snapshot.chat.feedback_count == 1, "feedback snapshot dedupes the same server id")
	_check(
		snapshot.chat.feedback_lines == ["Info : Updated"], "feedback upsert redraws changed text"
	)
	_hud._chat_panel._opacities["feedback:7"] = 0.01
	var faded_arrival: float = _hud._chat_panel._arrivals["feedback:7"]
	_hud.set_command_feedback([_feedback(7, "Updated")])
	_check(
		is_equal_approx(float(_hud._chat_panel._opacities["feedback:7"]), 0.01),
		"byte-identical feedback replay preserves faded opacity"
	)
	_check(
		is_equal_approx(float(_hud._chat_panel._arrivals["feedback:7"]), faded_arrival),
		"byte-identical feedback replay preserves arrival time"
	)
	_hud.set_command_feedback([_feedback(7, "Visible update")])
	_check(
		is_equal_approx(float(_hud._chat_panel._opacities["feedback:7"]), 1.0),
		"material same-id feedback update becomes visible again"
	)
	_check(
		_hud.inventory_snapshot().chat.feedback_lines == ["Info : Visible update"],
		"material same-id feedback update replaces displayed text"
	)
	var feedback: Array = []
	for id in 35:
		feedback.append(_feedback(id, "Result %d" % id))
	_hud.set_command_feedback(feedback)
	snapshot = _hud.inventory_snapshot()
	_check(snapshot.chat.feedback_count == 32, "feedback display remains bounded to 32 rows")
	_hud._chat_panel._opacities["feedback:34"] = 0.25
	var lobby_arrival: float = _hud._chat_panel._arrivals["feedback:34"]
	_hud.set_connection_state("disconnected", "Disconnected")
	snapshot = _hud.inventory_snapshot()
	_check(not snapshot.status.visible, "disconnect closes Status")
	_check(snapshot.chat.feedback_count == 32, "leaving world preserves lobby feedback snapshot")
	_hud.set_connection_state("connected", "Connected")
	_check(
		_hud.inventory_snapshot().chat.feedback_count == 32,
		"reentering with no new feedback restores the cached lobby snapshot"
	)
	_check(
		(
			is_equal_approx(float(_hud._chat_panel._opacities["feedback:34"]), 0.25)
			and is_equal_approx(float(_hud._chat_panel._arrivals["feedback:34"]), lobby_arrival)
		),
		"leave and reenter preserve feedback presentation state"
	)
	_hud.set_connection_state("disconnected", "Disconnected")
	_hud.set_command_feedback([])
	_check(_hud.inventory_snapshot().chat.feedback_count == 0, "account logout clears feedback")
	_hud.set_connection_state("connected", "Connected")
	_check(_hud.inventory_snapshot().chat.feedback_count == 0, "new account starts isolated")
	_hud.set_command_feedback([_feedback(42, "Restored")])
	_check(
		_hud.inventory_snapshot().chat.feedback_lines == ["Info : Restored"],
		"resubscription restores one private feedback snapshot"
	)
	_check(
		str(_hud.inventory_snapshot().chat.passive_colors.back()).begins_with("ffc8c8"),
		"private Info renders with the original pale-pink color"
	)
	_hud.set_progression({})
	_check(
		_hud.inventory_snapshot().status.values.level == "—",
		"missing progression never invents level-one values"
	)
	_check(_hud.inventory_snapshot().status.loading, "missing progression is distinguishable")
	_check(Art.item_name(27002) == "Red Potion (M)", "medium potion uses selected English name")
	var tooltip := Tooltip.new()
	root.add_child(tooltip)
	await process_frame
	tooltip.show_item({"vnum": 27002})
	_check(
		_tooltip_text(tooltip).contains("Cannot be used yet."),
		"medium potion tooltip marks use as deferred"
	)
	var visual_row := _progression(37, 300, 0, 4, 6)
	visual_row.current_sp = 260
	_hud.set_progression(visual_row)
	_hud.set_player_info({"name": "Warrior", "health": 380, "max_health": 760, "gold": 0})
	if not _hud.inventory_snapshot().status.visible:
		_key(KEY_C)
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://classic-status-1280.png")
		root.get_texture().get_image().save_png("user://classic-status-xp-fractional.png")
	root.size = Vector2i(1024, 600)
	await process_frame
	await process_frame
	var rect := _array_rect(_hud.inventory_snapshot().status.rect)
	_check(
		Rect2(Vector2.ZERO, Vector2(root.size)).encloses(rect),
		"Status stays on screen after resize"
	)
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://classic-status.png")
	if not _failed:
		print("CLASSIC_STATUS_SMOKE PASS ", _checks, " checks")
	_hud.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _progression(
	experience: int, next_exp: int, points: int, vitality: int, strength: int, level := 1
) -> Dictionary:
	return {
		"character_id": "a".repeat(64),
		"level": level,
		"experience": experience,
		"next_exp": next_exp,
		"level_step": 0,
		"unspent_stat_points": points,
		"strength": strength,
		"vitality": vitality,
		"dexterity": 3,
		"intelligence": 3,
		"random_hp": 0,
		"random_sp": 0,
		"current_sp": 130,
		"max_sp": 260,
	}


func _feedback(id: int, message: String) -> Dictionary:
	return {
		"id": id,
		"request_id": "b".repeat(32),
		"severity": "info",
		"message": message,
		"created_at": id,
	}


func _tooltip_text(node: Node) -> String:
	var lines: PackedStringArray = []
	for child in node.get_children():
		if child is Label:
			lines.append(child.text)
	return "\n".join(lines)


func _key(code: Key) -> bool:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	return _hud.handle_key(event)


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


func _hover(point: Array) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(point[0], point[1])
	root.push_input(motion, true)


func _submit_chat(text: String) -> void:
	_hud.focus_chat()
	_hud._chat_panel._chat_input.text = text
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = KEY_ENTER
		event.pressed = pressed
		root.push_input(event, true)
	await process_frame


func _array_rect(values: Array) -> Rect2:
	return Rect2(values[0], values[1], values[2], values[3])


func _xp_heights(snapshot: Dictionary) -> Array:
	var result: Array = []
	for fill: Dictionary in snapshot.taskbar.xp_fills:
		result.append(fill.height)
	return result


func _check(condition: bool, message: String) -> void:
	if condition:
		_checks += 1
	else:
		_failed = true
		push_error("CLASSIC_STATUS_SMOKE FAIL " + message)
