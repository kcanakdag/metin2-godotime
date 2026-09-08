extends "res://tests/actor_smoke.gd"
## Real converted fan, both Shaman skeletons, and held-intent timing boundaries.

const AttackInput = preload("res://scripts/actors/attack_input.gd")


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_check(_catalog.load_required(), "fan and character catalogs load")
	if _failed:
		_finish()
		return
	_build_stage()
	for sex in 2:
		await _shaman(sex)
	_finish()


func _shaman(sex: int) -> void:
	var player := PlayerActor.new()
	player.configure(_catalog)
	_stage.add_child(player)
	var row := _player_row()
	row.name = "Shaman (%s)" % ("male" if sex == 0 else "female")
	var appearance := _appearance(7000)
	appearance.character_class = 3
	appearance.sex = sex
	var actor_id := _catalog.player_actor_id(appearance)
	player.apply_state(row, true, appearance, 1_000_000)
	await process_frame
	var state := player.presentation_snapshot()
	_check(state.weapon_vnum == 7000 and state.equipment_attached, "fan attaches to Shaman")
	_check(state.mode == "fan" and ".fan.wait" in state.action_id, "equipped fan idle")
	_check(_equipment_bounds_are_sane(player, 7000), "fan bounds and grip use meters")
	_check(_skinned_meshes(player) > 0, "original Shaman skin is present")
	await _capture_from("fan-%d-idle" % sex, Vector3(2.2, 1.4, -3.2), player.position)
	for step in range(1, 5):
		var motion := _catalog.motion(actor_id, "fan", "", "combo_%d" % step)
		row.activity = 2
		row.attack_speed_percent = 126
		row.attack_sequence = step
		row.attack_action_id = motion.action_id
		row.action_started_at_us = 2_000_000
		row.action_ends_at_us = 2_000_000 + _scaled(int(motion.duration_us))
		player.apply_state(row, true, appearance, 2_300_000)
		await process_frame
		state = player.presentation_snapshot()
		_check(state.action_id == motion.action_id and state.equipment_attached, "fan combo clip")
		_check(is_equal_approx(float(state.animation_speed), 1.26), "captured fan playback rate")
		_check(
			absf(float(state.animation_position) - 0.378) < 0.08,
			"late subscription seeks the sped-up pose"
		)
		_check(_skeleton_pose_is_sane(player), "Shaman attack remains in meter bounds")
		var hit: Dictionary = motion.events.filter(func(event): return event.kind == "attack_window")[0]
		var sample: Dictionary = hit.samples[int(hit.samples.size() / 2.0)]
		var presentation := player.get_node("Visual") as ActorPresentation
		presentation.animation_player.play(str(motion.godot_name), 0.0)
		presentation.animation_player.seek(float(sample.time_us) / 1_000_000.0, true)
		presentation.animation_player.advance(0.0)
		presentation.animation_player.pause()
		await process_frame
		var landmark := _equipment_landmark(player, sample, 7000, float(hit.weapon_length_m))
		print(
			"FAN_LANDMARK_EVIDENCE ",
			JSON.stringify({"sex": sex, "step": step, "source_landmark": landmark})
		)
		var skeleton := _find_skeleton(player)
		var attachment := player.find_child("Equipment_7000", true, false) as BoneAttachment3D
		var bone_pose := (
			skeleton.global_transform
			* skeleton.get_bone_global_pose(skeleton.find_bone("equip_right"))
		)
		_check(
			attachment.global_transform.is_equal_approx(bone_pose),
			"fan follows the authored right-hand bone"
		)
		if sex == 1:
			_check(
				(
					float(landmark.get("hand_error_m", INF)) < 0.05
					and float(landmark.get("direction_dot", -1.0)) > 0.98
					and float(landmark.get("endpoint_error_m", INF)) < 0.15
				),
				"female fan attachment matches source landmarks: %s" % landmark
			)
		else:
			# The pinned male MSA copies female hit geometry despite distinct GR2
			# poses. It is not a valid male rig landmark; retain it as source data.
			var female := _catalog.motion(
				"actor.player.shaman-female", "fan", "", "combo_%d" % step
			)
			_check(
				_first_attack_window(female).samples == hit.samples,
				"pinned male hit metadata reuses the female samples"
			)
		await _capture_from(
			"fan-%d-combo-%d" % [sex, step], Vector3(2.2, 1.4, -3.2), player.position
		)
		var held := AttackInput.new()
		held.pressed({"attack_sequence": step - 1}, 1000)
		var pre := _scaled(int(motion.combo.pre_input_us) if step < 4 else int(motion.duration_us))
		_check(
			not held.should_send(row, _catalog, 2_000_000 + pre, 1300, actor_id), "no early link"
		)
		if step < 4:
			_check(
				held.should_send(row, _catalog, 2_040_000 + pre, 1400, actor_id), "fan link window"
			)
			_check(
				not held.should_send(row, _catalog, 2_060_000 + pre, 1600, actor_id),
				"no duplicate link"
			)
		held.release()
		_check(
			not held.should_send(row, _catalog, 2_080_000 + pre, 1800, actor_id),
			"release stops input"
		)
	row.activity = 0
	row.action_ends_at_us = 0
	player.apply_state(row, true, appearance, 4_000_000)
	_check(
		is_equal_approx(float(player.presentation_snapshot().animation_speed), 1.0),
		"idle resets playback speed"
	)
	player.queue_free()
	await process_frame


func _scaled(source_us: int) -> int:
	return preload("res://scripts/actors/attack_timing.gd").scaled_us(source_us, 126)
