extends Control
## Server-provided text in the existing original-asset board and buttons.

signal close_requested(session_id: int)

const Art := preload("res://scripts/ui/classic_art.gd")
var session_id := 0
var _title: Label
var _body: Label
var _close: TextureButton


func _ready() -> void:
	size = Vector2(340, 190)
	mouse_filter = Control.MOUSE_FILTER_STOP
	Art.board(self, size)
	_title = Art.label(self, "", Vector2(26, 20), Art.TITLE)
	_body = Art.label(self, "", Vector2(26, 52))
	_body.size = Vector2(288, 90)
	_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_close = Art.button(self, "public/large_button_", Vector2(113, 146), request_close)
	_close.position.x = (size.x - _close.texture_normal.get_width()) * 0.5
	var caption := Art.label(_close, "Close", Vector2.ZERO)
	caption.size = _close.texture_normal.get_size()
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	get_viewport().size_changed.connect(_layout)
	_layout()
	hide()


func set_interaction(row: Dictionary) -> void:
	session_id = int(row.get("session_id", 0))
	_title.text = str(row.get("title", ""))
	_body.text = str(row.get("body", ""))
	visible = session_id > 0


func request_close() -> void:
	if session_id > 0:
		close_requested.emit(session_id)


func snapshot() -> Dictionary:
	var point := _close.get_global_rect().get_center()
	return {
		"visible": is_visible_in_tree(),
		"session_id": session_id,
		"title": _title.text,
		"body": _body.text,
		"close_center": [point.x, point.y],
	}


func _layout() -> void:
	position = (get_viewport_rect().size - size) * 0.5
