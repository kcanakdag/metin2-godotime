extends SceneTree
## Run against the exported world's shared pack and entry chunk in a clean project.

const Registry = preload("res://scripts/world/stream_resource_uids.gd")


func _initialize() -> void:
	var folder := OS.get_cmdline_user_args()[0]
	var manifest: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(folder.path_join("manifest.json"))
	)
	for entry: Dictionary in [manifest.shared, manifest.chunks["002002"]]:
		assert(ProjectSettings.load_resource_pack(folder.path_join(entry.sha256 + ".pck"), false))
	var registry = Registry.new()
	assert(not registry.register_dependencies("res://scripts/main.gd"))
	assert(not registry.register_dependencies("res://assets/imported/maps/missing.tres"))
	var path := "res://assets/imported/maps/metin2_map_a1/chunks/002002.tscn"
	var parts := ResourceLoader.get_dependencies(path)[0].split("::")
	assert(parts.size() == 3)
	var id := ResourceUID.text_to_id(parts[0])
	assert(not ResourceUID.has_id(id))
	ResourceUID.add_id(id, "res://existing-resource.tres")
	assert(not registry.register_dependencies(path))
	assert(ResourceUID.get_id_path(id) == "res://existing-resource.tres")
	ResourceUID.remove_id(id)
	assert(registry.register_dependencies(path))
	assert(ResourceUID.get_id_path(id) == parts[-1])
	assert(registry.register_dependencies(path))
	var scene := (load(path) as PackedScene).instantiate()
	assert(scene.get_child_count() > 0)
	scene.free()
	print("STREAM_UID_CHECKS 10 passed")
	quit()
