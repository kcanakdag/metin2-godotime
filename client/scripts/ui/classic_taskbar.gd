extends Control
## Native-pixel taskbar geometry from the pinned English client layout.

signal inventory_requested
signal system_requested
signal character_requested
signal slot_primary(slot: Control)
signal slot_secondary(slot: Control)
signal slot_dropped(slot: Control, row: Dictionary)
signal drag_started
signal item_hovered(row: Dictionary)
signal item_unhovered
signal settings_changed

const Art = preload("res://scripts/ui/classic_art.gd")
const Slot = preload("res://scripts/ui/classic_slot.gd")

var page := 0
var bindings: Array[int] = []
var _rows: Dictionary = {}
var _slots: Array[Control] = []
var _middle: Control
var _right: Control
var _base: TextureRect
var _hp_clip: Control
var _sp_clip: Control
var _xp_clips: Array[Control] = []
var _xp_points: Array[TextureRect] = []
var _xp_hover: Control
var _sp_hover: Control
var _page_number: TextureRect
var _character_button: TextureButton


func _ready() -> void:
	name = "TaskBar"
	mouse_filter = Control.MOUSE_FILTER_STOP
	bindings.resize(32)
	bindings.fill(0)
	set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	offset_top = -37
	_base = Art.tile(self, "pattern/taskbar_base", Rect2(263, 0, 256, 37))
	Art.image(self, "game/taskbar/gauge", Vector2(0, -10))
	Art.image(self, "game/taskbar/rampage_01/00", Vector2(8, -6))
	_hp_clip = Control.new()
	_hp_clip.position = Vector2(59, 4)
	_hp_clip.size = Vector2(95, 11)
	_hp_clip.clip_contents = true
	_hp_clip.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(_hp_clip)
	Art.image(_hp_clip, "pattern/hpgauge/01", Vector2.ZERO)
	_sp_clip = Control.new()
	_sp_clip.position = Vector2(59, 14)
	_sp_clip.size = Vector2(95, 11)
	_sp_clip.clip_contents = true
	_sp_clip.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(_sp_clip)
	Art.image(_sp_clip, "pattern/spgauge/01", Vector2.ZERO)
	Art.image(self, "game/taskbar/exp_gauge", Vector2(158, 0))
	for index in 4:
		var clip := Control.new()
		clip.position = Vector2(163 + index * 25, 9)
		clip.size = Vector2(19, 0)
		clip.clip_contents = true
		clip.mouse_filter = Control.MOUSE_FILTER_PASS
		add_child(clip)
		_xp_points.append(Art.image(clip, "game/taskbar/exp_gauge_point", Vector2.ZERO))
		_xp_clips.append(clip)
	_sp_hover = _hover_region(Vector2(59, 14), Vector2(95, 11))
	_xp_hover = _hover_region(Vector2(158, 0), Vector2(105, 37))
	_middle = Control.new()
	_middle.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_middle)
	_build_middle()
	_right = Control.new()
	_right.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_right)
	_build_right()
	resized.connect(_layout)
	_layout()


func _build_middle() -> void:
	Art.button(_middle, "game/taskbar/mouse_button_move_", Vector2(-42, 3), Callable())
	Art.button(_middle, "game/taskbar/mouse_button_camera_", Vector2(291, 3), Callable())
	var expand := Art.button(_middle, "game/taskbar/chat_button_", Vector2(128, 1), Callable())
	expand.disabled = true
	for index in 8:
		var at := Vector2(index % 4 * 32 + (142 if index >= 4 else 0), 3)
		Art.image(_middle, "public/slot_base", at)
		var slot := Slot.new()
		slot.position = at
		slot.size = Vector2(32, 32)
		slot.cell = index
		slot.kind = "quickslot"
		slot.primary.connect(func(control: Control) -> void: slot_primary.emit(control))
		slot.secondary.connect(func(control: Control) -> void: slot_secondary.emit(control))
		slot.dropped.connect(
			func(control: Control, row: Dictionary) -> void: slot_dropped.emit(control, row)
		)
		slot.drag_started.connect(func() -> void: drag_started.emit())
		slot.hovered.connect(func(row: Dictionary) -> void: item_hovered.emit(row))
		slot.unhovered.connect(func() -> void: item_unhovered.emit())
		_middle.add_child(slot)
		_slots.append(slot)
		var key := str(index + 1) if index < 4 else "f%d" % (index - 3)
		Art.image(slot, "game/taskbar/" + key, Vector2(3, 3))
	Art.image(_middle, "game/taskbar/quickslot_button_board", Vector2(273, 15))
	_page_number = Art.image(_middle, "game/taskbar/1", Vector2(275, 15))
	Art.button(_middle, "game/taskbar/quickslot_upbutton_", Vector2(273, 9), change_page.bind(-1))
	Art.button(_middle, "game/taskbar/quickslot_downbutton_", Vector2(273, 24), change_page.bind(1))


func _build_right() -> void:
	_character_button = Art.button(
		_right,
		"game/taskbar/character_button_",
		Vector2.ZERO,
		func() -> void: character_requested.emit()
	)
	_character_button.tooltip_text = "Character"
	var inventory := Art.button(
		_right,
		"game/taskbar/inventory_button_",
		Vector2(34, 0),
		func() -> void: inventory_requested.emit()
	)
	inventory.tooltip_text = "Inventory (I)"
	var messenger := Art.button(
		_right, "game/taskbar/community_button_", Vector2(68, 0), Callable()
	)
	messenger.tooltip_text = "Friends"
	messenger.disabled = true
	var system := Art.button(
		_right,
		"game/taskbar/system_button_",
		Vector2(102, 0),
		func() -> void: system_requested.emit()
	)
	system.tooltip_text = "System (Esc)"


func set_player(row: Dictionary) -> void:
	var health := int(row.get("health", 0))
	var maximum := int(row.get("max_health", 0))
	_hp_clip.size.x = 95 * clampf(float(health) / maxf(1, maximum), 0, 1)
	_hp_clip.tooltip_text = "HP: %d / %d" % [health, maximum]


func set_progression(row: Dictionary) -> void:
	var current_sp := int(row.get("current_sp", 0))
	var max_sp := int(row.get("max_sp", 0))
	_sp_clip.size.x = 95 * clampf(float(current_sp) / maxf(1, max_sp), 0, 1)
	_sp_hover.tooltip_text = "SP: %d / %d" % [current_sp, max_sp]
	var experience := int(row.get("experience", 0))
	var next_exp := int(row.get("next_exp", 0))
	var quarters := 0.0
	if next_exp > 0:
		var quarter_exp := maxi(1, next_exp / 4)
		quarters = clampf(float(experience) / quarter_exp, 0, 4)
	for index in _xp_clips.size():
		var height := 19.0 * clampf(quarters - index, 0, 1)
		# The original SetRenderingRect crops from the top. Move the clip and
		# texture together so the fixed-size orb fills upward without stretching.
		_xp_clips[index].position.y = 9 + 19 - height
		_xp_clips[index].size = Vector2(19, height)
		_xp_points[index].position.y = -(19 - height)
	var tooltip := "XP: —"
	if not row.is_empty():
		tooltip = (
			"XP: Maximum level"
			if next_exp == 0
			else "XP: %d / %d (%.2f%%)" % [experience, next_exp, experience * 100.0 / next_exp]
		)
	_xp_hover.tooltip_text = tooltip


func _hover_region(at: Vector2, dimensions: Vector2) -> Control:
	var result := Control.new()
	result.position = at
	result.size = dimensions
	result.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(result)
	return result


func set_rows(rows: Array) -> void:
	_rows.clear()
	for row: Dictionary in rows:
		_rows[int(row["id"])] = row
	_refresh()


func bind_item(index: int, row: Dictionary) -> void:
	bindings[page * 8 + index] = int(row.get("id", 0))
	_refresh()


func item_at(index: int) -> Dictionary:
	return _rows.get(bindings[page * 8 + index], {})


func change_page(direction: int) -> void:
	set_page(posmod(page + direction, 4))


func set_page(value: int) -> void:
	page = clampi(value, 0, 3)
	_page_number.texture = Art.texture("game/taskbar/%d" % (page + 1))
	_refresh()
	settings_changed.emit()


func snapshot() -> Dictionary:
	var centers: Array = []
	for slot in _slots:
		var point := slot.get_global_rect().get_center()
		centers.append([point.x, point.y])
	var xp_fills: Array = []
	for clip: Control in _xp_clips:
		var fill := {"height": clip.size.y, "top": clip.position.y, "width": clip.size.x}
		xp_fills.append(fill)
	var character_center := _character_button.get_global_rect().get_center()
	var xp_hover_center := _xp_hover.get_global_rect().get_center()
	var sp_hover_center := _sp_hover.get_global_rect().get_center()
	return {
		"page": page,
		"bindings": bindings,
		"slot_centers": centers,
		"hp_width": _hp_clip.size.x,
		"sp_width": _sp_clip.size.x,
		"xp_fills": xp_fills,
		"xp_tooltip": _xp_hover.tooltip_text,
		"xp_hover_tooltip": _xp_hover.tooltip_text,
		"xp_hover_center": [xp_hover_center.x, xp_hover_center.y],
		"sp_hover_tooltip": _sp_hover.tooltip_text,
		"sp_hover_center": [sp_hover_center.x, sp_hover_center.y],
		"character_center": [character_center.x, character_center.y],
	}


func _refresh() -> void:
	for index in _slots.size():
		_slots[index].set_item(item_at(index))


func _layout() -> void:
	_base.size.x = maxf(0, size.x - 263)
	_middle.position = Vector2(floorf(size.x / 2) - 86, 0)
	_right.position = Vector2(size.x - 144, 3)
