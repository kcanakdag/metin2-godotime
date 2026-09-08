extends SceneTree

const Projectile = preload("res://scripts/actors/projectile_effect.gd")
const WorldProjectiles = preload("res://scripts/world/world_projectiles.gd")
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
	if args.size() not in [2, 3]:
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
	var meshes: Dictionary = {}
	if args.size() == 3:
		var mesh_catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[2]))
		for definition: Dictionary in mesh_catalog.meshes:
			meshes[mesh_catalog.source_effect] = {
				"definition": definition,
				"scene": load("res://" + str(definition.model)) as PackedScene,
				"texture": load("res://" + str(definition.geometries[0].texture)) as Texture2D
			}
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
	for index: int in range(4 if not meshes.is_empty() else 3):
		var definition: Dictionary = inventory.flight_definitions[index]
		var projectile := Projectile.new()
		world.add_child(projectile)
		_check(
			"flight configures",
			projectile.configure(
				definition, effects, textures, start, target, 42, 1.0 / 60.0, meshes
			)
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
	await _test_world_targets(world, camera, inventory, effects, textures, meshes)
	var arrow := Projectile.new()
	world.add_child(arrow)
	_check(
		"missing mesh resource rejects",
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


func _test_world_targets(
	world: Node3D,
	camera: Camera3D,
	inventory: Dictionary,
	effects: Dictionary,
	textures: Dictionary,
	meshes: Dictionary
) -> void:
	var targets := {
		"near": {"identity": "near", "life_sequence": 3, "position": Vector3(-2, 0, 0)},
		"selected": {"identity": "selected", "life_sequence": 3, "position": Vector3(3, 0, 0)}
	}
	var flights := {}
	for definition: Dictionary in inventory.flight_definitions:
		flights[definition.path] = definition
	for index: int in range(4 if not meshes.is_empty() else 3):
		var manager := WorldProjectiles.new()
		world.add_child(manager)
		_check(
			"world resources configure",
			manager.configure(
				flights, effects, textures, meshes, func(id: String): return targets.get(id, {})
			)
		)
		var row := {
			"id": 10,
			"life_sequence": 0,
			"attack_sequence": index + 1,
			"attack_action_id": "selected.attack",
			"action_started_at_us": 1000,
			"activity": 2,
			"attack_target": "selected",
			"attack_target_life_sequence": 3
		}
		var event := {
			"source_event": "Event00", "fly_definition": inventory.flight_definitions[index].path
		}
		targets.selected = {
			"identity": "selected", "life_sequence": 4, "position": Vector3(3, 0, 0)
		}
		_check(
			"new target life cannot receive old launch",
			not manager.launch(row, event, Vector3(-3, 0, 0), 0)
		)
		targets.selected.life_sequence = 3
		_check("matching target launch accepted", manager.launch(row, event, Vector3(-3, 0, 0), 0))
		_check("duplicate launch rejected", not manager.launch(row, event, Vector3(-3, 0, 0), 0))
		_check("world first step", manager.advance(1.0 / 60, camera))
		_check(
			"server selected target beats nearer player",
			manager.snapshot()[0].target_position == Vector3(3, 0, 0)
		)
		var before := manager.snapshot()
		_check("invalid step rejects", not manager.advance(NAN, camera))
		_check("invalid step preserves flights", manager.snapshot() == before)
		targets.selected.position = Vector3(3, 0.1, 0)
		manager.advance(1.0 / 60, camera)
		_check(
			"same target life moves", manager.snapshot()[0].target_position == Vector3(3, 0.1, 0)
		)
		if index % 2 == 0:
			targets.erase("selected")
		else:
			targets.selected.life_sequence = 4
		manager.advance(1.0 / 60, camera)
		_check("lost target becomes position", not manager.snapshot()[0].object_target)
		targets.selected = {
			"identity": "selected", "life_sequence": 3, "position": Vector3(20, 5, 0)
		}
		manager.advance(1.0 / 60, camera)
		_check(
			"returning identity cannot reacquire flight",
			(
				not manager.snapshot()[0].object_target
				and manager.snapshot()[0].target_position == Vector3(3, 0.1, 0)
			)
		)
		manager.forget_actor(10)
		_check("flight outlives source removal", manager.snapshot().size() == 1)
		await _capture("world-flight-%d" % index)
		for frame: int in range(600):
			if manager.snapshot().is_empty():
				break
			if not manager.advance(1.0 / 60, camera):
				_check("world flight update", false)
				break
		_check("world flight and impact clean up", manager.snapshot().is_empty())
		targets.selected.position = Vector3(3, 0, 0)
		row.attack_sequence += 10
		_check("later attack can launch", manager.launch(row, event, Vector3(-3, 0, 0), 0))
		manager.clear()
		_check("disconnect clears every flight", manager.snapshot().is_empty())
		manager.queue_free()
		await process_frame
