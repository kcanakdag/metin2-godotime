class_name ClassicTarget
extends Control
## Narrow original target board driven only by an accepted private target projection.

signal clear_requested
signal presentation_failed(message: String)

const Art = preload("res://scripts/ui/classic_art.gd")

# Pinned `ui.py`/`uitarget.py` source pixels for the enemy HP state.
const RESET_SIZE := Vector2(250, 40)
const TOP_OFFSET := 10.0
const NAME_POSITION := Vector2(23, 13)
const GAUGE_RIGHT_OFFSET := 175.0
const GAUGE_POSITION_Y := 17.0
const GAUGE_WIDTH := 130.0
const GAUGE_CAP_WIDTH := 16.0
const GAUGE_FILL_INSET := 12.0
const GAUGE_FILL_WIDTH := GAUGE_WIDTH - GAUGE_FILL_INSET * 2.0
const CLOSE_RIGHT_OFFSET := 30.0
const CLOSE_POSITION_Y := 13.0

var _frame: Control
var _name: Label
var _gauge_clip: Control
var _gauge: TextureRect
var _close: TextureButton
var _target: Dictionary = {}
var _monster: Dictionary = {}
var _display_name := ""
var _reported_error := ""


func _ready() -> void:
	name = "TargetBoard"
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 20
	_rebuild(RESET_SIZE.x)
	hide()
	get_viewport().size_changed.connect(_layout)


func set_target(target: Dictionary, monsters: Array) -> void:
	var matching: Array[Dictionary] = []
	var target_id := int(target.get("target_id", 0))
	var target_life := int(target.get("target_life_sequence", -1))
	if target_id > 0 and target_life >= 0:
		for value: Variant in monsters:
			if not value is Dictionary:
				continue
			var row: Dictionary = value
			if (
				int(row.get("id", 0)) == target_id
				and int(row.get("life_sequence", -1)) == target_life
			):
				matching.append(row)
	if matching.size() != 1:
		_hide_target()
		return
	var validation_error := _monster_validation_error(matching[0])
	if not validation_error.is_empty():
		_report_once(validation_error)
		_hide_target()
		return
	if not _valid_live_monster(matching[0]):
		_hide_target()
		return
	_reported_error = ""
	_target = target.duplicate()
	_monster = matching[0].duplicate()
	_display_name = "Lv.%d %s" % [int(_monster.level), str(_monster.name)]
	var source_width := 200.0 + 7.0 * _display_name.length()
	if not is_equal_approx(size.x, source_width):
		_rebuild(source_width)
	_name.text = _display_name
	var health := int(_monster.health)
	var maximum := int(_monster.max_health)
	_gauge_clip.size.x = GAUGE_FILL_WIDTH * clampf(float(health) / maximum, 0.0, 1.0)
	show()
	_layout()


func clear_view() -> void:
	_hide_target()


func snapshot() -> Dictionary:
	var close_center := Vector2.ZERO
	if is_instance_valid(_close):
		close_center = _close.get_global_rect().get_center()
	return {
		"visible": is_visible_in_tree(),
		"target_id": int(_target.get("target_id", 0)),
		"target_life_sequence": int(_target.get("target_life_sequence", -1)),
		"display_name": _display_name,
		"health": int(_monster.get("health", 0)),
		"max_health": int(_monster.get("max_health", 0)),
		"board_rect": [position.x, position.y, size.x, size.y],
		"name_position": [NAME_POSITION.x, NAME_POSITION.y],
		"gauge_position": [size.x - GAUGE_RIGHT_OFFSET, GAUGE_POSITION_Y],
		"gauge_width": GAUGE_WIDTH,
		"gauge_fill_position": [GAUGE_FILL_INSET, 0.0],
		"gauge_fill_max_width": GAUGE_FILL_WIDTH,
		"gauge_fill_width": _gauge_clip.size.x if is_instance_valid(_gauge_clip) else 0.0,
		"gauge_texture_width":
		(
			_gauge.texture.get_width()
			if is_instance_valid(_gauge) and is_instance_valid(_gauge.texture)
			else 0
		),
		"close_position": [size.x - CLOSE_RIGHT_OFFSET, CLOSE_POSITION_Y],
		"close_center": [close_center.x, close_center.y],
		"action_count": 1,
	}


func _valid_live_monster(row: Dictionary) -> bool:
	return (
		int(row.get("id", 0)) > 0
		and int(row.get("life_sequence", -1)) >= 0
		and int(row.get("level", 0)) > 0
		and not str(row.get("name", "")).is_empty()
		and int(row.get("health", 0)) > 0
		and int(row.get("max_health", 0)) > 0
		and int(row.get("activity", 0)) != 3
	)


func _monster_validation_error(row: Dictionary) -> String:
	var level := int(row.get("level", 0))
	if level <= 0 or level > 0xFF:
		return "The selected monster has an unsupported level."
	if str(row.get("name", "")).strip_edges().is_empty():
		return "The selected monster has no display name."
	if int(row.get("max_health", 0)) <= 0:
		return "The selected monster has invalid health data."
	return ""


func _report_once(message: String) -> void:
	if message == _reported_error:
		return
	_reported_error = message
	presentation_failed.emit(message)


func _hide_target() -> void:
	_target = {}
	_monster = {}
	_display_name = ""
	hide()


func _rebuild(width: float) -> void:
	if is_instance_valid(_frame):
		_frame.free()
	size = Vector2(width, RESET_SIZE.y)
	_frame = Control.new()
	_frame.name = "Frame"
	_frame.size = size
	_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_frame)
	Art.board(_frame, size, true)
	_name = Art.label(_frame, "", NAME_POSITION)
	var gauge_position := Vector2(size.x - GAUGE_RIGHT_OFFSET, GAUGE_POSITION_Y)
	Art.image(_frame, "pattern/gauge_slot_left", gauge_position)
	Art.tile(
		_frame,
		"pattern/gauge_slot_center",
		Rect2(gauge_position + Vector2(GAUGE_CAP_WIDTH, 0), Vector2(GAUGE_WIDTH - 32.0, 7.0))
	)
	Art.image(
		_frame,
		"pattern/gauge_slot_right",
		gauge_position + Vector2(GAUGE_WIDTH - GAUGE_CAP_WIDTH, 0)
	)
	_gauge_clip = Control.new()
	_gauge_clip.name = "HealthGaugeClip"
	_gauge_clip.position = gauge_position + Vector2(GAUGE_FILL_INSET, 0)
	_gauge_clip.size = Vector2(GAUGE_FILL_WIDTH, 0)
	_gauge_clip.clip_contents = true
	_gauge_clip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_frame.add_child(_gauge_clip)
	var gauge_texture: Texture2D = Art.texture("pattern/gauge_red")
	var gauge_height: float = (
		gauge_texture.get_height() if is_instance_valid(gauge_texture) else 0.0
	)
	_gauge = Art.tile(
		_gauge_clip,
		"pattern/gauge_red",
		Rect2(Vector2.ZERO, Vector2(GAUGE_FILL_WIDTH, gauge_height))
	)
	_gauge_clip.size.y = gauge_height
	_close = Art.button(
		_frame,
		"public/close_button_",
		Vector2(size.x - CLOSE_RIGHT_OFFSET, CLOSE_POSITION_Y),
		func() -> void: clear_requested.emit()
	)
	_close.tooltip_text = "Close target"
	_layout()


func _layout() -> void:
	var viewport_width := get_viewport_rect().size.x
	position = Vector2(maxf(0.0, floor((viewport_width - size.x) / 2.0)), TOP_OFFSET)
