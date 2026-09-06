extends Control
## Original 176 × 565 inventory layout. Items change only after server confirmation.

signal slot_primary(slot: Control)
signal slot_secondary(slot: Control)
signal slot_dropped(slot: Control, row: Dictionary)
signal drag_started
signal item_hovered(row: Dictionary)
signal item_unhovered
signal settings_changed

const Art = preload("res://scripts/ui/classic_art.gd")
const Slot = preload("res://scripts/ui/classic_slot.gd")
const DIMENSIONS := Vector2(176, 565)
const GRID_ORIGIN := Vector2(8, 246)

var page := 0
var _rows: Array = []
var _items: Control
var _weapon: Control
var _money: Label
var _tabs: Array[TextureButton] = []
var _moving := false
var _move_offset := Vector2.ZERO
var _placed := false


func _ready() -> void:
	name = "InventoryWindow"
	size = DIMENSIONS
	position = Vector2(get_viewport_rect().size.x - 176, maxf(0, get_viewport_rect().size.y - 602))
	mouse_filter = Control.MOUSE_FILTER_STOP
	Art.board(self, DIMENSIONS)
	var title := Art.title(self, "Inventory", 161, hide)
	title.gui_input.connect(_on_title_input)
	Art.image(self, "equipment_bg_without_ring", Vector2(10, 33))
	_build_equipment()
	for index in 2:
		var tab := Art.button(
			self,
			"game/windows/tab_button_large_",
			Vector2(10 + index * 78, 224),
			set_page.bind(index)
		)
		tab.toggle_mode = true
		var caption := Art.label(tab, "I" if index == 0 else "II", Vector2.ZERO)
		caption.size = Vector2(78, 20)
		caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_tabs.append(tab)
	for index in 45:
		Art.image(self, "public/slot_base", GRID_ORIGIN + Vector2(index % 5, index / 5) * 32)
	_items = Control.new()
	_items.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_items)
	Art.image(self, "public/parameter_slot_05", Vector2(26, 537))
	Art.image(self, "game/windows/money_icon", Vector2(8, 539))
	_money = Art.label(self, "0", Vector2(29, 540))
	_money.size.x = 134
	_money.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	set_page(0)
	hide()


func _process(_delta: float) -> void:
	if _moving:
		position = get_global_mouse_position() - _move_offset
		position = position.clamp(Vector2.ZERO, get_viewport_rect().size - Vector2(40, 40))
		if not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
			_moving = false
			settings_changed.emit()


func _build_equipment() -> void:
	_weapon = _slot(self, 255, "equipment", Vector2(16, 39), Vector2(32, 96))
	for entry in [
		["dragonsoul/dss_inventory_button_", Vector2(124, 140)],
		["game/taskbar/mall_button_", Vector2(128, 181)],
		["game/costume_button_", Vector2(88, 38)]
	]:
		var control := Art.button(self, entry[0], entry[1], Callable())
		control.disabled = true
	for index in 2:
		var control := Art.button(
			self, "game/windows/tab_button_small_", Vector2(96 + 32 * index, 194), Callable()
		)
		control.disabled = true
		var caption := Art.label(control, "I" if index == 0 else "II", Vector2.ZERO)
		caption.size = Vector2(32, 20)
		caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER


func _slot(parent: Node, cell: int, kind: String, at: Vector2, dimensions: Vector2) -> Control:
	var result := Slot.new()
	result.cell = cell
	result.kind = kind
	result.position = at
	result.size = dimensions
	result.primary.connect(func(slot: Control) -> void: slot_primary.emit(slot))
	result.secondary.connect(func(slot: Control) -> void: slot_secondary.emit(slot))
	result.dropped.connect(
		func(slot: Control, row: Dictionary) -> void: slot_dropped.emit(slot, row)
	)
	result.drag_started.connect(func() -> void: drag_started.emit())
	result.hovered.connect(func(row: Dictionary) -> void: item_hovered.emit(row))
	result.unhovered.connect(func() -> void: item_unhovered.emit())
	parent.add_child(result)
	return result


func set_rows(rows: Array) -> void:
	_rows = rows
	if not is_node_ready():
		return
	for child in _items.get_children():
		_items.remove_child(child)
		child.queue_free()
	_weapon.set_item({})
	var occupied: Dictionary = {}
	for row: Dictionary in rows:
		if bool(row.get("equipped", false)):
			_weapon.set_item(row)
			continue
		var cell := int(row.get("cell", 0))
		if cell / 45 != page:
			continue
		var local_cell := cell % 45
		var height := Art.item_height(int(row.get("vnum", 0)))
		for offset in height:
			occupied[local_cell + offset * 5] = true
		var slot := _slot(
			_items,
			cell,
			"bag",
			GRID_ORIGIN + Vector2(local_cell % 5, local_cell / 5) * 32,
			Vector2(32, height * 32)
		)
		slot.set_item(row)
	for cell in 45:
		if not occupied.has(cell):
			_slot(
				_items,
				page * 45 + cell,
				"bag",
				GRID_ORIGIN + Vector2(cell % 5, cell / 5) * 32,
				Vector2(32, 32)
			)


func set_page(value: int) -> void:
	page = clampi(value, 0, 1)
	for index in _tabs.size():
		_tabs[index].button_pressed = index == page
	set_rows(_rows)
	settings_changed.emit()


func set_gold(amount: int) -> void:
	_money.text = str(amount)


func toggle() -> void:
	if not _placed:
		position = Vector2(get_viewport_rect().size.x - 176, get_viewport_rect().size.y - 602)
		position.y = maxf(0, position.y)
		_placed = true
	visible = not visible
	if visible:
		move_to_front()


func first_free_cell(vnum: int) -> int:
	var occupied: Dictionary = {}
	for row: Dictionary in _rows:
		if bool(row.get("equipped", false)):
			continue
		for offset in Art.item_height(int(row.get("vnum", 0))):
			occupied[int(row["cell"]) + offset * 5] = true
	var height := Art.item_height(vnum)
	for cell in 90:
		if cell % 45 / 5 + height > 9:
			continue
		var free := true
		for offset in height:
			if occupied.has(cell + offset * 5):
				free = false
		if free:
			return cell
	return -1


func snapshot() -> Dictionary:
	var centers: Array = []
	for cell in 45:
		var point := (
			global_position + GRID_ORIGIN + Vector2(cell % 5, cell / 5) * 32 + Vector2(16, 16)
		)
		centers.append([point.x, point.y])
	var weapon := _weapon.get_global_rect().get_center()
	return {
		"visible": visible,
		"page": page,
		"position": [position.x, position.y],
		"size": [size.x, size.y],
		"slot_centers": centers,
		"weapon_center": [weapon.x, weapon.y]
	}


func _on_title_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_moving = event.pressed
		_move_offset = get_global_mouse_position() - global_position
		if event.pressed:
			move_to_front()
		accept_event()


func restore_settings(data: Dictionary) -> void:
	_placed = false
	position = Vector2(get_viewport_rect().size.x - 176, maxf(0, get_viewport_rect().size.y - 602))
	set_page(int(data.get("inventory_page", 0)))
	var saved: Variant = data.get("inventory_position", [])
	if saved is Array and saved.size() == 2:
		var restored := Vector2(float(saved[0]), float(saved[1]))
		if restored.is_finite():
			position = restored.clamp(Vector2.ZERO, get_viewport_rect().size - Vector2(40, 40))
			_placed = true
