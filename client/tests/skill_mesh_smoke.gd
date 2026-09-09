extends SceneTree

const MeshEffect = preload("res://scripts/actors/projectile_mesh_effect.gd")
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
	if args.size() != 1:
		quit(1)
		return
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var definition: Dictionary = catalog.meshes[0]
	var stationary: Dictionary = definition.duplicate(true)
	stationary.recipe.elements[0].billboard_type = 3
	_check("stationary MOVE billboard supported", MeshEffect._supported(stationary))
	stationary.recipe.position_events.append(stationary.recipe.position_events[0].duplicate(true))
	_check("moving MOVE tracks remain unqualified", not MeshEffect._supported(stationary))
	var scene := load("res://" + str(definition.model)) as PackedScene
	var texture := load("res://" + str(definition.geometries[0].texture)) as Texture2D
	root.size = Vector2i(800, 480)
	var world := Node3D.new()
	root.add_child(world)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.position = Vector3(0, 0, 3)
	camera.look_at(Vector3.ZERO)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 2
	camera.current = true
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	world.add_child(environment)
	var swatch := MeshInstance3D.new()
	swatch.mesh = QuadMesh.new()
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color(128.0 / 255, 64.0 / 255, 192.0 / 255, 1))
	var shader := Shader.new()
	shader.code = MeshEffect.additive_shader()
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("source_texture", ImageTexture.create_from_image(image))
	swatch.material_override = material
	world.add_child(swatch)
	# Independent CPU reference: fixed-function source RGB times source RGB.
	# Sweep every byte value, including the low range where renderer round-trip
	# approximations caused the original green-channel failure.
	var ramp := Image.create(256, 1, false, Image.FORMAT_RGBA8)
	for index: int in range(256):
		ramp.set_pixel(
			index, 0, Color(index / 255.0, (255 - index) / 255.0, 64 / 255.0, index / 255.0)
		)
	var ramp_texture := ImageTexture.create_from_image(ramp)
	material.set_shader_parameter("source_texture", ramp_texture)
	(swatch.mesh as QuadMesh).size = Vector2(256.0 / 240, 1)
	var max_error := 0.0
	var factors := [
		Vector3.ONE,
		Vector3(175, 175, 175) / 255.0,
		Vector3(176, 176, 176) / 255.0,
		Vector3(123, 67, 0) / 255.0
	]
	_check(
		"original gray factor rounds to 175",
		MeshEffect.packed_factor([0.686275, 0.686275, 0.686275, 1]) == factors[1]
	)
	_check("nonfinite factor rejects", not MeshEffect._factor_supported([NAN, 0, 0, 1]))
	_check("out-of-range factor rejects", not MeshEffect._factor_supported([2, 0, 0, 1]))
	for case: int in range(24):
		var operation: int = [3, 4, 6][(case / 2) % 3]
		var background: Color = [Color(0.8, 0.1, 0.2), Color(0.1, 0.8, 0.2)][case % 2]
		material.set_shader_parameter("color_operation", operation)
		var factor: Vector3 = factors[case / 6]
		material.set_shader_parameter("color_factor", factor)
		environment.environment.background_color = background
		swatch.visible = false
		await process_frame
		await RenderingServer.frame_post_draw
		var base := root.get_texture().get_image().get_pixel(400, 240)
		swatch.visible = true
		await process_frame
		await RenderingServer.frame_post_draw
		var capture := root.get_texture().get_image()
		for index: int in range(256):
			var pixel := capture.get_pixel(272 + index, 240)
			var source := Vector3(index, 255 - index, 64) / 255.0
			if operation != 3:
				source *= factor
			if operation == 6:
				source = (source * 4).clamp(Vector3.ZERO, Vector3.ONE)
			var expected := source * source * 255
			expected = (expected + Vector3(base.r, base.g, base.b) * 255).clamp(
				Vector3.ZERO, Vector3.ONE * 255
			)
			var error := Vector3(pixel.r, pixel.g, pixel.b) * 255 - expected
			max_error = maxf(max_error, maxf(absf(error.x), maxf(absf(error.y), absf(error.z))))
			_check(
				"additive 3/2 ramp pixel %d" % index,
				(
					error.abs().length_squared() < 3 * 2 * 2
					and absf(error.x) < 2
					and absf(error.y) < 2
					and absf(error.z) < 2
				)
			)
	print("MAX_BLEND_ERROR_BYTES ", max_error)
	swatch.queue_free()
	await process_frame
	for index: int in range(catalog.meshes.size()):
		definition = catalog.meshes[index].duplicate(true)
		if index == 1:
			definition.recipe.elements[0].billboard_type = 3
			definition.recipe.elements[0].color_factor = [0.686275, 0.686275, 0.686275, 1.0]
		scene = load("res://" + str(definition.model)) as PackedScene
		texture = load("res://" + str(definition.geometries[0].texture)) as Texture2D
		var effect := MeshEffect.new()
		world.add_child(effect)
		_check("original Bash mesh configures", effect.configure(definition, scene, texture))
		_check(
			"initial source visibility",
			effect.visible == (float(definition.recipe.start_time) == 0)
		)
		var mesh: MeshInstance3D = effect.find_children("*", "MeshInstance3D", true, false)[0]
		var bounds := mesh.get_aabb()
		camera.size = maxf(bounds.size.length() * 1.5, 0.5)
		camera.position = bounds.get_center() + Vector3(1, 1, 1) * camera.size
		camera.look_at(bounds.get_center())
		environment.environment.background_color = Color(0.05, 0.06, 0.08)
		var frames_seen: Dictionary = {}
		var state: Dictionary = {}
		for step: int in range(400):
			state = effect.advance(0.001)
			if effect.visible:
				frames_seen[state.frame] = true
			if effect.visible and int(state.frame) == 10:
				await process_frame
				await RenderingServer.frame_post_draw
				_check(
					"mesh capture saved",
					(
						root.get_texture().get_image().save_png(
							ProjectSettings.globalize_path("res://effect-bash-%d.png" % index)
						)
						== OK
					)
				)
			if state.finished:
				break
		_check("all original frames visible", frames_seen.size() == 31)
		_check("finite mesh finishes and hides", state.finished and not effect.visible)
		effect.queue_free()
		await process_frame
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)
