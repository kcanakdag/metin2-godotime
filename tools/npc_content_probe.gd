extends SceneTree
## Isolated converted NPC inspection; never installed in the playable client.

var _failed := false
var _checks := 0
var _motions: Array = []


func _initialize() -> void:
	_run.call_deferred()


func _check(passed: bool, description: String) -> bool:
	_checks += 1
	if not passed:
		push_error("NPC_CONTENT_PROBE FAIL " + description)
		_failed = true
	return passed


func _pose(skeleton: Skeleton3D) -> Array[Transform3D]:
	var result: Array[Transform3D] = []
	for index in skeleton.get_bone_count():
		result.append(skeleton.get_bone_global_pose(index))
	return result


func _verify_actor(instance: Node3D, actor: Dictionary) -> void:
	var skeletons := instance.find_children("*", "Skeleton3D", true, false)
	var players := instance.find_children("*", "AnimationPlayer", true, false)
	if not _check(
		skeletons.size() == 1 and players.size() == 1, "one skeleton and animation player"
	):
		return
	var skeleton := skeletons[0] as Skeleton3D
	var player := players[0] as AnimationPlayer
	var expected: Array = []
	for mode: Dictionary in actor.modes:
		for motion: Dictionary in mode.motions:
			expected.append(str(motion.godot_name))
			if not _check(player.has_animation(motion.godot_name), "clip " + str(motion.action_id)):
				continue
			var animation := player.get_animation(motion.godot_name)
			_check(
				absf(animation.length * 1_000_000.0 - float(motion.duration_us)) <= 1.0,
				"source duration"
			)
			player.play(motion.godot_name)
			player.seek(0.0, true)
			var before := _pose(skeleton)
			player.seek(animation.length * 0.5, true)
			var after := _pose(skeleton)
			var delta := 0.0
			for index in before.size():
				delta = maxf(delta, before[index].origin.distance_to(after[index].origin))
				for axis in 3:
					delta = maxf(
						delta, before[index].basis[axis].distance_to(after[index].basis[axis])
					)
			_check(delta > 0.000001, "evaluated pose changes")
			_motions.append(
				{"id": motion.action_id, "duration_us": motion.duration_us, "pose_delta": delta}
			)
	var actual := Array(player.get_animation_list())
	actual.sort()
	expected.sort()
	_check(actual == expected, "exact declared clip set")
	for node: MeshInstance3D in instance.find_children("*", "MeshInstance3D", true, false):
		_check(
			node.skin != null and node.get_node_or_null(node.skeleton) == skeleton,
			"every actor mesh follows the skeleton"
		)
		for surface in node.mesh.get_surface_count():
			var material := node.get_active_material(surface) as StandardMaterial3D
			_check(material != null and material.albedo_texture != null, "textured mesh surface")
	_show_idle(instance, actor)


func _show_idle(instance: Node3D, actor: Dictionary) -> void:
	var player := instance.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	for mode: Dictionary in actor.modes:
		for motion: Dictionary in mode.motions:
			if motion.action == "wait":
				player.play(motion.godot_name)
				player.seek(0.0, true)
				player.pause()
				return


func _view(packed: PackedScene, label_text: String, yaw: float) -> Node3D:
	var container := VBoxContainer.new()
	root.get_node("Grid").add_child(container)
	var label := Label.new()
	label.text = label_text
	container.add_child(label)
	var view_container := SubViewportContainer.new()
	view_container.custom_minimum_size = Vector2(640, 360)
	container.add_child(view_container)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(640, 360)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	view_container.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.14, 0.16, 0.19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.7
	world.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	world.add_child(light)
	var actor := packed.instantiate() as Node3D
	actor.rotation.y = yaw
	world.add_child(actor)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 2.8
	world.add_child(camera)
	camera.position = Vector3(0, 1.1, -5)
	camera.look_at(Vector3(0, 1.1, 0))
	camera.current = true
	return actor


func _run() -> void:
	var manifest: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://normalized.v1.json")
	)
	var actor: Dictionary = manifest.actors[0]
	var packed := load("res://generated/" + str(actor.output)) as PackedScene
	if not _check(packed != null, "NPC GLB imports"):
		quit(1)
		return
	var grid := GridContainer.new()
	grid.name = "Grid"
	grid.columns = 2
	root.add_child(grid)
	var views := [
		["View from -Z", 0.0], ["View from +Z", PI], ["Side A", PI / 2], ["Side B", -PI / 2]
	]
	for index in views.size():
		var view: Array = views[index]
		var instance := _view(packed, str(view[0]), float(view[1]))
		if index == 0:
			_verify_actor(instance, actor)
		else:
			_show_idle(instance, actor)
	await process_frame
	await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://npc-preview.png")
	var file := FileAccess.open("user://npc-probe.json", FileAccess.WRITE)
	file.store_string(
		JSON.stringify({"passed": not _failed, "checks": _checks, "motions": _motions}, "\t")
	)
	file.close()
	print("NPC_CONTENT_PROBE ", "FAIL" if _failed else "PASS", " ", _checks, " checks")
	quit(1 if _failed else 0)
