extends SceneTree

const Effect = preload("res://scripts/actors/particle_effect.gd")
const WorldEffects = preload("res://scripts/world/world_motion_effects.gd")
const Actor = preload("res://scripts/actors/actor_presentation.gd")
const Style = preload("res://scripts/actors/particle_style.gd")
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
	var textures: Dictionary = {}
	for path: String in catalog.textures:
		var image := Image.load_from_file(
			args[0].get_base_dir().path_join(catalog.textures[path].path)
		)
		textures[path] = ImageTexture.create_from_image(image)
	root.size = Vector2i(640, 480)
	var world := Node3D.new()
	root.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.04, 0.05, 0.07)
	world.add_child(environment)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.position = Vector3(0, 4, 7)
	camera.look_at(Vector3.ZERO)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 8
	camera.current = true
	await process_frame
	await RenderingServer.frame_post_draw
	var baseline := root.get_texture().get_image()
	_style_checks(catalog.effects[0].systems[0])
	_geometry_checks(world, camera, catalog.effects[0].systems[0])
	for i: int in range(catalog.effects.size()):
		var effect := Effect.new()
		world.add_child(effect)
		_check("effect configures", effect.configure(catalog.effects[i], textures, 42))
		var peak_pixels := 0
		var peak_alive := 0
		for frame: int in range(60):
			var result: Dictionary = effect.advance(1.0 / 60.0, camera)
			if result.has("error"):
				_check("simulation step", false)
				break
			peak_alive = maxi(peak_alive, int(result.alive))
			if frame in [2, 5, 11, 23, 35]:
				await process_frame
				await RenderingServer.frame_post_draw
				var image := root.get_texture().get_image()
				peak_pixels = maxi(peak_pixels, _different_pixels(baseline, image))
				var output := ProjectSettings.globalize_path(
					"res://effect-%02d-frame-%02d.png" % [i, frame + 1]
				)
				_check("capture saved", image.save_png(output) == OK)
		_check("effect visibly rendered", peak_pixels > 16)
		_check("effect emitted particles", peak_alive > 0)
		effect.queue_free()
		await process_frame
		await RenderingServer.frame_post_draw
	await _attachment_lifecycle(world, camera, catalog, textures)
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)


func _different_pixels(before: Image, after: Image) -> int:
	var count := 0
	for y: int in range(0, after.get_height(), 2):
		for x: int in range(0, after.get_width(), 2):
			var a := before.get_pixel(x, y)
			var b := after.get_pixel(x, y)
			if absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b) > 0.02:
				count += 1
	return count


func _style_checks(source: Dictionary) -> void:
	var color := Style.packed_color([[0, 255, 128, 0, 255], [1, 0, 128, 255, 0]], 0.5)
	_check(
		"packed term truncation",
		is_equal_approx(color.r, 127.0 / 255) and is_equal_approx(color.b, 127.0 / 255)
	)
	_check("constant packed channel", is_equal_approx(color.g, 128.0 / 255))
	var recipe := source.duplicate(true)
	recipe.particle.textures = ["one", "two", "three"]
	recipe.particle.TexAniType = 1
	recipe.particle.TexAniDelay = 0.125
	recipe.particle.TexAniRandomStartFrameEnable = 0
	recipe.particle.RotationRandomStartingBegin = 0
	recipe.particle.RotationRandomStartingEnd = 0
	recipe.particle.RotationType = 2
	var rng := RandomNumberGenerator.new()
	rng.seed = 1
	var particle := {"age": 0.0, "lifetime": 1.0}
	Style.initialize(particle, recipe, rng)
	particle.rotation_speed = 100.0
	Style.advance(particle, recipe, 0.125, rng)
	_check("texture exact deadline stays", particle.frame == 0)
	_check("rotation degrees per second", particle.rotation == 12.5)
	Style.advance(particle, recipe, 0.125, rng)
	_check("texture advances past deadline", particle.frame == 1)
	Style.advance(particle, recipe, 0.5, rng)
	_check("texture wraps multiple steps", particle.frame == 2)


func _geometry_checks(world: Node3D, camera: Camera3D, source: Dictionary) -> void:
	var effect := Effect.new()
	world.add_child(effect)
	var recipe := source.duplicate(true)
	recipe.particle.BillboardType = 3
	recipe.particle.StretchEnable = 0
	var particle := {
		"position": Vector3(2, 3, 4),
		"previous_position": Vector3(2, 3, 4),
		"attached": false,
		"rotation": 0.0,
		"half_size": Vector2(1, 2),
		"scale": Vector2.ONE
	}
	var corners: Array[Vector3] = effect._corners(particle, recipe, camera)
	_check("ground quad source corner", corners[0].is_equal_approx(Vector3(0, 3, 5)))
	_check("ground quad opposite corner", corners[3].is_equal_approx(Vector3(4, 3, 3)))
	var old_basis := camera.basis
	camera.rotate_y(0.7)
	_check(
		"ground quad ignores camera heading", effect._corners(particle, recipe, camera) == corners
	)
	camera.basis = old_basis
	particle.rotation = 90.0
	corners = effect._corners(particle, recipe, camera)
	_check("ground quarter turn", corners[0].is_equal_approx(Vector3(1, 3, 2)))
	var flat_camera := Camera3D.new()
	world.add_child(flat_camera)
	particle.rotation = 0.0
	recipe.particle.BillboardType = 2
	corners = effect._corners(particle, recipe, flat_camera)
	_check("Y billboard vertical edge", corners[0].is_equal_approx(Vector3(3, 1, 4)))
	_check("Y billboard opposite edge", corners[3].is_equal_approx(Vector3(1, 5, 4)))
	particle.rotation = 90.0
	corners = effect._corners(particle, recipe, flat_camera)
	_check("Y billboard local rotation", corners[0].is_equal_approx(Vector3(1, 5, 4)))
	particle.rotation = 0.0
	recipe.particle.BillboardType = 4
	corners = effect._corners(particle, recipe, flat_camera, -PI / 6.0)
	_check("two-face billboard rotated edge", corners[0].is_equal_approx(Vector3(2.866025, 1, 4.5)))
	recipe.particle.BillboardType = 5
	corners = effect._corners(particle, recipe, flat_camera)
	_check("three-face billboard center edge", corners[0].is_equal_approx(Vector3(3, 1, 4)))
	corners = effect._corners(particle, recipe, flat_camera, PI / 3.0)
	_check(
		"three-face billboard rotated edge", corners[0].is_equal_approx(Vector3(2.5, 1, 3.133975))
	)
	recipe.particle.BillboardType = 3
	particle.rotation = 90.0
	effect.position = Vector3(10, 0, 0)
	particle.attached = true
	corners = effect._corners(particle, recipe, camera)
	_check("attached ground center follows emitter", corners[0].is_equal_approx(Vector3(11, 3, 2)))
	flat_camera.queue_free()
	effect.queue_free()


func _attachment_lifecycle(
	world: Node3D, camera: Camera3D, catalog: Dictionary, textures: Dictionary
) -> void:
	var manager := WorldEffects.new()
	world.add_child(manager)
	_check("world effect catalog", manager.configure(catalog.effects, textures))
	var actor := Actor.new()
	world.add_child(actor)
	_check("bind effect actor", manager.bind_actor(actor, 180))
	_check("duplicate binding rejected", not manager.bind_actor(actor, 180))
	var event := {
		"effect_path": catalog.effects[0].effect_path,
		"attachment": "follow_root",
		"position_m": [1, 0, 0],
		"bone": ""
	}
	actor.motion_effect_requested.emit(event)
	event.attachment = "capture_root"
	actor.motion_effect_requested.emit(event)
	_check("two instances spawned", manager._instances.size() == 2)
	actor.model = Node3D.new()
	actor.add_child(actor.model)
	var skeleton := Skeleton3D.new()
	actor.model.add_child(skeleton)
	skeleton.add_bone("hand")
	skeleton.set_bone_pose_position(0, Vector3(0, 2, 0))
	event.attachment = "follow_bone"
	event.bone = "hand"
	actor.motion_effect_requested.emit(event)
	_check("bone instance spawned", manager._instances.size() == 3)
	actor.position = Vector3(2, 0, 0)
	_check("effect simulation step", manager.advance(1.0 / 60, camera))
	_check(
		"follow transform updates",
		manager._instances[0].node.global_position.is_equal_approx(Vector3(1, 0, 0))
	)
	_check(
		"capture preserves spawn transform",
		manager._instances[1].node.global_position.is_equal_approx(Vector3(-1, 0, 0))
	)
	skeleton.set_bone_pose_position(0, Vector3(0, 3, 0))
	_check("animated bone simulation step", manager.advance(1.0 / 60, camera))
	_check(
		"bone follows animated pose and actor",
		manager._instances[2].node.global_position.is_equal_approx(Vector3(1, 3, 0))
	)
	actor.queue_free()
	await actor.tree_exited
	_check("owner removal cleans following effect", manager._instances.size() == 1)
	_check("owner binding removed", manager._bindings.is_empty())
	_check("captured effect survives owner", manager.advance(1.0 / 60, camera))
	for unused: int in range(1200):
		if manager._instances.is_empty():
			break
		manager.advance(1.0 / 60, camera)
	_check("finite captured effect drains", manager._instances.is_empty())
	_check("no lifecycle errors", manager.error_message.is_empty())
	_check("invalid timestep rejects", not manager.advance(NAN, camera))
	manager.queue_free()
	await process_frame
