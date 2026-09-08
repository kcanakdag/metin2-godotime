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
	shader.code = MeshEffect.SHADER
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
		ramp.set_pixel(index, 0, Color(index / 255.0, (255 - index) / 255.0, 64 / 255.0, 1))
	var ramp_texture := ImageTexture.create_from_image(ramp)
	material.set_shader_parameter("source_texture", ramp_texture)
	(swatch.mesh as QuadMesh).size = Vector2(256.0 / 240, 1)
	var max_error := 0.0
	for background: Color in [Color(0.8, 0.1, 0.2), Color(0.1, 0.8, 0.2)]:
		environment.environment.background_color = background
		await process_frame
		await RenderingServer.frame_post_draw
		var capture := root.get_texture().get_image()
		for index: int in range(256):
			var pixel := capture.get_pixel(272 + index, 240)
			var expected := Vector3(
				index * index / 255.0, (255 - index) ** 2 / 255.0, 64 * 64 / 255.0
			)
			var error := Vector3(pixel.r, pixel.g, pixel.b) * 255 - expected
			max_error = maxf(max_error, maxf(absf(error.x), maxf(absf(error.y), absf(error.z))))
			_check(
				"opaque 3/8 ramp pixel %d" % index,
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
	var effect := MeshEffect.new()
	world.add_child(effect)
	_check("original arrow configures", effect.configure(definition, scene, texture))
	_check("exact frame deadline", effect.advance(0.02).frame == 0)
	_check("next frame past deadline", effect.advance(0.02).frame == 1)
	var mesh: MeshInstance3D = effect.find_children("*", "MeshInstance3D", true, false)[0]
	for index: int in range(4):
		_check(
			"exact morph weights",
			is_equal_approx(mesh.get_blend_shape_value(index), 1 if index == 0 else 0)
		)
	_check("multiple frame update", effect.advance(0.04).frame == 3)
	_check("frame loop", effect.advance(0.04).frame == 0)
	_check("twenty frame catch-up cap", effect.advance(0.5).frame == 0)
	_check("catch-up backlog retained", effect.advance(0.001).frame == 1)
	_check("nonfinite step rejects", effect.advance(NAN).has("error"))
	var bounds := mesh.get_aabb()
	camera.size = maxf(bounds.size.length() * 1.5, 0.5)
	camera.position = bounds.get_center() + Vector3(1, 1, 1) * camera.size
	camera.look_at(bounds.get_center())
	environment.environment.background_color = Color(0.05, 0.06, 0.08)
	await process_frame
	await RenderingServer.frame_post_draw
	_check(
		"arrow capture saved",
		(
			root.get_texture().get_image().save_png(
				ProjectSettings.globalize_path("res://effect-arrow.png")
			)
			== OK
		)
	)
	var transparent := SubViewport.new()
	transparent.transparent_bg = true
	world.add_child(transparent)
	var rejected := MeshEffect.new()
	transparent.add_child(rejected)
	_check("transparent destination rejects", not rejected.configure(definition, scene, texture))
	var invalid := definition.duplicate(true)
	invalid.recipe.elements[0].blending_destination = 6
	var wrong := MeshEffect.new()
	world.add_child(wrong)
	_check("other blend recipe rejects", not wrong.configure(invalid, scene, texture))
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)
