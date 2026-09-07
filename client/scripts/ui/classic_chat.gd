extends Control
## Chat geometry and interactions follow the pinned English client's uichat.py.
## The server supplies all displayed messages; this component only emits text intents.

signal submitted(message: String)

const Art = preload("res://scripts/ui/classic_art.gd")
const CHAT_WIDTH := 600.0
const LINE_STEP := 15.0
const VIEW_SECONDS := 5.0
const LOG_MINIMUM := Vector2(450, 120)
const MAX_MESSAGES := 300
const INFO_COLOR := Color8(255, 200, 200)

var _connected := false
var _waiting_for_rows := true
var _rows: Array[Dictionary] = []
var _feedback: Array[Dictionary] = []
var _local_info: Array[Dictionary] = []
var _arrivals: Dictionary = {}
var _opacities: Dictionary = {}
var _sent: Array[String] = []
var _sent_index := 0
var _entry: Control
var _chat_input: LineEdit
var _passive: Control
var _backdrop: TextureRect
var _sizing: Control
var _edit_height := 138.0
var _history: Control
var _history_input: LineEdit
var _history_lines: Control
var _history_entry: Control
var _history_title_middle: TextureRect
var _history_title_right: TextureRect
var _history_close: TextureButton
var _history_resize: Control
var _history_scroll: Control
var _scroll_down: TextureButton
var _scroll_thumb: TextureButton
var _scroll_position := 1.0
var _history_all: TextureButton
var _history_normal: TextureButton
var _history_info: TextureButton
var _show_normal := true
var _show_info := true
var _drag_mode := ""
var _drag_offset := Vector2.ZERO
var _last_fade_tick := -1


func _ready() -> void:
	name = "ClassicChat"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_build_chat()
	_build_history()
	get_viewport().size_changed.connect(_layout)
	_layout()
	hide()


func _build_chat() -> void:
	_backdrop = TextureRect.new()
	_backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_backdrop.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	var gradient := GradientTexture2D.new()
	gradient.gradient = Gradient.new()
	gradient.gradient.colors = PackedColorArray([Color.TRANSPARENT, Color(0, 0, 0, 0.8)])
	gradient.fill_to = Vector2(0, 1)
	_backdrop.texture = gradient
	add_child(_backdrop)
	_passive = Control.new()
	_passive.name = "ChatLines"
	_passive.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_passive.clip_contents = true
	add_child(_passive)
	_entry = _make_entry(self, CHAT_WIDTH - 50)
	_entry.name = "ChatEntry"
	_chat_input = _entry.get_node("Input")
	var whisper := Art.button(
		_entry, "game/taskbar/send_whisper_button_", Vector2(550, 2), Callable()
	)
	whisper.disabled = true
	whisper.tooltip_text = "Whisper is not available yet"
	var log_button := Art.button(
		_entry, "game/taskbar/open_chat_log_button_", Vector2(575, 2), toggle_history
	)
	log_button.tooltip_text = "Chat Log (L)"
	_entry.hide()
	_sizing = Control.new()
	_sizing.name = "ChatHeightHandle"
	_sizing.size = Vector2(CHAT_WIDTH, 22)
	_sizing.mouse_filter = Control.MOUSE_FILTER_STOP
	_sizing.mouse_default_cursor_shape = Control.CURSOR_VSIZE
	_sizing.gui_input.connect(_begin_drag.bind("chat_height"))
	add_child(_sizing)
	Art.image(_sizing, "pattern/chat_bar_left", Vector2.ZERO)
	Art.tile(_sizing, "pattern/chat_bar_middle", Rect2(64, 0, CHAT_WIDTH - 128, 32))
	Art.image(_sizing, "pattern/chat_bar_right", Vector2(CHAT_WIDTH - 64, 0))
	_sizing.hide()


func _make_entry(parent: Node, width: float) -> Control:
	var entry := Control.new()
	entry.size = Vector2(width, 25)
	entry.mouse_filter = Control.MOUSE_FILTER_STOP
	parent.add_child(entry)
	var mode := Panel.new()
	mode.position = Vector2(7, 2)
	mode.size = Vector2(40, 17)
	mode.add_theme_stylebox_override("panel", _outline())
	mode.tooltip_text = "Normal chat"
	entry.add_child(mode)
	var caption := Art.label(mode, "Normal", Vector2.ZERO, Color.WHITE)
	caption.size = mode.size
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var outline := Panel.new()
	outline.name = "InputOutline"
	outline.position = Vector2(53, 2)
	outline.size = Vector2(width - 86, 17)
	outline.mouse_filter = Control.MOUSE_FILTER_IGNORE
	outline.add_theme_stylebox_override("panel", _outline())
	entry.add_child(outline)
	var field := LineEdit.new()
	field.name = "Input"
	field.position = Vector2(57, 2)
	field.max_length = 160
	field.add_theme_font_size_override("font_size", 12)
	field.add_theme_color_override("font_color", Color.WHITE)
	field.add_theme_color_override("caret_color", Color.WHITE)
	for state in ["normal", "focus", "read_only"]:
		field.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	field.text_submitted.connect(_submit.bind(field))
	field.gui_input.connect(_on_input_key.bind(field))
	entry.add_child(field)
	field.size = Vector2(width - 93, 17)
	var send := Art.button(
		entry,
		"game/taskbar/send_chat_button_",
		Vector2(width - 25, 2),
		func() -> void: _submit(field.text, field)
	)
	send.name = "Send"
	send.tooltip_text = "Send Chat"
	return entry


func _outline(margin: int = 0) -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = Color.TRANSPARENT
	result.border_color = Color.WHITE
	result.set_border_width_all(1)
	result.set_corner_radius_all(2)
	result.content_margin_left = margin
	result.content_margin_right = margin
	return result


func _build_history() -> void:
	_history = Control.new()
	_history.name = "ChatLogWindow"
	_history.position = Vector2(20, 20)
	_history.size = LOG_MINIMUM
	_history.mouse_filter = Control.MOUSE_FILTER_STOP
	_history.draw.connect(_draw_history)
	add_child(_history)
	var title := Control.new()
	title.name = "Title"
	title.size = Vector2(LOG_MINIMUM.x, 24)
	title.mouse_filter = Control.MOUSE_FILTER_STOP
	title.gui_input.connect(_begin_drag.bind("history_move"))
	_history.add_child(title)
	Art.image(title, "pattern/chatlogwindow_titlebar_left", Vector2.ZERO)
	_history_title_middle = Art.tile(
		title, "pattern/chatlogwindow_titlebar_middle", Rect2(32, 0, LOG_MINIMUM.x - 64, 32)
	)
	_history_title_right = Art.image(
		title, "pattern/chatlogwindow_titlebar_right", Vector2(LOG_MINIMUM.x - 32, 0)
	)
	Art.label(title, "Chat Log", Vector2(20, 6), Color.WHITE)
	_history_close = Art.button(_history, "public/close_button_", Vector2.ZERO, _close_history)
	_history_close.tooltip_text = "Close"
	_history_all = _filter_button("All", 13, _select_all)
	_history_all.button_pressed = true
	_history_normal = _filter_button("Normal", 61, _select_normal)
	var unavailable := ["Party", "Guild", "Shout"]
	for index in unavailable.size():
		var button := _filter_button(unavailable[index], 109 + index * 48, Callable())
		button.disabled = true
		button.tooltip_text = unavailable[index] + " is not available yet"
	_history_info = _filter_button("Info", 253, _select_info)
	var notice := _filter_button("Notice", 301, Callable())
	notice.disabled = true
	notice.tooltip_text = "Notice is not available yet"
	_history_lines = Control.new()
	_history_lines.name = "HistoryLines"
	_history_lines.position = Vector2(10, 45)
	_history_lines.mouse_filter = Control.MOUSE_FILTER_STOP
	_history_lines.clip_contents = true
	_history_lines.gui_input.connect(_history_wheel)
	_history.add_child(_history_lines)
	_history_entry = _make_entry(_history, LOG_MINIMUM.x - 20)
	_history_input = _history_entry.get_node("Input")
	_build_scrollbar()
	_history_resize = Control.new()
	_history_resize.name = "Resize"
	_history_resize.size = Vector2(16, 16)
	_history_resize.mouse_filter = Control.MOUSE_FILTER_STOP
	_history_resize.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	_history_resize.gui_input.connect(_begin_drag.bind("history_size"))
	_history.add_child(_history_resize)
	_history.hide()


func _filter_button(text: String, x: float, action: Callable) -> TextureButton:
	var result := Art.button(_history, "public/xsmall_button_", Vector2(x, 24), action)
	result.toggle_mode = true
	var caption := Art.label(result, text, Vector2.ZERO)
	caption.size = Vector2(48, 17)
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return result


func _build_scrollbar() -> void:
	_history_scroll = Control.new()
	_history_scroll.name = "HistoryScroll"
	_history_scroll.mouse_filter = Control.MOUSE_FILTER_STOP
	_history_scroll.gui_input.connect(_on_scroll_track)
	_history.add_child(_history_scroll)
	Art.button(
		_history_scroll,
		"public/scrollbar_small_thin_up_button_",
		Vector2.ZERO,
		_scroll_by.bind(-0.2)
	)
	_scroll_down = Art.button(
		_history_scroll,
		"public/scrollbar_small_thin_down_button_",
		Vector2.ZERO,
		_scroll_by.bind(0.2)
	)
	_scroll_thumb = TextureButton.new()
	_scroll_thumb.name = "Thumb"
	_scroll_thumb.texture_normal = Art.texture("public/scrollbar_small_thin_middle_button_01")
	_scroll_thumb.texture_hover = _scroll_thumb.texture_normal
	_scroll_thumb.texture_pressed = _scroll_thumb.texture_normal
	_scroll_thumb.focus_mode = Control.FOCUS_NONE
	_scroll_thumb.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_scroll_thumb.gui_input.connect(_begin_drag.bind("scroll"))
	_history_scroll.add_child(_scroll_thumb)


func set_connected(value: bool) -> void:
	if not value and _connected:
		_waiting_for_rows = true
		_close_history()
		close_input()
		_sent.clear()
		_local_info.clear()
		_refresh_lines()
	if value and not _connected and _waiting_for_rows:
		_rows.clear()
		_prune_display_state()
		_refresh_lines()
	_connected = value
	visible = value
	_chat_input.editable = value
	_history_input.editable = value


func set_chat(rows: Array) -> void:
	var arrivals: Dictionary = {} if _waiting_for_rows else _arrivals
	var opacities: Dictionary = {} if _waiting_for_rows else _opacities
	_waiting_for_rows = false
	_rows.clear()
	var kept_arrivals: Dictionary = {}
	var kept_opacities: Dictionary = {}
	for value: Variant in rows.slice(maxi(0, rows.size() - MAX_MESSAGES)):
		if not value is Dictionary:
			continue
		var row: Dictionary = value.duplicate()
		var text := (
			"%s : %s"
			% [
				row.get("sender_name", row.get("name", "Player")),
				row.get("message", row.get("text", ""))
			]
		)
		var key := str(row.get("id", "")) + ":" + text
		row["display_text"] = text
		row["key"] = "normal:" + key
		row["kind"] = "normal"
		row["color"] = Color.WHITE
		row["order_at"] = int(row.get("sent_at", row.get("id", 0)))
		row["arrived"] = float(arrivals.get(row["key"], Time.get_ticks_msec() / 1000.0))
		kept_arrivals[row["key"]] = row["arrived"]
		kept_opacities[row["key"]] = opacities.get(row["key"], 1.0)
		_rows.append(row)
	for row: Dictionary in _feedback + _local_info:
		kept_arrivals[row["key"]] = row["arrived"]
		kept_opacities[row["key"]] = _opacities.get(row["key"], 1.0)
	_arrivals = kept_arrivals
	_opacities = kept_opacities
	if is_node_ready():
		_refresh_lines()


func set_feedback(rows: Array) -> void:
	var previous_by_id: Dictionary = {}
	for previous: Dictionary in _feedback:
		previous_by_id[int(previous.get("id", 0))] = previous
	var by_id: Dictionary = {}
	for value: Variant in rows:
		if value is Dictionary:
			by_id[int(value.get("id", 0))] = value
	var ids: Array = by_id.keys()
	ids.sort()
	_feedback.clear()
	for id: int in ids.slice(maxi(0, ids.size() - 32)):
		var row: Dictionary = by_id[id].duplicate()
		var key := "feedback:%d" % id
		row["display_text"] = "Info : " + str(row.get("message", ""))
		row["key"] = key
		row["kind"] = "info"
		row["color"] = INFO_COLOR
		row["order_at"] = int(row.get("created_at", id))
		var previous: Dictionary = previous_by_id.get(id, {})
		var changed := previous.is_empty() or not _same_feedback(previous, row)
		row["arrived"] = (
			Time.get_ticks_msec() / 1000.0
			if changed
			else float(_arrivals.get(key, Time.get_ticks_msec() / 1000.0))
		)
		_arrivals[key] = row["arrived"]
		_opacities[key] = 1.0 if changed else _opacities.get(key, 1.0)
		_feedback.append(row)
	_prune_display_state()
	if is_node_ready():
		_refresh_lines()


func _same_feedback(left: Dictionary, right: Dictionary) -> bool:
	for field in ["request_id", "severity", "message", "created_at"]:
		if left.get(field) != right.get(field):
			return false
	return true


func add_local_info(message: String) -> void:
	var text := message.strip_edges()
	if text.is_empty():
		return
	var key := "local:%d" % Time.get_ticks_usec()
	var row := {
		"display_text": "Info : " + text,
		"key": key,
		"kind": "info",
		"color": INFO_COLOR,
		"order_at": int(Time.get_unix_time_from_system() * 1000000.0),
		"arrived": Time.get_ticks_msec() / 1000.0,
	}
	_local_info.append(row)
	if _local_info.size() > 32:
		_local_info.pop_front()
	_arrivals[key] = row["arrived"]
	_opacities[key] = 1.0
	_prune_display_state()
	_refresh_lines()


func _prune_display_state() -> void:
	var live: Dictionary = {}
	for row: Dictionary in _display_rows():
		live[row["key"]] = true
	for key: String in _arrivals.keys():
		if not live.has(key):
			_arrivals.erase(key)
			_opacities.erase(key)


func _display_rows() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	result.append_array(_rows)
	result.append_array(_feedback)
	result.append_array(_local_info)
	result.sort_custom(
		func(a: Dictionary, b: Dictionary):
			if int(a["order_at"]) == int(b["order_at"]):
				return str(a["key"]) < str(b["key"])
			return int(a["order_at"]) < int(b["order_at"])
	)
	return result


func focus_chat() -> void:
	if not _connected:
		return
	_entry.show()
	_sizing.show()
	_sent_index = 0
	_chat_input.grab_focus()
	_layout()
	_refresh_lines()


func wants_keyboard() -> bool:
	return _chat_input.has_focus() or _history_input.has_focus()


func toggle_history() -> void:
	if not _connected:
		return
	if _history.visible:
		_close_history()
	else:
		_history.show()
		_history.move_to_front()
		_sent_index = 0
		_history_input.grab_focus()
		_layout_history()
		_refresh_history()


func close_input() -> bool:
	if _history_input.has_focus():
		_close_history()
		return true
	if not _entry.visible:
		return false
	_chat_input.clear()
	_chat_input.release_focus()
	_entry.hide()
	_sizing.hide()
	_layout()
	_refresh_lines()
	return true


func close_top() -> bool:
	if _history.visible:
		_close_history()
		return true
	return close_input()


func _close_history() -> void:
	_history_input.clear()
	_history_input.release_focus()
	_history.hide()
	_drag_mode = ""


func _submit(message: String, field: LineEdit) -> void:
	# Consume Enter before focus changes, so the world shortcut cannot reopen chat.
	get_viewport().set_input_as_handled()
	if not _connected:
		return
	var text := message.strip_edges()
	if text.is_empty():
		if field == _chat_input:
			close_input()
		return
	if text.length() > 160:
		return
	_sent.append(text)
	if _sent.size() > 32:
		_sent.pop_front()
	_sent_index = 0
	submitted.emit(text)
	field.clear()
	_chat_input.release_focus()
	_history_input.release_focus()
	# The development player's requested behavior returns WASD control after sending.
	close_input()


func _on_input_key(event: InputEvent, field: LineEdit) -> void:
	if not event is InputEventKey or not event.pressed:
		return
	if event.keycode == KEY_ESCAPE:
		if field == _history_input:
			_close_history()
		else:
			close_input()
		get_viewport().set_input_as_handled()
	elif event.keycode in [KEY_UP, KEY_DOWN] and not _sent.is_empty():
		var step := 1 if event.keycode == KEY_UP else -1
		_sent_index = clampi(_sent_index + step, 1, _sent.size())
		field.text = _sent[_sent.size() - _sent_index]
		field.caret_column = field.text.length()
		get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	var now := Time.get_ticks_msec() / 1000.0
	var display := _display_rows()
	for index in display.size():
		var row := display[index]
		if _entry.visible:
			_opacities[row["key"]] = 1.0
		elif now - float(row["arrived"]) >= VIEW_SECONDS or display.size() - index >= 5:
			# Match decay at the original 60 Hz target independently of browser FPS.
			_opacities[row["key"]] = float(_opacities[row["key"]]) * pow(0.9, delta * 60)
	var tick := Time.get_ticks_msec() / 100
	if tick != _last_fade_tick and not _entry.visible:
		_last_fade_tick = tick
		_refresh_passive()


func _layout() -> void:
	var viewport := get_viewport_rect().size
	var left := (viewport.x - CHAT_WIDTH) / 2
	_entry.position = Vector2(left, viewport.y - 62)
	_sizing.position = Vector2(left, viewport.y - 62 - _edit_height)
	_passive.position = Vector2(left + 10, _sizing.position.y + 25)
	_passive.size = Vector2(CHAT_WIDTH - 20, _edit_height - 25)
	if not _entry.visible:
		_passive.size.y += 25
	_layout_history()
	_refresh_lines()


func _layout_history() -> void:
	var dimensions := _history.size
	_history.get_node("Title").size.x = dimensions.x
	_history_title_middle.size.x = dimensions.x - 64
	_history_title_right.position.x = dimensions.x - 32
	_history_close.position = Vector2(dimensions.x - _history_close.size.x - 5, 5)
	_history_lines.size = Vector2(dimensions.x - 30, dimensions.y - 70)
	_history_entry.position = Vector2(0, dimensions.y - 25)
	_history_entry.size.x = dimensions.x - 20
	_history_input.size = Vector2(_history_entry.size.x - 93, 17)
	_history_entry.get_node("InputOutline").size.x = _history_entry.size.x - 86
	_history_entry.get_node("Send").position.x = _history_entry.size.x - 25
	_history_resize.position = dimensions - Vector2(16, 16)
	_history_scroll.position = Vector2(dimensions.x - 15, 45)
	_history_scroll.size = Vector2(12, dimensions.y - 57)
	_scroll_down.position.y = _history_scroll.size.y - _scroll_down.size.y
	_update_thumb()
	_history.queue_redraw()


func _draw_history() -> void:
	var dimensions := _history.size
	var shade := Color(0, 0, 0, 119.0 / 255.0)
	_history.draw_rect(Rect2(Vector2.ZERO, dimensions), shade)
	_history.draw_rect(Rect2(Vector2.ZERO, dimensions - Vector2(2, 0)), shade, false)
	_history.draw_rect(Rect2(Vector2.ONE, dimensions - Vector2(2, 0)), shade, false)
	_history.draw_rect(Rect2(dimensions.x - 15, 45, 13, dimensions.y - 45), shade)
	for length in [11, 7, 3]:
		var start := dimensions - Vector2(length + 2, 1)
		_history.draw_line(start, start + Vector2(length, -length), Color("989898"))


func _refresh_lines() -> void:
	_refresh_passive()
	_refresh_history()


func _refresh_passive() -> void:
	var lines: Array[Dictionary] = []
	for row in _display_rows():
		var opacity := 1.0 if _entry.visible else float(_opacities.get(row["key"], 1.0))
		if opacity > 0.1:
			for text in _wrap(str(row["display_text"]), _passive.size.x):
				lines.append({"text": text, "opacity": opacity, "color": row["color"]})
	_show_lines(_passive, lines, 1.0)
	_update_backdrop(lines.size())


func _update_backdrop(line_count: int) -> void:
	var gradient := _backdrop.texture as GradientTexture2D
	if _entry.visible:
		gradient.gradient.colors = PackedColorArray([Color(0, 0, 0, 0.5), Color(0, 0, 0, 0.5)])
		_backdrop.position = _sizing.position + Vector2(0, 10)
		_backdrop.size = Vector2(CHAT_WIDTH, _edit_height + 25)
	else:
		gradient.gradient.colors = PackedColorArray([Color.TRANSPARENT, Color(0, 0, 0, 0.8)])
		var shown := mini(line_count, floori(_passive.size.y / LINE_STEP))
		_backdrop.size = Vector2(CHAT_WIDTH, shown * LINE_STEP + 20 if shown > 0 else 0)
		_backdrop.position = Vector2(_entry.position.x, _entry.position.y + 25 - _backdrop.size.y)


func _refresh_history() -> void:
	var lines: Array[Dictionary] = []
	for row in _display_rows():
		if (row["kind"] == "normal" and _show_normal) or (row["kind"] == "info" and _show_info):
			for text in _wrap(str(row["display_text"]), _history_lines.size.x):
				lines.append({"text": text, "opacity": 1.0, "color": row["color"]})
	_show_lines(_history_lines, lines, _scroll_position)


func _wrap(text: String, width: float) -> PackedStringArray:
	var paragraph := TextParagraph.new()
	paragraph.width = maxf(1, width)
	paragraph.break_flags = (
		TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND | TextServer.BREAK_ADAPTIVE
	)
	paragraph.add_string(text, get_theme_default_font(), 12)
	var result: PackedStringArray = []
	for index in paragraph.get_line_count():
		var span := paragraph.get_line_range(index)
		result.append(text.substr(span.x, span.y - span.x))
	return result


func _show_lines(parent: Control, lines: Array[Dictionary], end: float) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()
	var count := maxi(0, floori(parent.size.y / LINE_STEP))
	var last := mini(lines.size(), count + roundi(maxi(0, lines.size() - count) * end))
	var first := maxi(0, last - count)
	var top := parent.size.y - (last - first) * LINE_STEP
	for index in range(first, last):
		var label := Art.label(
			parent, str(lines[index]["text"]), Vector2(0, top), lines[index]["color"]
		)
		label.modulate.a = float(lines[index]["opacity"])
		label.size = Vector2(parent.size.x, LINE_STEP)
		label.clip_text = true
		top += LINE_STEP


func _select_all() -> void:
	_show_normal = true
	_show_info = true
	_history_all.button_pressed = true
	_history_normal.button_pressed = false
	_history_info.button_pressed = false
	_refresh_history()


func _select_normal() -> void:
	_show_normal = true
	_show_info = false
	_history_all.button_pressed = false
	_history_normal.button_pressed = true
	_history_info.button_pressed = false
	_refresh_history()


func _select_info() -> void:
	_show_normal = false
	_show_info = true
	_history_all.button_pressed = false
	_history_normal.button_pressed = false
	_history_info.button_pressed = true
	_refresh_history()


func _scroll_by(step: float) -> void:
	_scroll_position = clampf(_scroll_position + step, 0, 1)
	_update_thumb()
	_refresh_history()


func _update_thumb() -> void:
	var travel := _history_scroll.size.y - _scroll_down.size.y * 2 - _scroll_thumb.size.y
	_scroll_thumb.position = Vector2(0, _scroll_down.size.y + maxf(0, travel) * _scroll_position)


func _history_wheel(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_scroll_by(-0.2)
			get_viewport().set_input_as_handled()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_scroll_by(0.2)
			get_viewport().set_input_as_handled()


func _on_scroll_track(event: InputEvent) -> void:
	_history_wheel(event)
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_LEFT:
			_set_scroll_from_y(event.position.y - _scroll_thumb.size.y / 2)
			get_viewport().set_input_as_handled()


func _set_scroll_from_y(y: float) -> void:
	var travel := _history_scroll.size.y - _scroll_down.size.y * 2 - _scroll_thumb.size.y
	_scroll_position = clampf((y - _scroll_down.size.y) / maxf(1, travel), 0, 1)
	_update_thumb()
	_refresh_history()


func _begin_drag(event: InputEvent, mode: String) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_drag_mode = mode if event.pressed else ""
		_drag_offset = event.position
		if mode == "history_size":
			_drag_offset -= _history_resize.size
		if mode != "chat_height":
			_history.move_to_front()
		get_viewport().set_input_as_handled()


func _input(event: InputEvent) -> void:
	if _drag_mode.is_empty():
		return
	if event is InputEventMouseMotion:
		if not event.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_drag_mode = ""
			return
		_update_drag(event.position)
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if not event.pressed:
			_drag_mode = ""
			get_viewport().set_input_as_handled()


func _update_drag(mouse: Vector2) -> void:
	var viewport := get_viewport_rect().size
	match _drag_mode:
		"history_move":
			_history.position = (mouse - _drag_offset).clamp(
				Vector2.ZERO, viewport - Vector2(40, 40)
			)
		"history_size":
			_history.size = (mouse - _history.global_position - _drag_offset).clamp(
				LOG_MINIMUM, viewport.max(LOG_MINIMUM)
			)
			_layout_history()
			_refresh_history()
		"chat_height":
			_edit_height = clampf(
				_entry.global_position.y - mouse.y + _drag_offset.y, 50, viewport.y - 87
			)
			_layout()
		"scroll":
			_set_scroll_from_y(mouse.y - _history_scroll.global_position.y - _drag_offset.y)


func snapshot() -> Dictionary:
	var shown: Array[String] = []
	var shown_colors: Array[String] = []
	for label: Label in _passive.get_children():
		shown.append(label.text)
		shown_colors.append(label.get_theme_color("font_color").to_html())
	var history: Array[String] = []
	for label: Label in _history_lines.get_children():
		history.append(label.text)
	var close_center := _history_close.get_global_rect().get_center()
	var resize_center := _history_resize.get_global_rect().get_center()
	return {
		"connected": _connected,
		"entry_visible": _entry.visible,
		"editing": _entry.visible,
		"focused": wants_keyboard(),
		"history_visible": _history.visible,
		"history_position": [_history.position.x, _history.position.y],
		"history_size": [_history.size.x, _history.size.y],
		"history_rect": _rect_values(_history),
		"history_close_center": [close_center.x, close_center.y],
		"history_resize_handle": [resize_center.x, resize_center.y],
		"input_rect": _rect_values(_chat_input),
		"history_input_rect": _rect_values(_history_input),
		"history_scroll_rect": _rect_values(_history_scroll),
		"history_scroll": _scroll_position,
		"history_lines": history,
		"passive_lines": shown,
		"passive_colors": shown_colors,
		"passive_visible_count": shown.size(),
		"message_count": _rows.size(),
		"feedback_count": _feedback.size(),
		"feedback_lines": _feedback.map(func(row: Dictionary): return row["display_text"]),
		"local_info_count": _local_info.size(),
		"show_normal": _show_normal,
		"show_info": _show_info,
		"input_limit": _chat_input.max_length,
		"entry_position": [_entry.position.x, _entry.position.y]
	}


func _rect_values(control: Control) -> Array:
	var rect := control.get_global_rect()
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]
