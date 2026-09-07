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
	for spawn: Dictionary in _layout.placements:
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


func refresh() -> void:
	if not _active or _layout.is_empty() or not _ready_at.is_valid():
		return
	for spawn: Dictionary in _layout.placements:
		var point := Vector3(spawn.position[0], spawn.position[1], spawn.position[2])
		if not _ready_at.call(point):
			if actors.has(spawn.id):
				_dispose(actors[spawn.id])
				actors.erase(spawn.id)
			continue
		if actors.has(spawn.id):
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
