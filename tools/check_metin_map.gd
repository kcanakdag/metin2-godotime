extends SceneTree
## Validate generated resources and placements using the actual Godot loader.

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("check_map")


func check_map() -> void:
	var args := OS.get_cmdline_user_args()
	var map_name := args[0] if args.size() == 1 else "metin2_map_a1"
	var folder := "res://assets/imported/maps/" + map_name
	if not ResourceLoader.exists(folder + "/map.tscn"):
		push_error("Run make import-map before checking the generated scene")
		quit(1)
		return
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder + "/map.json"))
	var scene: Node3D = load(folder + "/map.tscn").instantiate()
	root.add_child(scene)
	var checked := 0
	var source_to_godot := Basis(Vector3.RIGHT, Vector3.FORWARD, Vector3.UP)
	for chunk in data.chunks:
		var section := scene.get_node("Sections/Section_" + chunk.id) as Node3D
		require(
			section.position == Vector3(chunk.grid[0] * 256, 0, chunk.grid[1] * 256), "Chunk offset"
		)
		var ground := section.find_child("Terrain", true, false) as MeshInstance3D
		require(ground != null, "Missing terrain mesh")
		require(
			ground != null and ground.material_override is ShaderMaterial, "Lost terrain material"
		)
		require(
			section.find_children("Terrain*", "MeshInstance3D", true, false).size() == 1,
			"Duplicate terrain geometry"
		)
		if ground and ground.material_override is ShaderMaterial:
			var array: TextureLayered = ground.material_override.get_shader_parameter(
				"terrain_textures"
			)
			require(array.get_layers() == data.textures.size(), "Lost terrain texture layers")
		for record in chunk.objects:
			var prop: Dictionary = data.properties[record.crc]
			var parent := "Scenery" if prop.status == "converted" else "UnsupportedMarkers"
			var path := "%s/Object_%s_%03d_%s" % [parent, chunk.id, record.id, record.crc]
			var node := scene.get_node_or_null(path) as Node3D
			require(node != null, "Missing placement: " + path)
			if not node:
				continue
			# Recompute from source units; do not trust the generated Godot position field.
			var source: Array = record.source_position
			var expected := Vector3(source[0], source[2] + record.height_bias_cm, -source[1]) * 0.01
			require(node.position.distance_to(expected) < 0.001, "Incorrect placement: " + path)
			# Upright props dominate this fixture; verify heading with a transformed unit vector.
			if record.rotation_ypr_deg[0] == 0 and record.rotation_ypr_deg[1] == 0:
				var angle := deg_to_rad(record.rotation_ypr_deg[2])
				var expected_axis := source_to_godot * Vector3(cos(angle), sin(angle), 0)
				require(
					node.basis.x.distance_to(expected_axis) < 0.0001, "Incorrect heading: " + path
				)
			checked += 1
	require(
		(
			checked
			== (
				scene.get_node("Scenery").get_child_count()
				+ scene.get_node("UnsupportedMarkers").get_child_count()
			)
		),
		"Placement count"
	)
	scene.queue_free()
	if failures.is_empty():
		print(
			(
				"MAP_CHECK_OK placements=%d sections=%d texture_layers=%d"
				% [checked, data.chunks.size(), data.textures.size()]
			)
		)
		quit()
	else:
		for failure in failures:
			push_error(failure)
		quit(1)


func require(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
