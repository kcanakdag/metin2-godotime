extends Control
## A slot sends item intents; the server subscription supplies its displayed contents.

signal primary(slot: Control)
signal secondary(slot: Control)
signal dropped(slot: Control, row: Dictionary)
signal drag_started
signal hovered(row: Dictionary)
signal unhovered

const Art = preload("res://scripts/ui/classic_art.gd")

var row: Dictionary = {}
var cell := 0
var kind := "bag"
var _icon: TextureRect
var _count: Label
var _highlight: ColorRect
var _click_pending := false


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	_icon = TextureRect.new()
	_icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(_icon)
	_count = Art.label(self, "", Vector2.ZERO, Color.WHITE)
	_count.add_theme_font_size_override("font_size", 11)
	_highlight = ColorRect.new()
	_highlight.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_highlight.color = Color(1, 1, 1, 0.15)
	_highlight.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_highlight.hide()
	add_child(_highlight)
	mouse_entered.connect(_on_enter)
	mouse_exited.connect(_on_exit)
	set_item(row)


func set_item(value: Dictionary) -> void:
	row = value
	if not is_node_ready():
		return
	_icon.texture = Art.item_icon(int(row.get("vnum", 0))) if not row.is_empty() else null
	_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_icon.size = (
		size
		if kind == "quickslot"
		else (_icon.texture.get_size() if _icon.texture else Vector2.ZERO)
	)
	var amount := int(row.get("count", 0))
	_count.text = str(amount) if amount > 1 else ""
	_count.position = Vector2(size.x - _count.get_minimum_size().x - 2, size.y - 15)


func _gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton:
		return
	if event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		secondary.emit(self)
		accept_event()
	elif event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			_click_pending = true
		elif _click_pending:
			primary.emit(self)
			_click_pending = false
		accept_event()


func _get_drag_data(_at: Vector2) -> Variant:
	_click_pending = false
	if row.is_empty():
		return null
	drag_started.emit()
	var preview := TextureRect.new()
	preview.texture = Art.item_icon(int(row["vnum"]))
	preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	preview.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	set_drag_preview(preview)
	return {"mt2_item": row.duplicate(), "source_kind": kind, "source_cell": cell}


func _can_drop_data(_at: Vector2, data: Variant) -> bool:
	return data is Dictionary and data.get("mt2_item") is Dictionary


func _drop_data(_at: Vector2, data: Variant) -> void:
	dropped.emit(self, data["mt2_item"])


func _on_enter() -> void:
	_highlight.show()
	if not row.is_empty():
		hovered.emit(row)


func _on_exit() -> void:
	_highlight.hide()
	unhovered.emit()
