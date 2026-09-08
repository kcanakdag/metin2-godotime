extends Control
## Original-sized character status page backed only by subscribed server state.

signal allocation_requested(character_id: String, stat_code: String)
signal settings_changed
signal skills_requested

const Art = preload("res://scripts/ui/classic_art.gd")
const DIMENSIONS := Vector2(253, 361)
const STAT_ROWS := [
	{"code": "ht", "field": "vitality", "label": "VIT"},
	{"code": "iq", "field": "intelligence", "label": "INT"},
	{"code": "st", "field": "strength", "label": "STR"},
	{"code": "dx", "field": "dexterity", "label": "DEX"},
]

var _player: Dictionary = {}
var _progression: Dictionary = {}
var _labels: Dictionary = {}
var _plus_buttons: Dictionary = {}
var _tab_rects: Array[Control] = []
var _bars: Array[Control] = []
var _points_art: TextureRect
var _portrait: TextureRect
var _moving := false
var _move_offset := Vector2.ZERO
var _placed := false


func _ready() -> void:
	name = "CharacterStatus"
	size = DIMENSIONS
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 12
	Art.board(self, DIMENSIONS)
	_build_header()
	_build_status_page()
	_build_tabs()
	get_viewport().size_changed.connect(_on_viewport_resized)
	_place_default()
	_refresh()
	hide()


func _process(_delta: float) -> void:
	if not _moving:
		return
	position = (get_global_mouse_position() - _move_offset).clamp(
		Vector2.ZERO, get_viewport_rect().size - Vector2(40, 40)
	)
	if not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
		_moving = false
		settings_changed.emit()


func _build_header() -> void:
	Art.image(self, "game/windows/box_face", Vector2(7, 7))
	_portrait = Art.image(self, "icon/face/warrior_m", Vector2(11, 11))
	var title_host := Control.new()
	title_host.position = Vector2(53, 0)
	title_host.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(title_host)
	var title := Art.title(title_host, "Character", 185, hide)
	title.gui_input.connect(_on_title_input)
	Art.image(self, "public/parameter_slot_03", Vector2(60, 34))
	Art.image(self, "public/parameter_slot_03", Vector2(153, 34))
	_add_value("guild", "—", Vector2(60, 34), 90)
	_add_value("name", "", Vector2(153, 34), 90)


func _build_status_page() -> void:
	Art.image(self, "locale/en/ui/windows/label_level", Vector2(12, 61))
	Art.image(self, "locale/en/ui/windows/label_cur_exp", Vector2(56, 61))
	Art.image(self, "locale/en/ui/windows/label_last_exp", Vector2(153, 61))
	_add_value("level", "—", Vector2(12, 80), 37)
	_add_value("experience", "—", Vector2(59, 80), 86)
	_add_value("remaining_exp", "—", Vector2(154, 80), 90)
	_bars.append(Art.horizontal_bar(self, Rect2(15, 108, 223, 17)))
	Art.image(self, "locale/en/ui/windows/label_std", Vector2(16, 109))
	_points_art = Art.image(self, "locale/en/ui/windows/label_uppt", Vector2(153, 111))
	_add_value("unspent_stat_points", "—", Vector2(203, 111), 24)
	Art.image(self, "locale/en/ui/windows/label_std_item1", Vector2(20, 131))
	for index in STAT_ROWS.size():
		var entry: Dictionary = STAT_ROWS[index]
		var y := 132.0 + index * 23.0
		Art.image(self, "public/parameter_slot_00", Vector2(53, y))
		_add_value(str(entry.field), "—", Vector2(53, y + 3), 39)
		var plus := _plus_button(Vector2(94, 135 + index * 23), str(entry.code))
		plus.name = "Allocate" + str(entry.label)
		_plus_buttons[str(entry.code)] = plus
	var combat := ["health", "sp", "attack", "defense"]
	Art.image(self, "locale/en/ui/windows/label_std_item2", Vector2(103, 130))
	for index in combat.size():
		var y := 132.0 + index * 23.0
		Art.image(self, "public/parameter_slot_03", Vector2(148, y))
		_add_value(str(combat[index]), "—", Vector2(148, y + 3), 90)
	_bars.append(Art.horizontal_bar(self, Rect2(15, 227, 223, 17)))
	Art.image(self, "locale/en/ui/windows/label_ext", Vector2(16, 229))
	Art.image(self, "locale/en/ui/windows/label_ext_item1", Vector2(14, 252))
	Art.image(self, "locale/en/ui/windows/label_ext_item2", Vector2(131, 253))
	var left_details := ["move", "attack_speed", "cast_speed"]
	var right_details := ["magic_attack", "magic_defense", "evasion"]
	for index in 3:
		var y := 254.0 + index * 23.0
		Art.image(self, "public/parameter_slot_01", Vector2(69, y))
		_add_value(left_details[index], "—", Vector2(69, y + 3), 52)
		Art.image(self, "public/parameter_slot_01", Vector2(186, y))
		_add_value(right_details[index], "—", Vector2(186, y + 3), 52)


func _build_tabs() -> void:
	Art.image(self, "locale/en/ui/windows/tab_1", Vector2(0, 328))
	for entry in [
		[Vector2(6, 333), Vector2(53, 27), "Status"],
		[Vector2(61, 333), Vector2(67, 27), "Skills (K)"],
		[Vector2(130, 333), Vector2(61, 27), "Actions are not available yet"],
		[Vector2(192, 333), Vector2(55, 27), "Quests are not available yet"],
	]:
		var tab := Control.new()
		tab.position = entry[0]
		tab.size = entry[1]
		tab.mouse_filter = Control.MOUSE_FILTER_STOP
		tab.tooltip_text = entry[2]
		if entry[2] == "Skills (K)":
			tab.gui_input.connect(
				func(event):
					if (
						event is InputEventMouseButton
						and event.button_index == MOUSE_BUTTON_LEFT
						and event.pressed
					):
						hide()
						skills_requested.emit()
			)
		add_child(tab)
		_tab_rects.append(tab)


func _plus_button(at: Vector2, stat_code: String) -> TextureButton:
	var button := TextureButton.new()
	button.position = at
	button.size = Vector2(13, 13)
	button.texture_normal = Art.texture("game/windows/btn_plus_up")
	button.texture_hover = Art.texture("game/windows/btn_plus_over")
	button.texture_pressed = Art.texture("game/windows/btn_plus_down")
	button.texture_disabled = button.texture_normal
	button.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	button.focus_mode = Control.FOCUS_NONE
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.pressed.connect(_on_allocate.bind(stat_code))
	add_child(button)
	return button


func _add_value(key: String, text: String, at: Vector2, width: float) -> void:
	var label := Art.label(self, text, at)
	label.size = Vector2(width, 17)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_labels[key] = label


func set_player(row: Dictionary) -> void:
	_player = row.duplicate(true)
	_refresh()


func set_appearance(row: Dictionary) -> void:
	var class_id := int(row.get("character_class", -1))
	var sex := int(row.get("sex", -1))
	_portrait.visible = class_id in range(4) and sex in [0, 1]
	if _portrait.visible:
		var source_class: String = ["warrior", "assassin", "sura", "shaman"][class_id]
		_portrait.texture = Art.texture(
			"icon/face/%s_%s" % [source_class, "m" if sex == 0 else "w"]
		)


func set_progression(row: Dictionary) -> void:
	_progression = row.duplicate(true)
	_refresh()


func set_connected(value: bool) -> void:
	if not value:
		hide()
		_player.clear()
		_progression.clear()
	_refresh()


func toggle() -> void:
	if not _placed:
		_place_default()
		_placed = true
	visible = not visible
	if visible:
		move_to_front()


func close_top() -> bool:
	if not visible:
		return false
	hide()
	return true


func _refresh() -> void:
	if not is_node_ready():
		return
	_labels.name.text = str(_player.get("name", ""))
	_labels.guild.text = "—"
	if _progression.is_empty():
		for key in [
			"level",
			"experience",
			"remaining_exp",
			"vitality",
			"intelligence",
			"strength",
			"dexterity",
			"sp",
			"unspent_stat_points",
		]:
			_labels[key].text = "—"
	else:
		var experience := int(_progression.get("experience", 0))
		var next_exp := int(_progression.get("next_exp", 0))
		_labels.level.text = str(int(_progression.get("level", 0)))
		_labels.experience.text = str(experience)
		_labels.remaining_exp.text = str(maxi(0, next_exp - experience))
		for entry: Dictionary in STAT_ROWS:
			_labels[str(entry.field)].text = str(int(_progression.get(entry.field, 0)))
		_labels.unspent_stat_points.text = str(int(_progression.get("unspent_stat_points", 0)))
		_labels.sp.text = (
			"%d/%d" % [int(_progression.get("current_sp", 0)), int(_progression.get("max_sp", 0))]
		)
		_labels.remaining_exp.tooltip_text = (
			"Maximum level" if next_exp == 0 else "EXP needed for the next level"
		)
	var health := int(_player.get("health", 0))
	var max_health := int(_player.get("max_health", 0))
	_labels.health.text = "%d/%d" % [health, max_health] if max_health > 0 else "—"
	if _progression.is_empty():
		_labels.attack.text = "—"
		_labels.defense.text = "—"
	else:
		_labels.attack.text = _attack_value_text(
			int(_progression.get("display_attack_min", 0)),
			int(_progression.get("display_attack_max", 0))
		)
		_labels.defense.text = str(int(_progression.get("display_defense", 0)))
	_labels.attack_speed.text = (
		"—" if _progression.is_empty() else str(int(_progression.get("display_attack_speed", 100)))
	)
	_labels.attack.tooltip_text = "Equipped-weapon Attack. Actual damage depends on the target."
	for key in [
		"move",
		"cast_speed",
		"magic_attack",
		"magic_defense",
		"evasion",
	]:
		_labels[key].text = "—"
	_refresh_buttons()


func _attack_value_text(minimum: int, maximum: int) -> String:
	return str(minimum) if minimum == maximum else "%d-%d" % [minimum, maximum]


func _refresh_buttons() -> void:
	var points := int(_progression.get("unspent_stat_points", 0))
	var show_points := not _progression.is_empty() and points > 0
	_points_art.visible = show_points
	_labels.unspent_stat_points.visible = show_points
	for entry: Dictionary in STAT_ROWS:
		var code := str(entry.code)
		var value := int(_progression.get(entry.field, 0))
		var button: TextureButton = _plus_buttons[code]
		button.visible = show_points and value < 90
		button.disabled = not button.visible
		if _progression.is_empty():
			button.tooltip_text = "Waiting for authoritative progression."
		elif value >= 90:
			button.tooltip_text = "Maximum 90 reached."
		elif points <= 0:
			button.tooltip_text = "No stat points available."
		else:
			button.tooltip_text = "Allocate one point."


func _on_allocate(stat_code: String) -> void:
	var button: TextureButton = _plus_buttons.get(stat_code)
	var character_id := str(_progression.get("character_id", ""))
	if button == null or button.disabled or character_id.is_empty():
		return
	allocation_requested.emit(character_id, stat_code)


func _place_default() -> void:
	var viewport := get_viewport_rect().size
	position = Vector2(24, maxf(0, (viewport.y - 37 - DIMENSIONS.y) / 2))


func _on_viewport_resized() -> void:
	position = position.clamp(Vector2.ZERO, get_viewport_rect().size - Vector2(40, 40))


func restore_settings(data: Dictionary) -> void:
	_placed = false
	_place_default()
	var saved: Variant = data.get("status_position", [])
	if saved is Array and saved.size() == 2:
		var restored := Vector2(float(saved[0]), float(saved[1]))
		if restored.is_finite():
			position = restored.clamp(Vector2.ZERO, get_viewport_rect().size - Vector2(40, 40))
			_placed = true


func _on_title_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_moving = event.pressed
		_move_offset = get_global_mouse_position() - global_position
		if event.pressed:
			move_to_front()
		accept_event()


func snapshot() -> Dictionary:
	var buttons: Dictionary = {}
	for code: String in _plus_buttons:
		var button: TextureButton = _plus_buttons[code]
		var center := button.get_global_rect().get_center()
		buttons[code] = {
			"center": [center.x, center.y],
			"disabled": button.disabled,
			"visible": button.visible,
			"tooltip": button.tooltip_text,
		}
	var values: Dictionary = {}
	for key: String in _labels:
		values[key] = _labels[key].text
	var tabs: Array = []
	for tab: Control in _tab_rects:
		var rect := tab.get_global_rect()
		tabs.append([rect.position.x, rect.position.y, rect.size.x, rect.size.y])
	var bars: Array = []
	for bar: Control in _bars:
		var rect := bar.get_global_rect()
		var right: TextureRect = bar.get_child(2)
		var right_rect := right.get_global_rect()
		(
			bars
			. append(
				{
					"rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y],
					"right":
					[
						right_rect.position.x,
						right_rect.position.y,
						right_rect.size.x,
						right_rect.size.y,
					],
				}
			)
		)
	return {
		"visible": visible,
		"rect": [position.x, position.y, size.x, size.y],
		"values": values,
		"plus": buttons,
		"character_id": str(_progression.get("character_id", "")),
		"points_visible": _labels.unspent_stat_points.visible,
		"loading": _progression.is_empty(),
		"tab_rects": tabs,
		"bars": bars,
	}
