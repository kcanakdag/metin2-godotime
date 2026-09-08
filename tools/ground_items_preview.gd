extends SceneTree
## Isolated developer preview for import_ground_items.py output.

var _failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var document: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://normalized.v1.json")
	)
	var models: Dictionary = {}
	for item: Dictionary in document.items:
		models[item.id] = item.output
	var world := Node3D.new()
	root.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("52565e")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.7
	world.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	world.add_child(light)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.position = Vector3(0.5, 0.8, 1.2)
	camera.look_at(Vector3(0.5, 0.1, 0))
	camera.current = true
	var results: Array = []
	for index in document.ground_items.size():
		var row: Dictionary = document.ground_items[index]
		var path: String = "res://generated/" + str(models[row.model_id])
		var packed: PackedScene = load(path)
		if packed == null:
			_failures.append("Missing model for %s" % row.vnum)
			continue
		var model: Node3D = packed.instantiate()
		world.add_child(model)
		model.position.x = index * 0.5
		var meshes := 0
		var textured := 0
		for node: Node in model.find_children("*", "MeshInstance3D", true, false):
			meshes += 1
			var mesh := node as MeshInstance3D
			if not mesh.get_aabb().size.is_finite() or mesh.get_aabb().size.length() <= 0:
				_failures.append("Invalid bounds for %s" % row.vnum)
			for surface in mesh.mesh.get_surface_count():
				var material := mesh.get_active_material(surface) as BaseMaterial3D
				if material != null and material.albedo_texture != null:
					textured += 1
		if meshes == 0 or textured == 0:
			_failures.append("Untextured or empty model for %s" % row.vnum)
		results.append({"vnum": row.vnum, "meshes": meshes, "textured_surfaces": textured})
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("user://ground-items.png")
	var report := {"models": results, "failures": _failures}
	FileAccess.open("user://ground-items.json", FileAccess.WRITE).store_string(
		JSON.stringify(report)
	)
	print(JSON.stringify(report))
	quit(0 if _failures.is_empty() else 1)
