class_name ClassicMinimap
extends Control
## North-up source minimap; all markers come from subscribed world coordinates.

const MAP_PATH := "res://assets/imported/ui/maps/metin2_map_a1.png"
const MAP_SIZE := Vector2(1024, 1280)
const RADIUS := 63.0

var _texture: Texture2D
var _player_mark: Texture2D
var _other_mark: Texture2D
var _map_id := ""
var _player: Dictionary = {}
var _players: Array = []
var _identity := ""
var _meters_per_pixel := 1.0


func _ready() -> void:
	custom_minimum_size = Vector2(128, 128)
	size = custom_minimum_size
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_player_mark = load("res://assets/imported/ui/minimap/playermark.png")
	_other_mark = load("res://assets/imported/ui/minimap/whitemark.png")
	if ResourceLoader.exists(MAP_PATH):
		_texture = load(MAP_PATH)


func set_world_info(info: Dictionary) -> void:
	_map_id = str(info.get("map_id", ""))
	queue_redraw()


func set_player_info(row: Dictionary) -> void:
	_player = row
	queue_redraw()


func set_players(rows: Array, local_identity: String) -> void:
	_players = rows
	_identity = local_identity
	queue_redraw()


func zoom_in() -> void:
	_meters_per_pixel = maxf(0.5, _meters_per_pixel / 2)
	queue_redraw()


func zoom_out() -> void:
	_meters_per_pixel = minf(4, _meters_per_pixel * 2)
	queue_redraw()


func _draw() -> void:
	var center := size * 0.5
	draw_circle(center, RADIUS, Color("151411"))
	if _player.is_empty():
		return
	var position_on_map := Vector2(float(_player.x), float(_player.z))
	if _texture and _map_id == "metin2_map_a1":
		var points := PackedVector2Array()
		var uv := PackedVector2Array()
		for i in range(96):
			var offset := Vector2.from_angle(TAU * i / 96) * RADIUS
			points.append(center + offset)
			uv.append((position_on_map + offset * _meters_per_pixel) / MAP_SIZE)
		draw_polygon(points, PackedColorArray([Color.WHITE]), uv, _texture)
	for row: Dictionary in _players:
		if str(row.identity) == _identity:
			continue
		var offset := (Vector2(float(row.x), float(row.z)) - position_on_map) / _meters_per_pixel
		if offset.length() < RADIUS - 3:
			if _other_mark:
				draw_texture(
					_other_mark, center + offset - _other_mark.get_size() / 2, Color("ffeb4c")
				)
	if _player_mark:
		draw_set_transform(center, -float(_player.get("heading", 0)))
		draw_texture(_player_mark, -_player_mark.get_size() / 2)
		draw_set_transform(Vector2.ZERO)
