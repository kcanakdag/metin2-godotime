extends "res://tests/actor_smoke.gd"
## Qualifies every selected skill clip for both appearances without a game server.


func _run() -> void:
	root.size = Vector2i(1280, 800)
	if not _catalog.load_required(ActorCatalog.MANIFEST_PATH, true):
		_check(false, "all-class catalog loads")
		_finish()
		return
	_build_stage()
	var count := 0
	for definition: Dictionary in _catalog.characters.document.actors:
		var actor := ActorPresentation.new()
		_check(actor.configure(_catalog, str(definition.id)), "class skill actor configures")
		_stage.add_child(actor)
		for mode: Dictionary in definition.modes:
			for motion: Dictionary in mode.motions:
				if not str(motion.action).begins_with("skill_"):
					continue
				count += 1
				var poses: Array[PackedFloat32Array] = []
				for fraction: float in [0.15, 0.5, 0.85]:
					var offset := int(float(motion.duration_us) * fraction)
					_check(
						actor.play_action(
							"general", str(motion.action_id), "", offset, 1000000, 1000000 + offset
						),
						str(motion.action_id) + " plays original motion"
					)
					# Finish the normal transition before measuring the imported pose.
					actor.animation_player.advance(0.13)
					actor.animation_player.seek(float(offset) / 1000000.0, true)
					actor.animation_player.advance(0.0)
					actor.animation_player.pause()
					await process_frame
					poses.append(_pose_values(actor))
					_check(
						_skeleton_pose_is_sane(actor),
						str(motion.action_id) + " finite bounded pose"
					)
					if fraction == 0.5:
						var center := _skeleton_pose_center(actor)
						await _capture_from(
							str(definition.id).get_slice(".", 2) + "-" + str(motion.action),
							center + Vector3(2.0, 0.8, -3.0),
							center
						)
				_check(
					poses[0] != poses[1] or poses[1] != poses[2],
					str(motion.action_id) + " animates its skeleton"
				)
		actor.queue_free()
		await process_frame
	_check(count == 88, "all 44 class skills have both appearances")
	_finish()


func _pose_values(actor: Node) -> PackedFloat32Array:
	var skeleton := _find_skeleton(actor)
	var result := PackedFloat32Array()
	for index in skeleton.get_bone_count():
		var position := skeleton.get_bone_pose_position(index)
		var rotation := skeleton.get_bone_pose_rotation(index)
		result.append_array(
			[position.x, position.y, position.z, rotation.x, rotation.y, rotation.z, rotation.w]
		)
	return result
