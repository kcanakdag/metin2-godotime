class_name WorldNpcs
extends Node3D
## Map-bound static NPCs, instantiated only over available terrain chunks.

signal failed(message: String)

const Catalog := preload("res://scripts/content/npc_catalog.gd")
const Actor := preload("res://scripts/actors/npc_actor.gd")

var error_message := ""
var actors: Dictionary = {}
var _catalog := Catalog.new()
var _layout: Dictionary = {}
var _models: Dictionary = {}
var _ready_at: Callable
var _active := false
var _elapsed := 0.0
var _spawn_rows: Array = []


func prepare(info: Dictionary, ready_at: Callable) -> bool:
	clear()
	error_message = ""
	if str(info.get("map_id", "")) == "training":
		return true
	if not _catalog.load_required():
		error_message = _catalog.error_message
		return false
	if FileAccess.get_sha256(Catalog.PATH) != str(info.get("npc_catalog_hash", "")):
		error_message = "NPC catalog differs from the server. Update the client content."
		return false
	_layout = _catalog.layout(info)
	if _layout.is_empty():
		error_message = _catalog.error_message
		return false
	var definitions: Array = _layout.placements + _layout.get("areas", [])
	for spawn: Dictionary in definitions:
		var definition: Dictionary = _catalog.actors[spawn.actor_id]
		if _models.has(spawn.actor_id):
			continue
		var packed := load(str(definition.model)) as PackedScene
		if packed == null:
			error_message = "NPC model could not load. Update the client content."
			clear()
			return false
		_models[spawn.actor_id] = packed
	_ready_at = ready_at
	return true


func set_active(value: bool) -> void:
	_active = value
	visible = value
	if value:
		refresh()
	else:
		_remove_actors()


func clear() -> void:
	set_active(false)
	_layout.clear()
	_models.clear()
	_ready_at = Callable()
	_spawn_rows.clear()


func set_spawn_rows(rows: Array) -> void:
	_spawn_rows = rows.duplicate(true)
	refresh()


func _placements() -> Array:
	var result: Array = _layout.placements.duplicate(true)
	var areas: Dictionary = {}
	for area: Dictionary in _layout.get("areas", []):
		areas[area.id] = area
	var seen: Dictionary = {}
	for row: Dictionary in _spawn_rows:
		if row.get("map_id") != _layout.id:
			continue
		var id := str(row.get("spawn_id", ""))
		if not areas.has(id) or seen.has(id) or not _valid_spawn_row(row, areas[id]):
			error_message = "Server NPC placement differs from the map definition."
			return []
		seen[id] = true
		result.append(
			{
				"id": id,
				"actor_id": row.actor_id,
				"position": [float(row.x_cm) / 100, float(row.height_m), float(row.z_cm) / 100],
				"yaw": row.yaw
			}
		)
	return result


func _valid_spawn_row(row: Dictionary, area: Dictionary) -> bool:
	if (
		row.get("actor_id") != area.actor_id
		or not row.get("x_cm") is int
		or not row.get("z_cm") is int
		or not row.get("heading_degrees") is int
		or not _catalog._number(row.get("height_m"), -1000000, 1000000)
		or not _catalog._number(row.get("yaw"), 0, TAU)
	):
		return false
	var b: Array = area.bounds_cm
	if (
		row.x_cm < b[0]
		or row.x_cm > b[2]
		or row.z_cm < b[1]
		or row.z_cm > b[3]
		or row.heading_degrees < 0
		or row.heading_degrees > 360
	):
		return false
	var expected := fposmod(PI + deg_to_rad(float(row.heading_degrees % 360)), TAU)
	return absf(wrapf(float(row.yaw) - expected, -PI, PI)) < 0.00001


func refresh() -> void:
	if not _active or _layout.is_empty() or not _ready_at.is_valid():
		return
	var placements := _placements()
	if not error_message.is_empty():
		clear()
		failed.emit(error_message)
		return
	var wanted: Dictionary = {}
	for spawn: Dictionary in placements:
		wanted[spawn.id] = true
		var point := Vector3(spawn.position[0], spawn.position[1], spawn.position[2])
		if not _ready_at.call(point):
			if actors.has(spawn.id):
				_dispose(actors[spawn.id])
				actors.erase(spawn.id)
			continue
		if actors.has(spawn.id):
			actors[spawn.id].position = point
			actors[spawn.id].rotation.y = float(spawn.yaw)
			continue
		var actor := Actor.new()
		add_child(actor)
		if not actor.configure(_catalog.actors[spawn.actor_id], spawn, _models[spawn.actor_id]):
			error_message = actor.error_message
			_dispose(actor)
			clear()
			failed.emit(error_message)
			return
		actors[spawn.id] = actor
	for id: String in actors.keys():
		if not wanted.has(id):
			_dispose(actors[id])
			actors.erase(id)


func _process(delta: float) -> void:
	_elapsed += delta
	if _active and _elapsed >= 0.25:
		_elapsed = 0.0
		refresh()


func _remove_actors() -> void:
	for actor: Node in actors.values():
		_dispose(actor)
	actors.clear()


func _dispose(actor: Node) -> void:
	remove_child(actor)
	actor.queue_free()
