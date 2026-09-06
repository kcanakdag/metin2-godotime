extends SceneTree
## Partition an actual Godot-exported pack into shared resources and section packs.

var output := ""
var usages: Dictionary = {}
var chunks: Dictionary = {}
var failed := false


func _initialize() -> void:
	output = OS.get_cmdline_user_args()[0]
	DirAccess.make_dir_recursive_absolute(output)
	for x in 4:
		for z in 5:
			var id := "%03d%03d" % [x, z]
			var files: Dictionary = {}
			collect("res://assets/imported/maps/metin2_map_a1/chunks/" + id + ".tscn", files, {})
			if failed:
				quit(1)
				return
			chunks[id] = files
			for file: String in files:
				usages[file] = int(usages.get(file, 0)) + 1
	var shared: Array[String] = []
	for file: String in usages:
		if int(usages[file]) > 1:
			shared.append(file)
	var manifest := {"version": 1, "map": "metin2_map_a1", "chunks": {}, "shared": pack(shared)}
	manifest["content_sha256"] = (
		JSON
		. parse_string(
			FileAccess.get_file_as_string("res://assets/imported/maps/metin2_map_a1/collision.json")
		)
		. content_sha256
	)
	for id: String in chunks:
		var unique: Array[String] = []
		for file: String in chunks[id]:
			if usages[file] == 1:
				unique.append(file)
		manifest.chunks[id] = pack(unique)
	var result := FileAccess.open(output + "/manifest.json", FileAccess.WRITE)
	result.store_string(JSON.stringify(manifest, "  "))
	result.close()
	print("WORLD_PACKS " + JSON.stringify(manifest))
	quit()


func collect(path: String, files: Dictionary, visited: Dictionary) -> void:
	if visited.has(path):
		return
	visited[path] = true
	var exists := FileAccess.file_exists(path)
	if exists:
		files[path] = true
	var remapped := false
	for suffix in [".remap", ".import"]:
		var config := ConfigFile.new()
		if not FileAccess.file_exists(path + suffix):
			continue
		if config.load(path + suffix) != OK or not config.has_section("remap"):
			push_error("Invalid exported resource remap: " + path + suffix)
			failed = true
			return
		files[path + suffix] = true
		for key: String in config.get_section_keys("remap"):
			# Exported GPU textures select a feature-specific path (for example path.s3tc).
			# The original PNG is omitted from the PCK, so collecting only path loses its bytes.
			if key == "path" or key.begins_with("path."):
				var target := str(config.get_value("remap", key))
				if not target.is_empty():
					remapped = true
					collect(target, files, visited)
	if not exists and not remapped:
		push_error("Unresolved exported resource dependency: " + path)
		failed = true
		return
	for dependency: String in ResourceLoader.get_dependencies(path):
		collect(dependency.split("::")[-1], files, visited)


func pack(files: Array[String]) -> Dictionary:
	files.sort()
	var path := output + "/packing.pck"
	var writer := PCKPacker.new()
	if writer.pck_start(path) != OK:
		push_error("Could not open output pack")
		quit(1)
	var included := 0
	for file: String in files:
		if not FileAccess.file_exists(file):
			push_error("Collected dependency disappeared before packing: " + file)
			quit(1)
			return {}
		if file.get_extension() in ["gd", "gdc"] or "addons/" in file:
			push_error("Executable script or addon in world asset pack: " + file)
			quit(1)
		if writer.add_file(file, file) != OK:
			push_error("Could not pack " + file)
			quit(1)
		included += 1
	writer.flush()
	var hash_value := FileAccess.get_sha256(path)
	var size := FileAccess.get_file_as_bytes(path).size()
	DirAccess.rename_absolute(path, output + "/" + hash_value + ".pck")
	return {"sha256": hash_value, "bytes": size, "files": included}
