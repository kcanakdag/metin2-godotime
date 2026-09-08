extends RefCounted
## Source-free imported resources. Offline packaging verifies original asset bytes.

var error_message := ""
var document: Dictionary = {}
var textures: Dictionary = {}
var scenes: Dictionary = {}


func with_effects(motion: Dictionary) -> Dictionary:
	## Preserve the immutable actor catalog; enrich a private presentation copy.
	var events: Array = document.get("links", {}).get(str(motion.get("action_id", "")), [])
	if events.is_empty():
		return motion
	var result := motion.duplicate(true)
	result.effects = events.duplicate(true)
	return result


func load_required(path: String, character_hash: String, skill_hash: String) -> bool:
	document = {}
	textures = {}
	scenes = {}
	error_message = ""
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if (
		not value is Dictionary
		or value.get("schema") != "mt2spacetime.motion-effects"
		or value.get("version") != 1
	):
		return _fail("Missing or unsupported motion effect package")
	if (
		character_hash.is_empty()
		or skill_hash.is_empty()
		or value.get("character_catalog_sha256") != character_hash
		or value.get("skill_catalog_sha256") != skill_hash
	):
		return _fail("Motion effects do not match installed characters and skills")
	for key: String in ["effects", "mixed_effects", "textures", "links", "files"]:
		if not value.get(key) is Dictionary or value[key].size() > 1024:
			return _fail("Invalid motion effect section: " + key)
	if value.files.is_empty() or value.links.is_empty():
		return _fail("Empty motion effect package")
	if not _load_resources(value, path.get_base_dir()) or not _validate_links(value):
		textures = {}
		scenes = {}
		return false
	document = value
	return true


func _load_resources(value: Dictionary, root_path: String) -> bool:
	var resources: Dictionary = {}
	for relative: String in value.files:
		var hash_value := str(value.files[relative])
		var extension := relative.get_extension()
		if (
			hash_value.length() != 64
			or not hash_value.is_valid_hex_number(false)
			or extension not in ["png", "glb"]
			or relative != "assets/" + hash_value + "." + extension
		):
			return _fail("Unsafe motion effect resource path")
		var path := root_path.path_join(relative)
		if not ResourceLoader.exists(path):
			return _fail("Missing motion effect resource: " + relative)
		var resource := load(path)
		if (
			(extension == "png" and not resource is Texture2D)
			or (extension == "glb" and not resource is PackedScene)
		):
			return _fail("Wrong motion effect resource type")
		resources[relative] = resource
		if resource is PackedScene:
			scenes[relative] = resource
	for virtual: String in value.textures:
		var relative: Variant = value.textures[virtual]
		if not relative is String or not resources.get(relative) is Texture2D:
			return _fail("Missing motion effect texture")
		textures[virtual] = resources[relative]
	return _validate_mesh_resources(value)


func _validate_mesh_resources(value: Dictionary) -> bool:
	for entry: Variant in value.mixed_effects.values():
		if not entry is Dictionary or not entry.get("meshes") is Array:
			return _fail("Invalid mixed effect resource list")
		for mesh: Variant in entry.meshes:
			if (
				not mesh is Dictionary
				or not scenes.has(mesh.get("model"))
				or not mesh.get("geometries") is Array
			):
				return _fail("Missing mixed effect scene")
			for geometry: Variant in mesh.geometries:
				if not geometry is Dictionary or not textures.has(geometry.get("texture")):
					return _fail("Missing mixed effect mesh texture")
	return true


func _validate_links(value: Dictionary) -> bool:
	for action: String in value.links:
		var events: Variant = value.links[action]
		if action.is_empty() or not events is Array or events.is_empty() or events.size() > 32:
			return _fail("Invalid motion effect event list")
		var identities: Dictionary = {}
		for event: Variant in events:
			if not event is Dictionary or not event.get("source_event") is String:
				return _fail("Invalid motion effect event")
			if identities.has(event.source_event):
				return _fail("Duplicate motion effect event")
			identities[event.source_event] = true
			var effect := str(event.get("effect_path", ""))
			if value.effects.has(effect) == value.mixed_effects.has(effect):
				return _fail("Unresolved or ambiguous motion effect")
	return true


func _fail(message: String) -> bool:
	error_message = message
	return false
