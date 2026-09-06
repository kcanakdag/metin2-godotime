extends Control
## Original minimap/atlas geometry, composed independently from archive layout observations.
## References: uiscript/{minimap,atlaswindow}.py, root/uiminimap.py, PythonMiniMap.cpp.

const Art = preload("res://scripts/ui/classic_art.gd")
const Minimap = preload("res://scripts/world/classic_minimap.gd")
const MAP_ID := "metin2_map_a1"
const ATLAS_IMAGE := "atlas/metin2_map_a1/atlas"
const ATLAS_IMAGE_SIZE := Vector2(171, 214)
const ATLAS_SIZE := ATLAS_IMAGE_SIZE + Vector2(15, 38)

var _minimap: Control
var _mini_open: Control
var _mini_closed: TextureButton
var _mini_close_button: TextureButton
var _atlas_button: TextureButton
var _zoom_buttons: Array[TextureButton] = []
var _atlas: Control
var _atlas_map: Control
var _atlas_close_button: BaseButton
var _supported := false
var _player: Dictionary = {}
var _players: Array = []
var _identity := ""
var _moving := false
var _move_offset := Vector2.ZERO
var _atlas_placed := false


func _ready() -> void:
	name = "MapPanel"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_build_minimap()
	_build_atlas()
	get_viewport().size_changed.connect(_layout)
	_layout()
	set_world_info({})


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		_moving = false


func set_world_info(info: Dictionary) -> void:
	_supported = str(info.get("map_id", "")) == MAP_ID and Art.texture(ATLAS_IMAGE) != null
	_minimap.set_world_info(info)
	_atlas_button.disabled = not _supported
	_atlas_button.tooltip_text = "Open Large Map" if _supported else "Large Map cannot be shown."
	for button in _zoom_buttons:
		button.disabled = not _supported
	if not _supported:
		_atlas.hide()
		_moving = false
	_minimap.set_player_info(_player if _supported else {})
	_minimap.set_players(_players if _supported else [], _identity)
	_atlas_map.set_player(_player if _supported else {})


func set_player_info(row: Dictionary) -> void:
	_player = row
	_minimap.set_player_info(row if _supported else {})
	_atlas_map.set_player(row if _supported else {})


func set_players(rows: Array, identity: String) -> void:
	_players = rows
	_identity = identity
	_minimap.set_players(rows if _supported else [], identity)


func toggle_atlas() -> void:
	if not _supported:
		return
	_atlas.visible = not _atlas.visible
	if _atlas.visible:
		_show_atlas()


func close_top() -> bool:
	if not _atlas.visible:
		return false
	_atlas.hide()
	_moving = false
	return true


func snapshot() -> Dictionary:
	var rectangle := _atlas.get_global_rect()
	return {
		"supported": _supported,
		"minimap_open": _mini_open.visible,
		"minimap_visible": _mini_open.is_visible_in_tree(),
		"atlas_visible": _atlas.visible and is_visible_in_tree(),
		"atlas_rect":
		[rectangle.position.x, rectangle.position.y, rectangle.size.x, rectangle.size.y],
		"atlas_image_size": [ATLAS_IMAGE_SIZE.x, ATLAS_IMAGE_SIZE.y],
		"minimap_meters_per_pixel": _minimap._meters_per_pixel,
		"atlas_player": _atlas_map.marker_position(),
		"mapimage_rect":
		[
			rectangle.position.x + 7,
			rectangle.position.y + 30,
			ATLAS_IMAGE_SIZE.x,
			ATLAS_IMAGE_SIZE.y
		],
		"zoom_in_center": _center(_zoom_buttons[0]),
		"zoom_out_center": _center(_zoom_buttons[1]),
		"minimap_close_center": _center(_mini_close_button),
		"minimap_open_center": _center(_mini_closed),
		"atlas_button_center": _center(_atlas_button),
		"atlas_close_center": _center(_atlas_close_button),
		"atlas_title_center": [rectangle.position.x + 70, rectangle.position.y + 18]
	}


func _build_minimap() -> void:
	var frame := Control.new()
	frame.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	frame.offset_left = -136
	frame.size = Vector2(136, 137)
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(frame)
	_mini_open = Control.new()
	_mini_open.size = frame.size
	_mini_open.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.add_child(_mini_open)
	_minimap = Minimap.new()
	_minimap.position = Vector2(4, 5)
	_mini_open.add_child(_minimap)
	_minimap.mouse_filter = Control.MOUSE_FILTER_STOP
	Art.image(_mini_open, "minimap/minimap", Vector2.ZERO)
	_zoom_buttons.append(
		_map_button(_mini_open, "minimap_scaleup", Vector2(101, 116), _minimap.zoom_in, "Zoom in")
	)
	_zoom_buttons.append(
		_map_button(
			_mini_open, "minimap_scaledown", Vector2(115, 103), _minimap.zoom_out, "Zoom out"
		)
	)
	_mini_close_button = _map_button(
		_mini_open, "minimap_close", Vector2(111, 6), _set_minimap_open.bind(false), "Close"
	)
	_atlas_button = _map_button(
		_mini_open, "atlas_open", Vector2(12, 12), _show_atlas, "Open Large Map"
	)
	_mini_closed = _map_button(
		frame, "minimap_open", Vector2(100, 4), _set_minimap_open.bind(true), "Open Mini Map"
	)
	_set_minimap_open(true)


func _map_button(
	parent: Node, asset: String, at: Vector2, action: Callable, hint: String
) -> TextureButton:
	var result := TextureButton.new()
	result.position = at
	result.texture_normal = Art.texture("minimap/" + asset + "_default")
	result.texture_hover = Art.texture("minimap/" + asset + "_over")
	result.texture_pressed = Art.texture("minimap/" + asset + "_down")
	if result.texture_hover == null:
		result.texture_hover = result.texture_normal
	if result.texture_pressed == null:
		result.texture_pressed = result.texture_normal
	result.texture_disabled = result.texture_normal
	result.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	result.tooltip_text = hint
	result.focus_mode = Control.FOCUS_NONE
	result.pressed.connect(action)
	parent.add_child(result)
	return result


func _build_atlas() -> void:
	_atlas = Control.new()
	_atlas.name = "AtlasWindow"
	_atlas.size = ATLAS_SIZE
	_atlas.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_atlas)
	Art.board(_atlas, ATLAS_SIZE)
	var title := Art.title(_atlas, "Large Map", ATLAS_SIZE.x - 15, close_top)
	title.gui_input.connect(_on_title_input)
	for child in title.get_children():
		if child is BaseButton:
			_atlas_close_button = child
	_atlas_map = AtlasCanvas.new()
	_atlas_map.position = Vector2(7, 30)
	_atlas_map.size = ATLAS_IMAGE_SIZE
	_atlas.add_child(_atlas_map)
	_atlas.hide()


func _show_atlas() -> void:
	if _supported:
		_atlas.show()
		move_to_front()
		_clamp_atlas()


func _set_minimap_open(value: bool) -> void:
	_mini_open.visible = value
	_mini_closed.visible = not value


func _on_title_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_moving = event.pressed
		_move_offset = event.position
		if event.pressed:
			move_to_front()
			_atlas_placed = true
		accept_event()
	elif event is InputEventMouseMotion and _moving:
		_atlas.position += event.position - _move_offset
		_clamp_atlas()
		accept_event()


func _layout() -> void:
	if not _atlas_placed:
		_atlas.position = Vector2(get_viewport_rect().size.x - 402, 0)
	_clamp_atlas()


func _clamp_atlas() -> void:
	_atlas.position = _atlas.position.clamp(
		Vector2.ZERO, (get_viewport_rect().size - ATLAS_SIZE).max(Vector2.ZERO)
	)


func _center(control: Control) -> Array:
	var point := control.get_global_rect().get_center()
	return [point.x, point.y]


class AtlasCanvas:
	extends Control
	## Original atlas marks only the main character; NPC/warp data is not fabricated.

	var _texture: Texture2D
	var _marker: Texture2D
	var _player: Dictionary = {}
	var _blink_on := true
	var _hover: Label

	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_PASS
		clip_contents = true
		texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		_texture = Art.texture(ATLAS_IMAGE)
		_marker = Art.texture("minimap/playermark")
		_hover = Art.label(get_parent(), "", Vector2.ZERO, Color.WHITE)
		_hover.hide()

	func _process(_delta: float) -> void:
		var blink := (Time.get_ticks_msec() / 500) % 2 == 1
		if blink != _blink_on:
			_blink_on = blink
			queue_redraw()
		var marker := marker_position()
		var hovered := (
			not marker.is_empty()
			and get_local_mouse_position().distance_to(Vector2(marker[0], marker[1])) < 7
		)
		_hover.visible = hovered
		if hovered:
			_hover.text = "%s(%d, %d)" % [_player.get("name", ""), _player.x, _player.z]
			_hover.position = (
				(get_local_mouse_position() - Vector2(_hover.get_minimum_size().x + 5, 17))
				. max(Vector2.ZERO)
			)

	func set_player(row: Dictionary) -> void:
		_player = row
		queue_redraw()

	func marker_position() -> Array:
		if _player.is_empty() or not _player.has_all(["x", "z"]):
			return []
		var point := Vector2(float(_player.x), float(_player.z))
		if not point.is_finite() or not Rect2(Vector2.ZERO, Minimap.MAP_SIZE).has_point(point):
			return []
		point = point / Minimap.MAP_SIZE * size
		return [point.x, point.y]

	func _draw() -> void:
		if _texture:
			draw_texture_rect(_texture, Rect2(Vector2.ZERO, size), false)
		var point := marker_position()
		if point.is_empty() or _marker == null or not _blink_on:
			return
		draw_set_transform(Vector2(point[0], point[1]), -float(_player.get("heading", 0)))
		draw_texture(_marker, -_marker.get_size() / 2)
		draw_set_transform(Vector2.ZERO)
