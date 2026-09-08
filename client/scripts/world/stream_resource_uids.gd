extends RefCounted
## Restore dependency identities from mounted, hash-verified scenery resources.

const MAP_ROOT := "res://assets/imported/maps/"
const TERRAIN_SHADER := "res://shaders/imported_terrain.gdshader"
var last_error := ""
var _visited: Dictionary = {}


func register_dependencies(path: String) -> bool:
	last_error = ""
	var pending: Dictionary = {}
	var visited: Dictionary = {}
	if not _collect(path, pending, visited):
		return false
	# Validate the whole graph before changing the global UID registry.
	for id: int in pending:
		if ResourceUID.has_id(id) and ResourceUID.get_id_path(id) != pending[id]:
			last_error = "Scenery resource UID conflicts with an installed resource."
			return false
	for id: int in pending:
		if not ResourceUID.has_id(id):
			ResourceUID.add_id(id, pending[id])
	_visited.merge(visited)
	return true


func _collect(path: String, pending: Dictionary, visited: Dictionary) -> bool:
	if _visited.has(path) or visited.has(path):
		return true
	if not path.begins_with(MAP_ROOT) and path != TERRAIN_SHADER:
		last_error = "Scenery dependency is outside the map resource namespace."
		return false
	if not ResourceLoader.exists(path):
		last_error = "Scenery dependency is missing: " + path
		return false
	visited[path] = true
	for dependency: String in ResourceLoader.get_dependencies(path):
		var parts := dependency.split("::")
		var target := parts[-1]
		if parts.size() == 3 and parts[0].begins_with("uid://"):
			var id := ResourceUID.text_to_id(parts[0])
			if id == ResourceUID.INVALID_ID or (pending.has(id) and pending[id] != target):
				last_error = "Scenery dependency has an invalid or conflicting UID."
				return false
			pending[id] = target
		if not _collect(target, pending, visited):
			return false
	return true
