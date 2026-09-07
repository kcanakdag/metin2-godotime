class_name DevHud
extends CanvasLayer
## Classic Metin2 presentation and validated user intents; networking belongs to the session.

signal connect_requested(server_url: String, database: String, player_name: String)
signal disconnect_requested
signal change_character_requested
signal reconnect_requested
signal reset_identity_requested
signal attack_requested
signal pickup_requested
signal chat_submitted(message: String)
signal command_requested(command: String, request_id: String, argument: String)
signal debug_option_changed(option: String, value: Variant)
signal screenshot_requested
signal copy_diagnostics_requested
signal move_item_requested(item_id: int, cell: int)
signal equip_item_requested(item_id: int)
signal unequip_item_requested(item_id: int, cell: int)
signal use_item_requested(item_id: int)
signal stat_allocation_requested(character_id: String, stat_code: String)
signal combat_target_clear_requested

const Art = preload("res://scripts/ui/classic_art.gd")
const Inventory = preload("res://scripts/ui/classic_inventory.gd")
const Taskbar = preload("res://scripts/ui/classic_taskbar.gd")
const ItemTooltip = preload("res://scripts/ui/classic_tooltip.gd")
const MapPanel = preload("res://scripts/ui/classic_map_panel.gd")
const ChatPanel = preload("res://scripts/ui/classic_chat.gd")
const StatusPanel = preload("res://scripts/ui/classic_status.gd")
const TargetPanel = preload("res://scripts/ui/classic_target.gd")

const INK := Color(0.055, 0.065, 0.077, 0.96)
const BRONZE := Color(0.63, 0.47, 0.28)
const GOLD := Color(0.91, 0.75, 0.48)
const IVORY := Color(0.9, 0.88, 0.81)
const MUTED := Color(0.57, 0.62, 0.66)
const GREEN := Color(0.5, 0.79, 0.64)
const RED := Color(0.91, 0.4, 0.36)
const DIAGNOSTIC_FIELDS := {
	"fps": "Frames / second",
	"server_url": "Server",
	"database": "Database",
	"profile": "Local profile",
	"identity": "Identity",
	"players": "Players",
	"rx_messages": "Messages received",
	"tx_messages": "Messages sent",
	"snapshot_age_ms": "Last update age (ms)",
	"position": "Displayed position",
	"server_position": "Server position",
	"activity": "Activity",
	"world_tick_ms": "World tick (ms)",
}

var target_panel: Control

var _root: Control
var _connection: PanelContainer
var _server: LineEdit
var _database: LineEdit
var _player_name: LineEdit
var _profile: Label
var _connect_button: Button
var _retry_button: Button
var _reset_identity_button: Button
var _connection_message: Label
var _connection_state: Label
var _header_action: Button
var _world_name: Label
var _online_count: Label
var _chat_panel: Control
var _hotbar: Control
var _debug: PanelContainer
var _debug_values: Dictionary = {}
var _roster: Label
var _notice: Label
var _notice_timer: Timer
var _inventory: Control
var _tooltip: Control
var _carry_preview: TextureRect
var _carry: Dictionary = {}
var _inventory_rows: Array = []
var _profile_key := ""
var _minimap: Control
var _system: Control
var _system_buttons: Dictionary = {}
var _status: Control
var _connected := false
var _state := "disconnected"
var _account_entry := false


func _ready() -> void:
	layer = 10
	_root = Control.new()
	_root.name = "HUD"
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = _make_theme()
	add_child(_root)
	_build_connection()
	_build_chat()
	_build_hotbar()
	_build_target()
	_build_status()
	_build_inventory()
	_build_minimap()
	_build_system()
	_build_debug()
	_build_notice()
	get_viewport().size_changed.connect(_layout)
	_layout()
	set_connection_state("disconnected", "Choose a name and join the development map.")
	set_player_info({})


func set_connection_defaults(url: String, db: String, player_name: String, profile: String) -> void:
	_server.text = url
	_database.text = db
	_player_name.text = player_name
	_profile.text = "PROFILE  " + profile
	_profile.tooltip_text = "Profiles keep separate local identity tokens for multiple clients."


func set_connection_state(state: String, message: String) -> void:
	_state = state
	_connected = state == "connected"
	var busy := state in ["connecting", "subscribing", "joining"]
	_connection.visible = not _connected and not _account_entry
	_chat_panel.set_connected(_connected)
	_minimap.visible = _connected
	if not _connected:
		_inventory.hide()
		target_panel.clear_view()
		_status.set_connected(false)
		_minimap.close_top()
		_system.hide()
		_cancel_carry()
	_hotbar.visible = _connected
	_connection_state.text = state.to_upper()
	_connection_state.add_theme_color_override(
		"font_color", GREEN if _connected else (RED if state == "error" else GOLD)
	)
	_connection_message.text = message
	_connection_message.add_theme_color_override("font_color", RED if state == "error" else MUTED)
	if not _connected:
		_online_count.text = "— players"
	_connect_button.disabled = busy
	_connect_button.text = "Joining…" if busy else "ENTER WORLD"
	_retry_button.visible = state == "error"
	_reset_identity_button.visible = state == "error"
	_header_action.text = "Leave world" if _connected else "Connection"
	_header_action.disabled = busy
	for entry in [_server, _database, _player_name]:
		entry.editable = not busy


func set_world_info(info: Dictionary) -> void:
	_minimap.set_world_info(info)
	_world_name.text = str(
		info.get("map_name", info.get("display_name", info.get("name", "Development grounds")))
	)


func set_player_info(row: Dictionary) -> void:
	_hotbar.set_player(row)
	_status.set_player(row)
	_inventory.set_gold(int(row.get("gold", 0)))
	_minimap.set_player_info(row)


func set_progression(row: Dictionary) -> void:
	_hotbar.set_progression(row)
	_status.set_progression(row)


func set_players(rows: Array, local_identity: String) -> void:
	_minimap.set_players(rows, local_identity)
	_online_count.text = "%d %s" % [rows.size(), "player" if rows.size() == 1 else "players"]
	var names: PackedStringArray = []
	for row in rows:
		if not row is Dictionary:
			continue
		var player_name := str(row.get("name", row.get("player_name", "Warrior")))
		if str(row.get("identity", "")) == local_identity:
			player_name += "  (you)"
		names.append(player_name)
	_roster.text = "\n".join(names) if not names.is_empty() else "No players connected"


func set_chat(rows: Array) -> void:
	_chat_panel.set_chat(rows)


func set_command_feedback(rows: Array) -> void:
	_chat_panel.set_feedback(rows)


func _show_info(message: String) -> void:
	_chat_panel.add_local_info(message)


func set_diagnostics(data: Dictionary) -> void:
	for key in _debug_values:
		var value: Variant = data.get(key, "—")
		var text := str(value)
		if value is float:
			text = "%.1f" % value
		var label: Label = _debug_values[key]
		label.tooltip_text = text
		if key == "identity" and text.length() > 24:
			text = text.left(12) + "…" + text.right(8)
		label.text = text


func show_notice(message: String) -> void:
	_notice.text = message
	_notice.show()
	_notice_timer.start()


func toggle_debug() -> void:
	_debug.visible = not _debug.visible


func is_debug_visible() -> bool:
	return _debug.visible


func focus_chat() -> void:
	if _connected:
		_chat_panel.focus_chat()


func wants_keyboard() -> bool:
	var focused := get_viewport().gui_get_focus_owner()
	return focused is LineEdit or focused is TextEdit


func release_chat_focus() -> void:
	_chat_panel.close_input()


func set_account_entry(enabled: bool) -> void:
	_account_entry = enabled
	_connection.visible = not _connected and not enabled
	if enabled:
		get_viewport().gui_release_focus()


func _make_theme() -> Theme:
	var result := Theme.new()
	result.default_font_size = 15
	result.set_color("font_color", "Label", IVORY)
	result.set_color("default_color", "RichTextLabel", IVORY)
	result.set_stylebox("panel", "PanelContainer", _box(INK, BRONZE.darkened(0.4)))
	result.set_stylebox("normal", "Button", _box(Color(0.13, 0.14, 0.15), BRONZE))
	result.set_stylebox("hover", "Button", _box(Color(0.22, 0.2, 0.16), GOLD))
	result.set_stylebox("pressed", "Button", _box(Color(0.1, 0.1, 0.09), GOLD))
	result.set_stylebox("disabled", "Button", _box(Color(0.1, 0.11, 0.12), MUTED.darkened(0.6)))
	result.set_stylebox("focus", "Button", _box(Color.TRANSPARENT, GOLD))
	result.set_color("font_color", "Button", IVORY)
	result.set_color("font_hover_color", "Button", GOLD)
	result.set_color("font_disabled_color", "Button", MUTED.darkened(0.15))
	result.set_stylebox("normal", "LineEdit", _box(Color(0.035, 0.043, 0.052), MUTED.darkened(0.5)))
	result.set_stylebox("focus", "LineEdit", _box(Color(0.055, 0.065, 0.073), GOLD))
	result.set_stylebox("read_only", "LineEdit", _box(Color(0.06, 0.07, 0.08), MUTED.darkened(0.6)))
	result.set_color("font_color", "LineEdit", IVORY)
	result.set_color("font_placeholder_color", "LineEdit", MUTED)
	result.set_color("caret_color", "LineEdit", GOLD)
	result.set_constant("separation", "VBoxContainer", 10)
	result.set_constant("separation", "HBoxContainer", 10)
	return result


func _box(background: Color, border: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	return style


func _label(text: String, size: int = 15, color: Color = IVORY) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label


func _button(text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 36
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.pressed.connect(callback)
	return button


func _panel(parent: Node) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(panel)
	return panel


func _build_connection() -> void:
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.offset_top = 84
	center.offset_bottom = -16
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(center)
	_connection = _panel(center)
	_connection.custom_minimum_size.x = 440
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 11)
	_connection.add_child(column)
	column.add_child(_label("ENTER YONGAN", 21, GOLD))
	_connection_state = _label("DISCONNECTED", 13, GOLD)
	column.add_child(_connection_state)
	column.add_child(_label("A familiar world. A new foundation.", 14, MUTED))
	_server = _field(column, "SERVER ADDRESS", "http://127.0.0.1:3210")
	_database = _field(column, "DATABASE", "mt2-dev-world")
	if OS.has_feature("web"):
		_server.get_parent().hide()
		_database.get_parent().hide()
	_player_name = _field(column, "CHARACTER NAME", "Warrior")
	_player_name.max_length = 16
	_player_name.text_submitted.connect(func(_text: String) -> void: _on_connect())
	_profile = _label("PROFILE  default", 12, MUTED)
	column.add_child(_profile)
	_profile.visible = not OS.has_feature("web")
	_connection_message = _label("", 13, MUTED)
	_connection_message.custom_minimum_size.x = 410
	_connection_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_connection_message)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	_connect_button = _button("ENTER WORLD", _on_connect)
	_connect_button.custom_minimum_size.y = 42
	_connect_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions.add_child(_connect_button)
	_retry_button = _button("Retry", func() -> void: reconnect_requested.emit())
	actions.add_child(_retry_button)
	_reset_identity_button = _identity_reset_button()
	column.add_child(_reset_identity_button)


func _field(parent: Node, title: String, placeholder: String) -> LineEdit:
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 4)
	parent.add_child(column)
	column.add_child(_label(title, 11, MUTED))
	var field := LineEdit.new()
	field.placeholder_text = placeholder
	field.custom_minimum_size.y = 36
	column.add_child(field)
	return field


func _build_chat() -> void:
	_chat_panel = ChatPanel.new()
	_root.add_child(_chat_panel)
	_chat_panel.submitted.connect(_on_chat_input)


func _on_chat_input(message: String) -> void:
	if not message.begins_with("/"):
		chat_submitted.emit(message)
		return
	var separator := message.find(" ")
	var command := message if separator < 0 else message.left(separator)
	var argument := "" if separator < 0 else message.substr(separator + 1)
	if command == "/help" and not argument.is_empty():
		_show_info("Usage: /help")
		return
	if command not in ["/help", "/xp", "/level"]:
		_show_info("Unknown command. Use /help.")
		return
	var request_id := Crypto.new().generate_random_bytes(16).hex_encode()
	command_requested.emit(command.trim_prefix("/"), request_id, argument)


func _build_hotbar() -> void:
	_hotbar = Taskbar.new()
	_root.add_child(_hotbar)
	_hotbar.inventory_requested.connect(func() -> void: _inventory.toggle())
	_hotbar.character_requested.connect(_status_toggle)
	_hotbar.system_requested.connect(func() -> void: _system.visible = not _system.visible)
	_connect_slots(_hotbar)
	_hotbar.settings_changed.connect(_save_profile)


func _build_status() -> void:
	_status = StatusPanel.new()
	_root.add_child(_status)
	_status.allocation_requested.connect(
		func(character_id: String, stat_code: String):
			stat_allocation_requested.emit(character_id, stat_code)
	)
	_status.settings_changed.connect(_save_profile)


func _build_target() -> void:
	target_panel = TargetPanel.new()
	_root.add_child(target_panel)
	target_panel.clear_requested.connect(func() -> void: combat_target_clear_requested.emit())
	target_panel.presentation_failed.connect(show_notice)


func _status_toggle() -> void:
	if _connected:
		_status.toggle()


func _build_inventory() -> void:
	_inventory = Inventory.new()
	_root.add_child(_inventory)
	_connect_slots(_inventory)
	_inventory.settings_changed.connect(_save_profile)
	_tooltip = ItemTooltip.new()
	_root.add_child(_tooltip)
	_carry_preview = TextureRect.new()
	_carry_preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_carry_preview.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_carry_preview.z_index = 25
	_root.add_child(_carry_preview)


func _connect_slots(component: Control) -> void:
	component.slot_primary.connect(_on_slot_primary)
	component.slot_secondary.connect(_on_slot_secondary)
	component.slot_dropped.connect(_on_slot_dropped)
	component.drag_started.connect(_cancel_carry)
	component.item_hovered.connect(func(row: Dictionary) -> void: _tooltip.show_item(row))
	component.item_unhovered.connect(func() -> void: _tooltip.hide())


func _build_debug() -> void:
	_debug = _panel(_root)
	_debug.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_debug.offset_left = -450
	_debug.offset_right = -16
	_debug.offset_top = 91
	_debug.hide()
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_debug.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	var heading := HBoxContainer.new()
	column.add_child(heading)
	var title := _label("DEVELOPER TOOLS", 17, GOLD)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(title)
	heading.add_child(_button("Close · Ctrl+F3", toggle_debug))
	column.add_child(_label("Live session diagnostics", 12, MUTED))
	_world_name = _label("Yongan", 13)
	column.add_child(_world_name)
	_online_count = _label("0 players", 13)
	column.add_child(_online_count)
	_header_action = _button("Leave world", _on_header_action)
	column.add_child(_header_action)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 5)
	column.add_child(grid)
	for key in DIAGNOSTIC_FIELDS:
		grid.add_child(_label(DIAGNOSTIC_FIELDS[key], 12, MUTED))
		var value := _label("—", 12)
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		value.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
		value.custom_minimum_size.x = 170
		grid.add_child(value)
		_debug_values[key] = value
	_build_debug_options(column)
	column.add_child(_label("PLAYERS ON THIS MAP", 11, GOLD))
	_roster = _label("No players connected", 13)
	_roster.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_roster)


func _build_debug_options(column: VBoxContainer) -> void:
	column.add_child(HSeparator.new())
	for option in [
		["show_collision", "Show collision shapes", false], ["shadows", "Shadows", true]
	]:
		var toggle := CheckButton.new()
		toggle.text = option[1]
		toggle.button_pressed = option[2]
		toggle.toggled.connect(_on_debug_option.bind(option[0]))
		column.add_child(toggle)
	var distance_label := _label("Camera distance", 13, MUTED)
	column.add_child(distance_label)
	var distance := HSlider.new()
	distance.min_value = 5
	distance.max_value = 20
	distance.value = 10
	distance.step = 0.5
	distance.custom_minimum_size.y = 25
	distance.tooltip_text = "Camera distance in world units"
	distance.value_changed.connect(_on_debug_option.bind("camera_distance"))
	column.add_child(distance)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	actions.add_child(_button("Screenshot", func() -> void: screenshot_requested.emit()))
	actions.add_child(
		_button("Copy diagnostics", func() -> void: copy_diagnostics_requested.emit())
	)
	column.add_child(_identity_reset_button())


func _identity_reset_button() -> Button:
	var button := _button(
		"Reset identity · new character", func() -> void: reset_identity_requested.emit()
	)
	button.tooltip_text = (
		"Disconnect and clear this profile's saved login. "
		+ "Your next connection creates a new character."
	)
	return button


func _build_notice() -> void:
	_notice = _label("", 15, GOLD)
	_notice.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_notice.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	_notice.offset_left = -270
	_notice.offset_right = 270
	_notice.offset_top = 92
	_notice.add_theme_color_override("font_shadow_color", Color.BLACK)
	_notice.add_theme_constant_override("shadow_offset_x", 1)
	_notice.add_theme_constant_override("shadow_offset_y", 1)
	_notice.hide()
	_root.add_child(_notice)
	_notice_timer = Timer.new()
	_notice_timer.wait_time = 4.0
	_notice_timer.one_shot = true
	_notice_timer.timeout.connect(_notice.hide)
	add_child(_notice_timer)


func _layout() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	_debug.offset_bottom = maxf(300, viewport_size.y - 70)


func _on_header_action() -> void:
	if _connected:
		disconnect_requested.emit()
	else:
		_connection.show()
		_server.grab_focus()


func _on_connect() -> void:
	if _state in ["connecting", "subscribing", "joining"]:
		return
	if _server.text.strip_edges().is_empty() or _database.text.strip_edges().is_empty():
		show_notice("Enter the server address and database.")
		return
	if _player_name.text.strip_edges().is_empty():
		_player_name.grab_focus()
		show_notice("Choose a character name.")
		return
	connect_requested.emit(
		_server.text.strip_edges(), _database.text.strip_edges(), _player_name.text.strip_edges()
	)


func _on_debug_option(value: Variant, option: String) -> void:
	debug_option_changed.emit(option, value)


func _process(_delta: float) -> void:
	if not _carry.is_empty():
		_carry_preview.position = _root.get_global_mouse_position() - Vector2(16, 16)


func set_inventory(rows: Array) -> void:
	_inventory_rows = rows
	_inventory.set_rows(rows)
	_hotbar.set_rows(rows)
	if not _carry.is_empty() and _find_item(int(_carry["id"])).is_empty():
		_cancel_carry()


func handle_key(event: InputEventKey) -> bool:
	if not event.pressed or event.echo:
		return false
	if event.keycode == KEY_ESCAPE:
		if wants_keyboard():
			_chat_panel.close_input()
			get_viewport().gui_release_focus()
		elif not _carry.is_empty():
			_cancel_carry()
		elif _inventory.visible:
			_inventory.hide()
			_tooltip.hide()
		elif _minimap.close_top():
			pass
		elif _chat_panel.close_top():
			pass
		elif _status.close_top():
			pass
		elif _connected:
			_system.visible = not _system.visible
		return true
	if wants_keyboard() or not _connected or event.ctrl_pressed or event.alt_pressed:
		return false
	var toggles := {
		KEY_M: _minimap.toggle_atlas,
		KEY_L: _chat_panel.toggle_history,
		KEY_I: _inventory.toggle,
		KEY_C: _status_toggle,
	}
	if toggles.has(event.keycode):
		toggles[event.keycode].call()
		return true
	var slot_keys := [KEY_1, KEY_2, KEY_3, KEY_4, KEY_F1, KEY_F2, KEY_F3, KEY_F4]
	var index := slot_keys.find(event.keycode)
	if index >= 0:
		if event.shift_pressed and index < 4:
			_hotbar.set_page(index)
		else:
			_activate_item(_hotbar.item_at(index))
		return true
	return false


func inventory_snapshot() -> Dictionary:
	var result: Dictionary = _inventory.snapshot()
	var origin: Vector2 = _inventory.global_position
	var quick: Dictionary = _hotbar.snapshot()
	result["window_rect"] = [origin.x, origin.y, _inventory.size.x, _inventory.size.y]
	result["grid_origin"] = [origin.x + 8, origin.y + 246]
	result["equipment_origin"] = [origin.x + 16, origin.y + 39]
	result["quickslot_centers"] = quick["slot_centers"]
	result["quickslot_page"] = quick["page"]
	result["quickslot_bindings"] = quick["bindings"].duplicate()
	result["tab_centers"] = [[origin.x + 49, origin.y + 233], [origin.x + 127, origin.y + 233]]
	result["tooltip_visible"] = _tooltip.visible
	result["dragging"] = not _carry.is_empty() or get_viewport().gui_is_dragging()
	result["map"] = _minimap.snapshot()
	result["chat"] = _chat_panel.snapshot()
	result["status"] = _status.snapshot()
	result["target"] = target_panel.snapshot()
	result["taskbar"] = quick
	var system := {"visible": _system.is_visible_in_tree()}
	for key: String in _system_buttons:
		var center: Vector2 = _system_buttons[key].get_global_rect().get_center()
		system[key + "_center"] = [center.x, center.y]
	result["system"] = system
	return result


func _on_slot_primary(slot: Control) -> void:
	if not _carry.is_empty():
		_on_slot_dropped(slot, _carry)
	elif slot.kind == "quickslot":
		_activate_item(slot.row)
	elif not slot.row.is_empty():
		_carry = slot.row.duplicate()
		_carry_preview.texture = Art.item_icon(int(_carry["vnum"]))
		_carry_preview.show()
		_tooltip.hide()


func _on_slot_secondary(slot: Control) -> void:
	_cancel_carry()
	if slot.kind == "quickslot":
		_hotbar.bind_item(slot.cell, {})
		_save_profile()
	else:
		_activate_item(slot.row)


func _on_slot_dropped(slot: Control, row: Dictionary) -> void:
	var current := _find_item(int(row.get("id", 0)))
	_cancel_carry()
	if current.is_empty():
		return
	var item_id := int(current["id"])
	if slot.kind == "quickslot":
		_hotbar.bind_item(slot.cell, current)
		_save_profile()
	elif slot.kind == "equipment":
		equip_item_requested.emit(item_id)
	elif bool(current.get("equipped", false)):
		unequip_item_requested.emit(item_id, slot.cell)
	elif int(current["cell"]) != slot.cell:
		move_item_requested.emit(item_id, slot.cell)


func _activate_item(row: Dictionary) -> void:
	if row.is_empty():
		return
	var current := _find_item(int(row.get("id", 0)))
	if current.is_empty():
		return
	var item_id := int(current["id"])
	if int(current["vnum"]) == 10:
		if bool(current.get("equipped", false)):
			var cell: int = _inventory.first_free_cell(10)
			if cell >= 0:
				unequip_item_requested.emit(item_id, cell)
			else:
				show_notice("There is not enough space in your inventory.")
		else:
			equip_item_requested.emit(item_id)
	else:
		use_item_requested.emit(item_id)


func _find_item(item_id: int) -> Dictionary:
	for row: Dictionary in _inventory_rows:
		if int(row.get("id", 0)) == item_id:
			return row
	return {}


func _cancel_carry() -> void:
	_carry.clear()
	if is_instance_valid(_carry_preview):
		_carry_preview.hide()


func _build_minimap() -> void:
	_minimap = MapPanel.new()
	_root.add_child(_minimap)


func _build_system() -> void:
	_system = Control.new()
	_system.size = Vector2(200, 288)
	_root.add_child(_system)
	_system.set_anchors_and_offsets_preset(Control.PRESET_CENTER, Control.PRESET_MODE_KEEP_SIZE)
	Art.board(_system, _system.size, true)
	for entry in [
		["Help", 17, Callable()],
		["Item Shop", 57, Callable()],
		["System Options", 87, Callable()],
		["Game Options", 117, Callable()],
		["Change Character", 147, func() -> void: change_character_requested.emit()],
		["Logout", 177, func() -> void: disconnect_requested.emit()],
		["Exit Game", 217, func() -> void: disconnect_requested.emit()],
		["Cancel", 247, _system.hide]
	]:
		var button := Art.button(_system, "public/xlarge_button_", Vector2(10, entry[1]), entry[2])
		_system_buttons[str(entry[0]).to_lower().replace(" ", "_")] = button
		button.disabled = not entry[2].is_valid()
		var caption := Art.label(button, entry[0], Vector2.ZERO)
		caption.size = Vector2(180, 30)
		caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_system.hide()


func set_profile(key: String) -> void:
	if key == _profile_key:
		return
	_save_profile()
	_profile_key = ""
	_hotbar.bindings.fill(0)
	_hotbar.set_page(0)
	_inventory.restore_settings({})
	_status.restore_settings({})
	if key.length() != 64 or not key.is_valid_hex_number():
		return
	var path := "user://ui/" + key + ".json"
	if FileAccess.file_exists(path):
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if data is Dictionary:
			var bindings: Variant = data.get("bindings", [])
			if bindings is Array and bindings.size() == 32:
				for index in 32:
					_hotbar.bindings[index] = maxi(0, int(bindings[index]))
			_hotbar.set_page(int(data.get("quickslot_page", 0)))
			_inventory.restore_settings(data)
			_status.restore_settings(data)
	_profile_key = key


func _save_profile() -> void:
	if _profile_key.is_empty():
		return
	DirAccess.make_dir_recursive_absolute("user://ui")
	var file := FileAccess.open("user://ui/" + _profile_key + ".json", FileAccess.WRITE)
	if file:
		var data := {
			"bindings": _hotbar.bindings,
			"quickslot_page": _hotbar.page,
			"inventory_page": _inventory.page,
			"inventory_position": [_inventory.position.x, _inventory.position.y],
			"status_position": [_status.position.x, _status.position.y],
		}
		file.store_string(JSON.stringify(data))
