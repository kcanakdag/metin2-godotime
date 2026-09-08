extends RefCounted
## Portable converted resources. Source-file hashes are verified by the packager.

var loaded := false
var error_message := ""
var flights: Dictionary = {}
var effects: Dictionary = {}
var textures: Dictionary = {}
var meshes: Dictionary = {}
var content_hash := ""


func load_required(path: String) -> bool:
	loaded = false
	error_message = ""
	flights = {}
	effects = {}
	textures = {}
	meshes = {}
	content_hash = ""
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		return _fail("Projectile catalog is missing or invalid JSON")
	if parsed.get("schema") != "mt2spacetime.projectile-catalog" or parsed.get("version") != 1:
		return _fail("Unsupported projectile catalog version")
	for key: String in ["flights", "effects", "textures", "meshes", "files"]:
		if not parsed.get(key) is Dictionary or parsed[key].size() > 256:
			return _fail("Invalid projectile catalog section: " + key)
	if parsed.flights.is_empty() or parsed.files.is_empty():
		return _fail("Projectile catalog has no flights or resources")
	return _load_resources(parsed, path.get_base_dir())


func _load_resources(document: Dictionary, root: String) -> bool:
	var resources := {}
	for relative: String in document.files:
		var resource := _read_resource(relative, str(document.files[relative]), root)
		if resource == null:
			return false
		resources[relative] = resource
	var candidate_textures := {}
	for virtual: String in document.textures:
		var metadata: Variant = document.textures[virtual]
		if not metadata is Dictionary or not resources.get(metadata.get("path")) is Texture2D:
			return _fail("Missing referenced particle texture")
		candidate_textures[virtual] = resources[metadata.path]
	var candidate_meshes := {}
	for virtual: String in document.meshes:
		var mesh: Variant = document.meshes[virtual]
		if (
			not mesh is Dictionary
			or not mesh.get("geometries") is Array
			or mesh.geometries.size() != 1
		):
			return _fail("Unsupported projectile mesh geometry count")
		var geometry: Variant = mesh.geometries[0]
		if (
			not geometry is Dictionary
			or not resources.get(geometry.get("texture")) is Texture2D
			or not resources.get(mesh.get("model")) is PackedScene
		):
			return _fail("Missing referenced mesh resource")
		candidate_meshes[virtual] = {
			"definition": mesh,
			"scene": resources[mesh.model],
			"texture": resources[geometry.texture]
		}
	if not _validate_links(document):
		return false
	flights = document.flights
	effects = document.effects
	textures = candidate_textures
	meshes = candidate_meshes
	content_hash = str(document.get("content_hash", ""))
	loaded = true
	return true


func _read_resource(relative: String, hash_value: String, root: String) -> Resource:
	var suffix := relative.get_extension()
	if (
		hash_value.length() != 64
		or not hash_value.is_valid_hex_number(false)
		or suffix not in ["png", "glb"]
		or relative != "assets/" + hash_value + "." + suffix
	):
		_fail("Unsafe projectile resource path")
		return null
	var path := root.path_join(relative)
	if not ResourceLoader.exists(path):
		_fail("Missing projectile resource: " + relative)
		return null
	var resource := load(path)
	if (
		(suffix == "png" and not resource is Texture2D)
		or (suffix == "glb" and not resource is PackedScene)
	):
		_fail("Wrong projectile resource type: " + relative)
		return null
	return resource


func _validate_links(document: Dictionary) -> bool:
	for flight: Variant in document.flights.values():
		if not flight is Dictionary or not flight.get("attachments") is Array:
			return _fail("Invalid projectile attachment list")
		for attachment: Variant in flight.attachments:
			if not attachment is Dictionary:
				return _fail("Invalid projectile attachment")
			var path := str(attachment.get("effect", ""))
			if document.effects.has(path) == document.meshes.has(path):
				return _fail("Missing or ambiguous projectile effect")
		if flight.get("bomb_effect") != null and not document.effects.has(flight.bomb_effect):
			return _fail("Missing projectile impact effect")
	return true


func _fail(message: String) -> bool:
	error_message = message
	return false
