class_name DevHud
extends CanvasLayer
## Runtime HUD: presentation and user intent only; networking belongs to the client session.

signal connect_requested(server_url: String, database: String, player_name: String)
signal disconnect_requested
signal reconnect_requested
signal reset_identity_requested
signal attack_requested
signal pickup_requested
signal chat_submitted(message: String)
signal debug_option_changed(option: String, value: Variant)
signal screenshot_requested
signal copy_diagnostics_requested

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
var _chat_panel: PanelContainer
var _chat_log: RichTextLabel
var _chat_input: LineEdit
var _hotbar: PanelContainer
var _attack_button: Button
var _health: ProgressBar
var _health_text: Label
var _character_name: Label
var _debug: PanelContainer
var _debug_values: Dictionary = {}
var _roster: Label
var _notice: Label
var _notice_timer: Timer
var _connected := false
var _state := "disconnected"


func _ready() -> void:
	layer = 10
	_root = Control.new()
	_root.name = "HUD"
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = _make_theme()
	add_child(_root)
	_build_header()
	_build_connection()
	_build_chat()
	_build_hotbar()
	_build_debug()
	_build_notice()
	_allow_world_input(_root)
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
	_connection.visible = not _connected
	_chat_panel.visible = _connected
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
	_attack_button.disabled = not _connected
	_chat_input.editable = _connected
	_chat_input.placeholder_text = "Enter to chat…" if _connected else "Connect to chat"
	for entry in [_server, _database, _player_name]:
		entry.editable = not busy


func set_world_info(info: Dictionary) -> void:
	_world_name.text = str(
		info.get("map_name", info.get("display_name", info.get("name", "Development grounds")))
	)


func set_player_info(row: Dictionary) -> void:
	var hp := float(row.get("hp", row.get("health", 0)))
	var max_hp := maxf(1.0, float(row.get("max_hp", row.get("max_health", 100))))
	_health.max_value = max_hp
	_health.value = hp
	_health_text.text = "%d / %d" % [hp, max_hp]
	_character_name.text = (
		"%s  ·  %d gold%s"
		% [
			row.get("name", "Warrior"),
			row.get("gold", 0),
			"  · Respawning…" if hp == 0 and not row.is_empty() else ""
		]
	)


func set_players(rows: Array, local_identity: String) -> void:
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
	var lines: PackedStringArray = []
	for row in rows.slice(maxi(0, rows.size() - 60)):
		if row is Dictionary:
			lines.append(
				(
					"%s: %s"
					% [
						row.get("sender_name", row.get("name", "Player")),
						row.get("message", row.get("text", ""))
					]
				)
			)
	_chat_log.text = "\n".join(lines)


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
		_chat_input.grab_focus()


func wants_keyboard() -> bool:
	var focused := get_viewport().gui_get_focus_owner()
	return focused is LineEdit or focused is TextEdit


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


func _allow_world_input(node: Node) -> void:
	if node is Container and not node is ScrollContainer:
		node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for child in node.get_children():
		_allow_world_input(child)


func _build_header() -> void:
	var panel := _panel(_root)
	panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	panel.offset_left = 16
	panel.offset_right = -16
	panel.offset_top = 14
	var row := HBoxContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(row)
	var title := VBoxContainer.new()
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_constant_override("separation", 3)
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(title)
	title.add_child(_label("METIN2 / SPACETIME", 18, GOLD))
	_world_name = _label("Development grounds", 13, MUTED)
	title.add_child(_world_name)
	var status := VBoxContainer.new()
	status.add_theme_constant_override("separation", 3)
	status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(status)
	_connection_state = _label("DISCONNECTED", 13, GOLD)
	status.add_child(_connection_state)
	_online_count = _label("0 players", 13, MUTED)
	status.add_child(_online_count)
	_header_action = _button("Connection", _on_header_action)
	row.add_child(_header_action)
	row.add_child(_button("F3 · Tools", toggle_debug))


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
	_chat_panel = _panel(_root)
	_chat_panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_chat_panel.offset_left = 16
	_chat_panel.offset_right = 410
	_chat_panel.offset_top = -207
	_chat_panel.offset_bottom = -16
	var column := VBoxContainer.new()
	_chat_panel.add_child(column)
	column.add_child(_label("LOCAL CHAT", 11, GOLD))
	_chat_log = RichTextLabel.new()
	_chat_log.bbcode_enabled = false
	_chat_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_chat_log.custom_minimum_size.y = 90
	_chat_log.scroll_following = true
	_chat_log.add_theme_font_size_override("normal_font_size", 14)
	column.add_child(_chat_log)
	_chat_input = LineEdit.new()
	_chat_input.max_length = 160
	_chat_input.custom_minimum_size.y = 34
	_chat_input.text_submitted.connect(_on_chat)
	column.add_child(_chat_input)


func _build_hotbar() -> void:
	_hotbar = _panel(_root)
	_hotbar.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 7)
	_hotbar.add_child(column)
	_character_name = _label("Warrior", 13, GOLD)
	column.add_child(_character_name)
	_health = ProgressBar.new()
	_health.custom_minimum_size.y = 23
	_health.show_percentage = false
	_health.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_health.add_theme_stylebox_override("background", _box(Color(0.14, 0.035, 0.045), BRONZE))
	var fill := _box(Color(0.64, 0.10, 0.12), Color(0.78, 0.22, 0.18))
	fill.content_margin_top = 0
	fill.content_margin_bottom = 0
	_health.add_theme_stylebox_override("fill", fill)
	column.add_child(_health)
	_health_text = _label("0 / 100", 12)
	_health_text.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_health_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_health_text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_health.add_child(_health_text)
	var row := HBoxContainer.new()
	column.add_child(row)
	_attack_button = _button("ATTACK  [Space]", func() -> void: attack_requested.emit())
	_attack_button.custom_minimum_size = Vector2(150, 44)
	row.add_child(_attack_button)
	row.add_child(_button("LOOT [E]", func(): pickup_requested.emit()))
	var help := _label("WASD / click · Move\nEnter · Chat   F3 · Tools", 12, MUTED)
	help.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(help)


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
	heading.add_child(_button("Close · F3", toggle_debug))
	column.add_child(_label("Live session diagnostics", 12, MUTED))
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
	var size := get_viewport().get_visible_rect().size
	_chat_panel.offset_right = minf(410, size.x * 0.42)
	var anchor := 0.5 if size.x >= 1180 else 1.0
	_hotbar.anchor_left = anchor
	_hotbar.anchor_right = anchor
	_hotbar.offset_left = -184 if anchor == 0.5 else -384
	_hotbar.offset_right = 184 if anchor == 0.5 else -16
	_hotbar.offset_top = -160
	_hotbar.offset_bottom = -16
	_debug.offset_bottom = maxf(300, size.y - 184)


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


func _on_chat(message: String) -> void:
	var trimmed := message.strip_edges()
	if not trimmed.is_empty() and _connected:
		chat_submitted.emit(trimmed)
		_chat_input.clear()


func _on_debug_option(value: Variant, option: String) -> void:
	debug_option_changed.emit(option, value)
