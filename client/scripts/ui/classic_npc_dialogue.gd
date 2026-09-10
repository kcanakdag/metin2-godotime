extends Control
## Server-provided quest dialogue in the original thin board with answer bars.
##
## Layout follows the original quest window: a 350x300 thin board, a title bar,
## wrapped body text and up to eight 200x26 answer bars stacked from the bottom
## half of the board. The server owns every string; this panel only presents.

signal close_requested(session_id: int)
signal choose_requested(session_id: int, option: int)

const Art := preload("res://scripts/ui/classic_art.gd")

const WIDTH := 350.0
const HEIGHT := 300.0
const BODY_TOP := 42.0
const BODY_MARGIN := 22.0
const BAR_WIDTH := 200.0
const BAR_HEIGHT := 26.0
const BAR_STEP := 28.0
const MAX_OPTIONS := 8
const BAR_FILL := Color(0.38, 0.32, 0.24, 0.94)
const BAR_HOVER := Color(0.5, 0.44, 0.32, 0.96)

var session_id := 0

var _title: Label
var _body: Label
var _close: TextureButton
var _board: Control
var _bars: Array[Control] = []


func _ready() -> void:
	size = Vector2(WIDTH, HEIGHT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	_rebuild_board()
	_title = Art.label(self, "", Vector2(BODY_MARGIN, 12), Art.TITLE)
	_title.size = Vector2(WIDTH - BODY_MARGIN * 2 - 24, 20)
	_title.clip_text = true
	_body = Art.label(self, "", Vector2(BODY_MARGIN, BODY_TOP))
	_body.size = Vector2(WIDTH - BODY_MARGIN * 2, HEIGHT - 64.0 - BODY_TOP)
	_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	_close = Art.button(self, "public/large_button_", Vector2.ZERO, request_close)
	_close.tooltip_text = "Close"
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
	_populate_bars(row.get("options", []))
	visible = session_id > 0
	_layout()


func request_close() -> void:
	if session_id > 0:
		close_requested.emit(session_id)


func choose(option: int) -> void:
	if session_id > 0 and option >= 0 and option < _bars.size():
		choose_requested.emit(session_id, option)


func option_count() -> int:
	return _bars.size()


func snapshot() -> Dictionary:
	var point := _close.get_global_rect().get_center()
	var answers: Array = []
	for index in _bars.size():
		var label: Label = _bars[index].get_child(1)
		var center := _bars[index].get_global_rect().get_center()
		answers.append({"option": index, "center": [center.x, center.y], "text": label.text})
	return {
		"visible": is_visible_in_tree(),
		"session_id": session_id,
		"title": _title.text,
		"body": _body.text,
		"options": answers.map(func(entry: Dictionary) -> String: return entry.text),
		"answers": answers,
		"close_center": [point.x, point.y],
	}


func _populate_bars(options: Variant) -> void:
	for bar in _bars:
		bar.queue_free()
	_bars.clear()
	if not options is Array:
		return
	for index in mini(options.size(), MAX_OPTIONS):
		_bars.append(_make_bar(index, str(options[index])))


func _make_bar(option: int, text: String) -> Control:
	var bar := Control.new()
	bar.size = Vector2(BAR_WIDTH, BAR_HEIGHT)
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bar)
	var fill := ColorRect.new()
	fill.color = BAR_FILL
	fill.size = bar.size
	fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_child(fill)
	var caption := Art.label(bar, text, Vector2.ZERO)
	caption.size = bar.size
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	caption.clip_text = true
	var hit := Button.new()
	hit.size = bar.size
	hit.flat = true
	hit.focus_mode = Control.FOCUS_NONE
	hit.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	hit.tooltip_text = text
	hit.add_theme_stylebox_override("hover", _hover_style())
	hit.add_theme_stylebox_override("pressed", _hover_style())
	hit.pressed.connect(func() -> void: choose(option))
	bar.add_child(hit)
	return bar


func _hover_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = BAR_HOVER
	return style


func _layout() -> void:
	var close_height := _close.texture_normal.get_height()
	var bars_height := 0.0 if _bars.is_empty() else BAR_STEP * float(_bars.size() - 1) + BAR_HEIGHT
	var minimum := 96.0 + bars_height + close_height
	if not is_equal_approx(size.y, maxf(HEIGHT, minimum)):
		size.y = maxf(HEIGHT, minimum)
		_rebuild_board()
	_body.size = Vector2(WIDTH - BODY_MARGIN * 2, size.y - bars_height - close_height - 64.0)
	var top := size.y - close_height - 18.0 - bars_height
	for index in _bars.size():
		var bar: Control = _bars[index]
		bar.position = Vector2((WIDTH - BAR_WIDTH) * 0.5, top + BAR_STEP * float(index))
	position = (get_viewport_rect().size - size) * 0.5
	_close.position.x = (WIDTH - _close.texture_normal.get_width()) * 0.5
	_close.position.y = size.y - close_height - 12.0


func _rebuild_board() -> void:
	if is_instance_valid(_board):
		_board.free()
	_board = Art.board(self, size, true)
	move_child(_board, 0)
