extends SceneTree

const Projectile = preload("res://scripts/actors/projectile_effect.gd")
const Trail = preload("res://scripts/actors/projectile_trail.gd")
var _checks := 0
var _failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)


func _capture(name: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	_check(
		"capture saved",
		image.save_png(ProjectSettings.globalize_path("res://effect-" + name + ".png")) == OK
	)


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		quit(1)
		return
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var inventory: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var effects: Dictionary = {}
	for effect: Dictionary in catalog.effects:
		effects[effect.effect_path] = effect
	var textures: Dictionary = {}
	for path: String in catalog.textures:
		textures[path] = ImageTexture.create_from_image(
			Image.load_from_file(args[0].get_base_dir().path_join(catalog.textures[path].path))
		)
	root.size = Vector2i(800, 480)
	var world := Node3D.new()
	root.add_child(world)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.position = Vector3(0, 4, 8)
	camera.look_at(Vector3.ZERO)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 9
	camera.current = true
	var start := Vector3(-3, 0, 0)
	var target := Vector3(3, 0, 0)
	for index: int in range(3):
		var definition: Dictionary = inventory.flight_definitions[index]
		var projectile := Projectile.new()
		world.add_child(projectile)
		_check(
			"flight configures",
			projectile.configure(definition, effects, textures, start, target, 42, 1.0 / 60.0)
		)
		var hits := 0
		var done := false
		var previous := start
		var moved := false
		for frame: int in range(360):
			var state: Dictionary = projectile.advance(1.0 / 60.0, target, camera)
			if state.has("error"):
				_check("flight step accepted", false)
				break
			if state.event == "flying":
				moved = moved or projectile.flight.position.distance_to(previous) > 0.01
				previous = projectile.flight.position
				if definition.attachments.size() == 2:
					var a: Transform3D = projectile.attachment_transform(definition.attachments[0])
					var b: Transform3D = projectile.attachment_transform(definition.attachments[1])
					_check(
						"paired attachment separation",
						is_equal_approx(a.origin.distance_to(b.origin), 0.6)
					)
			if frame in [3, 7]:
				await _capture("flight-%d-frame-%d" % [index, frame + 1])
			if state.event == "target_hit":
				hits += 1
				_check("attachments removed at hit", state.attachments == 0)
				_check("independent impact survives hit", state.impacts == 1)
				await _capture("flight-%d-impact" % index)
			if state.done:
				done = true
				break
		_check("flight moves and hits once", moved and hits == 1)
		_check("impact drains to completion", done)
		projectile.queue_free()
		await process_frame
	var arrow := Projectile.new()
	world.add_child(arrow)
	_check(
		"unimplemented mesh flight rejects",
		not arrow.configure(inventory.flight_definitions[3], effects, textures, start, target, 1, 0)
	)
	arrow.queue_free()
	var short: Dictionary = inventory.flight_definitions[0].duplicate(true)
	short.flight.Range = 10
	var expired := Projectile.new()
	world.add_child(expired)
	_check(
		"failed texture load rejects",
		not expired.configure(short, effects, {}, start, target, 1, 0)
	)
	_check(
		"retry after failed setup", expired.configure(short, effects, textures, start, target, 1, 0)
	)
	var state: Dictionary = expired.advance(1.0 / 60.0, target, camera)
	_check(
		"range expiry has no impact",
		state.event == "out_of_range" and state.impacts == 0 and state.done
	)
	expired.queue_free()
	var trail := Trail.new()
	world.add_child(trail)
	_check(
		"negative source trail accepted",
		trail.configure(inventory.flight_definitions[0].attachments[0].tail)
	)
	_check("negative trail update", trail.advance(0, start, camera))
	_check("negative source trail has no history", trail.history.is_empty())
	_check(
		"positive trail configures",
		trail.configure(inventory.flight_definitions[2].attachments[0].tail)
	)
	trail.advance(0, start, camera)
	trail.advance(0.1, target, camera)
	_check("history equality boundary retained", trail.history.size() == 2)
	trail.advance(0.1001, target, camera)
	_check("old trail sample expires", is_equal_approx(float(trail.history.back().time), 0.1))
	trail.queue_free()
	await process_frame
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)
