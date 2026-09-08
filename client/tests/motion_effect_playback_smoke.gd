extends SceneTree

const Actor = preload("res://scripts/actors/actor_presentation.gd")
var _checks := 0
var _failures: Array[String] = []
var _events: Array[String] = []
var _projectiles: Array[Vector3] = []


func _init() -> void:
	call_deferred("_run")


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)


func _run() -> void:
	var actor := Actor.new()
	root.add_child(actor)
	actor.set_process(false)
	var player := AnimationPlayer.new()
	actor.add_child(player)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := AnimationLibrary.new()
	var clip := Animation.new()
	clip.length = 1.0
	library.add_animation("skill", clip)
	player.add_animation_library("", library)
	actor.animation_player = player
	actor._clips = {"skill": "skill"}
	player.animation_finished.connect(actor._on_animation_finished)
	actor.motion_effect_requested.connect(_record)
	actor.projectile_launched.connect(
		func(_definition: Dictionary, origin: Vector3) -> void: _projectiles.append(origin)
	)
	var motion := {
		"action_id": "skill",
		"godot_name": "skill",
		"duration_us": 1000000,
		"effects":
		[
			{"source_event": "a", "start_us": 250000},
			{"source_event": "b", "start_us": 500000},
			{"source_event": "missing", "start_us": 500000, "enabled": false},
			{"source_event": "end", "start_us": 1000000},
		]
	}
	_check("start", actor._play_motion(motion, "general", 1, 0, 0, false, 1.0))
	player.advance(0.249)
	actor._process(0.249)
	_check("before boundary", _events.is_empty())
	player.advance(0.001)
	actor._process(0.001)
	_check("at boundary", _events == ["a"])
	actor._process(0)
	_check("no repeat", _events == ["a"])
	_check("same forced resync", actor._play_motion(motion, "general", 1, 0, 0, true, 1.0))
	player.advance(0.5)
	actor._process(0.5)
	_check("resync and disabled event", _events == ["a", "b"])
	player.advance(0.6)
	_check("finish drains unpolled event", _events == ["a", "b", "end"])
	actor._on_animation_finished("skill")
	_check("finish does not duplicate", _events.size() == 3)
	_events.clear()
	_check(
		"late subscription", actor._play_motion(motion, "general", 2, 1000000, 1500000, false, 1.0)
	)
	actor._process(0)
	_check("skip past but include exact boundary", _events == ["b"])
	actor.reset_action()
	_events.clear()
	_check(
		"new sequence accelerated",
		actor._play_motion(motion, "general", 3, 1000000, 1200000, false, 1.5)
	)
	actor._process(0)
	_check("late offset uses animation speed", _events.is_empty())
	player.advance(0.14)
	actor._process(0.14)
	_check("accelerated event clock", _events == ["b"])
	actor.freeze_at_end()
	actor._process(0)
	_check("frozen pose emits nothing", _events == ["b"])
	actor.reset_action()
	_events.clear()
	_check(
		"reset allows original sequence", actor._play_motion(motion, "general", 1, 0, 0, false, 1.0)
	)
	player.advance(1.1)
	_check("long frame drains every enabled event", _events == ["a", "b", "end"])
	actor.reset_action()
	_events.clear()
	var projectile_motion := motion.duplicate(true)
	projectile_motion.erase("effects")
	projectile_motion.projectile_launches = [
		{
			"source_event": "fly",
			"start_us": 250000,
			"attached": false,
			"source_position_cm": [100, 200, 300]
		}
	]
	_check(
		"projectile-only motion",
		actor._play_motion(projectile_motion, "general", 4, 0, 0, false, 1.0)
	)
	player.advance(0.5)
	actor._process(0.5)
	_check("legacy projectile dispatch preserved", _projectiles == [Vector3(1, 3, -2)])
	_check("no effects required for legacy motion", _events.is_empty())
	_attachment_checks(actor)
	actor.queue_free()
	await process_frame
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)


func _record(event: Dictionary) -> void:
	_events.append(str(event.source_event))
	# Signal receivers must not mutate catalog metadata.
	event.start_us = -1


func _attachment_checks(actor: Node3D) -> void:
	actor.model = Node3D.new()
	actor.add_child(actor.model)
	var skeleton := Skeleton3D.new()
	actor.model.add_child(skeleton)
	skeleton.add_bone("hand")
	skeleton.set_bone_pose_position(0, Vector3(1, 2, 3))
	skeleton.set_bone_pose_rotation(0, Quaternion(Vector3.UP, PI / 2))
	actor.position = Vector3(10, 0, 0)
	var effect := {"attachment": "follow_root", "position_m": [1, 0, 0]}
	var result: Dictionary = actor.motion_effect_transform(effect, 180.0)
	_check(
		"source yaw rotates root offset", result.transform.origin.is_equal_approx(Vector3(9, 0, 0))
	)
	effect.attachment = "follow_bone"
	effect.bone = "hand"
	result = actor.motion_effect_transform(effect, 180.0)
	_check(
		"offset does not rotate with hand",
		result.transform.origin.is_equal_approx(Vector3(10, 2, 3))
	)
	_check(
		"bone axes converted for effect geometry",
		result.transform.basis.is_equal_approx(
			Basis(Vector3.UP, PI / 2) * Basis(Vector3.RIGHT, PI / 2)
		)
	)
	effect.bone = "missing"
	_check(
		"missing resolved bone rejects", actor.motion_effect_transform(effect, 180.0).has("error")
	)
	effect.attachment = "follow_root"
	effect.position_m = [NAN, 0, 0]
	_check("nonfinite offset rejects", actor.motion_effect_transform(effect, 180.0).has("error"))
