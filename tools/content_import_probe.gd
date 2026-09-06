extends SceneTree


func _transform_delta(left: Transform3D, right: Transform3D) -> float:
	var result := left.origin.distance_to(right.origin)
	for axis in 3:
		result = maxf(result, left.basis[axis].distance_to(right.basis[axis]))
	return result


func _pose(skeleton: Skeleton3D) -> Array[Transform3D]:
	var result: Array[Transform3D] = []
	for index in skeleton.get_bone_count():
		result.append(skeleton.get_bone_global_pose(index))
	return result


func _max_pose_delta(left: Array[Transform3D], right: Array[Transform3D]) -> float:
	var result := 0.0
	for index in left.size():
		result = maxf(result, _transform_delta(left[index], right[index]))
	return result


func _global_rest_position(skeleton: Skeleton3D, bone_name: String) -> Vector3:
	var index := skeleton.find_bone(bone_name)
	if index < 0:
		assert(false, "Missing facing marker bone: " + bone_name)
	return (skeleton.global_transform * skeleton.get_bone_global_rest(index)).origin


func _global_scale(node: Node3D) -> Array[float]:
	var basis := node.global_transform.basis
	return [basis.x.length(), basis.y.length(), basis.z.length()]


func _mesh_bounds(root: Node) -> AABB:
	var initialized := false
	var result := AABB()
	for candidate in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := candidate as MeshInstance3D
		var local := mesh.get_aabb()
		for x in [local.position.x, local.end.x]:
			for y in [local.position.y, local.end.y]:
				for z in [local.position.z, local.end.z]:
					var point := mesh.global_transform * Vector3(x, y, z)
					if initialized:
						result = result.expand(point)
					else:
						result = AABB(point, Vector3.ZERO)
						initialized = true
	assert(initialized, "Instantiated resource has no MeshInstance3D")
	return result


func _actor_probe(actor: Dictionary) -> Dictionary:
	var packed := load(actor.model.path) as PackedScene
	assert(packed != null, "Could not load " + actor.model.path)
	var instance := packed.instantiate() as Node3D
	root.add_child(instance)
	var skeletons := instance.find_children("*", "Skeleton3D", true, false)
	var players := instance.find_children("*", "AnimationPlayer", true, false)
	assert(skeletons.size() == 1, "Expected one Skeleton3D for " + actor.id)
	assert(players.size() == 1, "Expected one AnimationPlayer for " + actor.id)
	var skeleton := skeletons[0] as Skeleton3D
	var player := players[0] as AnimationPlayer
	var expected: Array[String] = []
	for mode in actor.modes:
		for motion in mode.motions:
			expected.append(motion.godot_name)
	var actual: Array[String] = []
	var expected_durations: Dictionary = {}
	for mode in actor.modes:
		for motion in mode.motions:
			expected_durations[motion.godot_name] = motion.duration_us
	var animation_results: Array[Dictionary] = []
	for library_name in player.get_animation_library_list():
		var library := player.get_animation_library(library_name)
		for animation_name in library.get_animation_list():
			actual.append(animation_name)
			var animation := library.get_animation(animation_name)
			var duration_error_us: float = absf(
				animation.length * 1_000_000.0 - expected_durations[animation_name]
			)
			assert(
				duration_error_us <= 1.0, "Imported animation duration differs: " + animation_name
			)
			var playback_name := String(animation_name)
			if not String(library_name).is_empty():
				playback_name = String(library_name) + "/" + playback_name
			player.play(playback_name)
			player.seek(0.0, true)
			var before := _pose(skeleton)
			player.seek(animation.length * 0.5, true)
			var after := _pose(skeleton)
			var delta := _max_pose_delta(before, after)
			assert(delta > 0.000001, "Animation has no evaluated pose change: " + playback_name)
			(
				animation_results
				. append(
					{
						"name": String(animation_name),
						"duration_s": animation.length,
						"duration_error_us": duration_error_us,
						"max_pose_delta": delta,
					}
				)
			)
	actual.sort()
	expected.sort()
	assert(actual == expected, "Imported animation names differ for " + actor.id)
	var rear_marker := "Bip01 Tail"
	if actor.kind == "player":
		rear_marker = "Bip01 Ponytail1"
	var rear := _global_rest_position(skeleton, rear_marker)
	var head := _global_rest_position(skeleton, "Bip01 Head")
	var heading := head - rear
	heading.y = 0.0
	var forward_dot := heading.normalized().dot(Vector3.FORWARD)
	assert(forward_dot > 0.9, "Actor does not face canonical Godot -Z: " + actor.id)
	return {
		"id": actor.id,
		"skeleton_bones": skeleton.get_bone_count(),
		"animations": animation_results,
		"forward_dot_negative_z": forward_dot,
		"instance": instance,
		"skeleton": skeleton,
	}


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	assert(args.size() == 2, "Usage: -- <manifest res://path> <report absolute path>")
	var manifest_file := FileAccess.open(args[0], FileAccess.READ)
	assert(manifest_file != null, "Could not read manifest")
	var manifest: Dictionary = JSON.parse_string(manifest_file.get_as_text())
	assert(typeof(manifest) == TYPE_DICTIONARY, "Manifest JSON is invalid")
	var actor_results: Array[Dictionary] = []
	var actor_nodes: Dictionary = {}
	for actor: Dictionary in manifest.actors:
		var result := _actor_probe(actor)
		actor_nodes[actor.id] = result
		(
			actor_results
			. append(
				{
					"id": result.id,
					"skeleton_bones": result.skeleton_bones,
					"animations": result.animations,
					"forward_dot_negative_z": result.forward_dot_negative_z,
				}
			)
		)
	var item: Dictionary = manifest.items[0]
	var sword_scene := load(item.model.path) as PackedScene
	assert(sword_scene != null, "Could not load sword")
	var sword := sword_scene.instantiate() as Node3D
	var warrior: Dictionary = actor_nodes["actor.player.warrior-male"]
	var skeleton := warrior.skeleton as Skeleton3D
	var attachment := BoneAttachment3D.new()
	attachment.bone_name = manifest.actors[0].attachment_bones[item.actor_attachment]
	skeleton.add_child(attachment)
	attachment.add_child(sword)
	await process_frame
	var sword_bounds := _mesh_bounds(sword)
	var longest_axis := maxf(sword_bounds.size.x, maxf(sword_bounds.size.y, sword_bounds.size.z))
	assert(longest_axis > 0.5 and longest_axis < 3.0, "Attached sword has implausible scale")
	var report := {
		"schema": "mt2spacetime.godot-content-import-report",
		"schema_version": 1,
		"profile_id": manifest.profile_id,
		"godot_version": Engine.get_version_info().string,
		"actors": actor_results,
		"attachment":
		{
			"bone": attachment.bone_name,
			"attachment_global_scale": _global_scale(attachment),
			"sword_root_global_scale": _global_scale(sword),
			"sword_global_bounds_m":
			{
				"position":
				[sword_bounds.position.x, sword_bounds.position.y, sword_bounds.position.z],
				"size": [sword_bounds.size.x, sword_bounds.size.y, sword_bounds.size.z],
			},
		},
		"status": "imported",
	}
	var output := FileAccess.open(args[1], FileAccess.WRITE)
	assert(output != null, "Could not open report path")
	output.store_string(JSON.stringify(report, "  ") + "\n")
	quit()


func _initialize() -> void:
	_run.call_deferred()
