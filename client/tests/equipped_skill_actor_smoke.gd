extends "res://tests/actor_smoke.gd"
## Selected live Warrior skills with original sword attachment on both appearances.


func _run() -> void:
	root.size = Vector2i(1280, 800)
	if not _catalog.load_required(ActorCatalog.MANIFEST_PATH, true):
		_check(false, "equipped skill catalog loads")
		_finish()
		return
	_build_stage()
	await _test_skill_appearances()
	_finish()


func _test_skill_appearances() -> void:
	for actor_id: String in ["actor.player.warrior-male", "actor.player.warrior-female"]:
		var actor := ActorPresentation.new()
		_check(actor.configure(_catalog, actor_id), actor_id + " configures skill model")
		_stage.add_child(actor)
		_check(actor.set_weapon(10), actor_id + " attaches sword for skill")
		for skill: Dictionary in _catalog.skills.available(0):
			var action_id := actor_id + ".general." + str(skill.motion)
			var motion: Dictionary = _catalog.motion(actor_id, "general", action_id)
			for fraction: float in [0.15, 0.35, 0.6, 0.85]:
				var sample_us := int(float(motion.duration_us) * fraction)
				_check(
					actor.play_action(
						"onehand", action_id, "", sample_us, 1000000, 1000000 + sample_us
					),
					actor_id + " resolves equipped skill across motion modes"
				)
				actor.animation_player.advance(0.13)
				actor.animation_player.seek(float(sample_us) / 1000000.0, true)
				actor.animation_player.advance(0.0)
				actor.animation_player.pause()
				await process_frame
				_check(_skeleton_pose_is_sane(actor), actor_id + " skill deformation stays bounded")
				_check(
					_equipment_bounds_are_sane(actor),
					actor_id + " skill keeps bounded sword attachment"
				)
				_check(
					actor.snapshot().action_id == action_id, actor_id + " uses original skill clip"
				)
				var center := _skeleton_pose_center(actor)
				await _capture_from(
					actor_id.get_slice(".", 2) + "-" + str(skill.motion) + "-%d" % sample_us,
					center + Vector3(2.0, 0.8, -3.0),
					center
				)
		actor.queue_free()
		await process_frame
