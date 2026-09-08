extends SceneTree
## Load one streamed section without the full export or any other section masking dependencies.

var failures: Array[String] = []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var folder := args[0]
	var id := args[1]
	var source_terrain := args[2]
	var manifest: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(folder.path_join("manifest.json"))
	)
	for entry: Dictionary in [manifest.shared, manifest.chunks[id]]:
		var path := folder.path_join(str(entry.sha256) + ".pck")
		if FileAccess.get_sha256(path) != entry.sha256:
			failures.append("Stream pack hash mismatch")
		elif not ProjectSettings.load_resource_pack(path, false):
			failures.append("Could not mount stream pack")
	var identities = preload("res://scripts/world/stream_resource_uids.gd").new()
	if not identities.register_dependencies(
		"res://assets/imported/maps/metin2_map_a1/chunks/" + id + ".tscn"
	):
		failures.append(identities.last_error)
		finish({})
		return
	var packed := (
		load("res://assets/imported/maps/metin2_map_a1/chunks/" + id + ".tscn") as PackedScene
	)
	if not packed:
		failures.append("Could not load isolated chunk " + id)
		finish({})
		return
	var scene := packed.instantiate()
	var terrain_count := 0
	var textured_surfaces := 0
	var data_textures := 0
	for mesh: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if str(mesh.name).begins_with("Terrain"):
			terrain_count += 1
			var material := mesh.material_override as ShaderMaterial
			if not material or not material.shader:
				failures.append("Terrain shader missing")
				continue
			var layers: TextureLayered = material.get_shader_parameter("terrain_textures")
			if not layers or layers.get_layers() != 17 or layers.get_width() <= 0:
				failures.append("Terrain texture array missing or incomplete")
			for parameter: String in ["tile_ids", "attributes"]:
				var texture: Texture2D = material.get_shader_parameter(parameter)
				var expected := 258 if parameter == "tile_ids" else 256
				if (
					not texture
					or texture.get_width() != expected
					or texture.get_height() != expected
				):
					failures.append("Terrain " + parameter + " texture missing or incomplete")
					continue
				var suffix := "tiles" if parameter == "tile_ids" else "attributes"
				check_data_texture(texture, source_terrain.path_join(id + "-" + suffix + ".png"))
				data_textures += 1
		else:
			for surface in mesh.mesh.get_surface_count():
				var material := mesh.get_active_material(surface) as BaseMaterial3D
				if material and material.albedo_texture:
					if material.albedo_texture.get_width() <= 0:
						failures.append("Prop texture failed to load")
					textured_surfaces += 1
	if terrain_count != 1:
		failures.append("Expected exactly one terrain mesh")
	scene.free()
	finish(
		{
			"chunk": id,
			"terrain_meshes": terrain_count,
			"textured_surfaces": textured_surfaces,
			"lossless_data_textures": data_textures,
		}
	)


func check_data_texture(texture: Texture2D, source: String) -> void:
	var actual := texture.get_image()
	var expected := Image.load_from_file(source)
	if not actual or not expected:
		failures.append("Cannot inspect original and exported data texels: " + source)
		return
	if actual.is_compressed():
		failures.append("Numeric data texture uses lossy GPU compression: " + source)
		actual.decompress()
	if actual.has_mipmaps():
		failures.append("Numeric data texture has interpolated mipmap levels: " + source)
		actual.clear_mipmaps()
	actual.convert(Image.FORMAT_R8)
	expected.convert(Image.FORMAT_R8)
	if actual.get_data() != expected.get_data():
		failures.append("Export changed terrain IDs or attribute bits: " + source)


func finish(result: Dictionary) -> void:
	if not failures.is_empty():
		for failure in failures:
			push_error(failure)
		quit(1)
		return
	print("WORLD_PACK_CHECK " + JSON.stringify(result))
	quit()
