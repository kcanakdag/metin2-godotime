extends Control
## Native-pixel taskbar geometry from the pinned English client layout.

signal inventory_requested
signal system_requested
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
var _page_number: TextureRect


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
	Art.image(self, "game/taskbar/exp_gauge", Vector2(158, 0))
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
	var character := Art.button(_right, "game/taskbar/character_button_", Vector2.ZERO, Callable())
	character.tooltip_text = "Character"
	character.disabled = true
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
	var health := float(row.get("health", 0))
	var maximum := maxf(1, float(row.get("max_health", 100)))
	_hp_clip.size.x = 95 * clampf(health / maximum, 0, 1)
	_hp_clip.tooltip_text = "HP: %d / %d" % [health, maximum]


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
	return {"page": page, "bindings": bindings, "slot_centers": centers}


func _refresh() -> void:
	for index in _slots.size():
		_slots[index].set_item(item_at(index))


func _layout() -> void:
	_base.size.x = maxf(0, size.x - 263)
	_middle.position = Vector2(floorf(size.x / 2) - 86, 0)
	_right.position = Vector2(size.x - 144, 3)
