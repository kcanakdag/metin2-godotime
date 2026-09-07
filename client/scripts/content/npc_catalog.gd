class_name NpcCatalog
extends RefCounted
## Immutable stationary presentation. No interaction or gameplay authority.

const PATH := "res://assets/imported/npcs/catalog.v1.json"
const PREFIX := "res://assets/imported/npcs/actors/"

var error_message := ""
var actors: Dictionary = {}
var maps: Dictionary = {}


func load_required(path := PATH) -> bool:
	if not FileAccess.file_exists(path):
		return _fail("NPC content is missing. Build and install the NPC catalog.")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		return _fail("NPC catalog is not valid JSON.")
	return load_document(parsed)


func load_document(document: Dictionary) -> bool:
	actors.clear()
	maps.clear()
	error_message = ""
	if (
		document.get("schema") != "mt2spacetime.static-npcs"
		or document.get("version") != 1
		or not document.get("actors") is Array
		or not document.get("maps") is Array
	):
		return _fail("Unsupported NPC catalog.")
	if document.actors.is_empty() or document.actors.size() > 256 or document.maps.size() > 32:
		return _fail("NPC catalog exceeds supported bounds.")
	for actor: Variant in document.actors:
		if not _index_actor(actor):
			return _fail("Invalid NPC actor definition.")
	for world: Variant in document.maps:
		if not _index_map(world):
			return _fail("Invalid NPC map layout.")
	return true


func layout(info: Dictionary) -> Dictionary:
	error_message = ""
	var map_id := str(info.get("map_id", ""))
	if not maps.has(map_id):
		error_message = "NPC layout is missing for this map. Update the client content."
		return {}
	var world: Dictionary = maps[map_id]
	if world.content_hash != info.get("content_hash", ""):
		error_message = "NPC placements differ from the server map. Update the client content."
		return {}
	return world.duplicate(true)


func _index_actor(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	var id := str(value.get("id", ""))
	var path := str(value.get("model", ""))
	if (
		id.is_empty()
		or actors.has(id)
		or not path.begins_with(PREFIX)
		or not path.ends_with(".glb")
		or path.contains("..")
		or path.contains("\\")
		or str(value.get("name", "")).is_empty()
		or not _number(value.get("label_height"), 0.1, 100)
		or not value.get("idle") is Array
	):
		return false
	if not _valid_idle(value.idle):
		return false
	actors[id] = value.duplicate(true)
	return true


func _valid_idle(motions: Array) -> bool:
	var total := 0
	var clips: Dictionary = {}
	if motions.is_empty() or motions.size() > 16:
		return false
	for motion: Variant in motions:
		if not motion is Dictionary or not _number(motion.get("weight"), 1, 100):
			return false
		var clip := str(motion.get("clip", ""))
		if clip.is_empty() or clips.has(clip) or float(motion.weight) != int(motion.weight):
			return false
		clips[clip] = true
		total += int(motion.weight)
	return total == 100


func _index_map(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	var id := str(value.get("id", ""))
	if (
		id.is_empty()
		or maps.has(id)
		or not value.get("placements") is Array
		or value.placements.size() > 4096
		or not RegEx.create_from_string("^[a-f0-9]{64}$").search(str(value.get("content_hash", "")))
	):
		return false
	var ids: Dictionary = {}
	for spawn: Variant in value.placements:
		if not spawn is Dictionary or not _valid_placement(spawn, ids):
			return false
		ids[spawn.id] = true
	maps[id] = value.duplicate(true)
	return true


func _valid_placement(spawn: Dictionary, ids: Dictionary) -> bool:
	if (
		str(spawn.get("id", "")).is_empty()
		or ids.has(spawn.get("id"))
		or not actors.has(spawn.get("actor_id"))
		or not _number(spawn.get("yaw"), -TAU, TAU)
		or not spawn.get("position") is Array
		or spawn.position.size() != 3
	):
		return false
	for coordinate: Variant in spawn.position:
		if not _number(coordinate, -1000000, 1000000):
			return false
	return true


func _number(value: Variant, minimum: float, maximum: float) -> bool:
	return (
		(value is int or value is float)
		and is_finite(float(value))
		and float(value) >= minimum
		and float(value) <= maximum
	)


func _fail(message: String) -> bool:
	actors.clear()
	maps.clear()
	error_message = message
	return false
