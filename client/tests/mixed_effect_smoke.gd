extends SceneTree

const Mixed = preload("res://scripts/actors/mixed_effect.gd")
var _checks := 0
var _failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var scenes: Dictionary = {}
	var textures: Dictionary = {}
	for mesh: Dictionary in catalog.meshes:
		scenes[mesh.model] = load("res://" + str(mesh.model))
		for geometry: Dictionary in mesh.geometries:
			textures[geometry.texture] = load("res://" + str(geometry.texture))
	for path: String in catalog.textures:
		textures[path] = load("res://" + str(catalog.textures[path].path))
	root.size = Vector2i(800, 600)
	var world := Node3D.new()
	root.add_child(world)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.position = Vector3(5, 4, 7)
	camera.look_at(Vector3(0, 0, 2))
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 9
	camera.current = true
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.04, 0.05, 0.07)
	world.add_child(environment)
	var effect := Mixed.new()
	world.add_child(effect)
	_check("complete mixed effect configures", effect.configure(catalog, scenes, textures, 42))
	if effect._particles == null:
		print("CONFIGURE_ERROR ", effect.error_message)
		_finish()
		return
	_check(
		"all particle systems present",
		effect._particles._layers.size() == catalog.particle_effect.systems.size()
	)
	_check("all mesh layers present", effect._meshes.size() == catalog.meshes.size())
	for index: int in range(catalog.meshes.size()):
		_check(
			"every geometry has material",
			effect._meshes[index].materials.size() == catalog.meshes[index].geometries.size()
		)
	for layer_index: int in range(catalog.meshes.size()):
		var layer: Node3D = effect._meshes[layer_index]
		for index: int in range(layer.materials.size()):
			var material: ShaderMaterial = layer.materials[index]
			_check(
				"surface uses its ordered material",
				layer._mesh.get_surface_override_material(index) == material
			)
			_check(
				"surface factor follows original element",
				(
					material.get_shader_parameter("color_factor")
					== layer.packed_factor(
						catalog.meshes[layer_index].recipe.elements[index].color_factor
					)
				)
			)
	var peak := 0
	var clean := true
	var completed := false
	for frame: int in range(1200):
		var state: Dictionary = effect.advance(1.0 / 60, camera)
		if state.has("error"):
			print("MIXED_ERROR ", state.error)
			clean = false
			break
		peak = maxi(peak, int(state.alive))
		if frame in [3, 8, 14, 29, 59]:
			await process_frame
			await RenderingServer.frame_post_draw
			_check(
				"mixed capture saved",
				(
					root.get_texture().get_image().save_png(
						ProjectSettings.globalize_path("res://effect-mixed-%d.png" % frame)
					)
					== OK
				)
			)
		if state.finished:
			completed = true
			break
	_check("particles emitted", peak > 0)
	_check("combined simulation clean", clean)
	_check("whole effect completes", completed)
	var invalid := Mixed.new()
	world.add_child(invalid)
	_check(
		"missing mesh resource rejects whole effect",
		not invalid.configure(catalog, {}, textures, 1)
	)
	_check("rejection leaves no partial children", invalid.get_child_count() == 0)
	_finish()


func _finish() -> void:
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)
