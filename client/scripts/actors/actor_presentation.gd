class_name ActorPresentation
extends Node3D
## Shared model, manifest motion, and bone-equipment presentation.

signal motion_effect_requested(definition: Dictionary)

signal projectile_launched(definition: Dictionary, origin: Vector3)

var catalog: RefCounted
var motion_effect_catalog: RefCounted
var actor_id := ""
var error_message := ""
var model: Node3D
var animation_player: AnimationPlayer
var current_motion: Dictionary = {}
var current_mode := ""
var current_sequence := -1
var weapon_vnum := 0

var _definition: Dictionary = {}
var _clips: Dictionary = {}
var _equipment: Node3D
var _frozen_pose := false
var _consumed_launches: Dictionary = {}
var _consumed_effects: Dictionary = {}


func configure(value: RefCounted, definition_id: String) -> bool:
	catalog = value
	actor_id = definition_id
	_definition = catalog.actor(actor_id) if catalog else {}
	if _definition.is_empty():
		return _fail("Unknown actor presentation: " + actor_id)
	if is_inside_tree():
		return _build()
	return true


func _ready() -> void:
	if model == null and not _definition.is_empty():
		_build()


func play_action(
	mode_id: String,
	action_id: String,
	action: String,
	sequence: int,
	started_at_us: int = 0,
	server_time_us: int = 0,
	force := false,
	attack_speed_percent: int = 100
) -> bool:
	if attack_speed_percent < 100 or attack_speed_percent > 170:
		return _fail("Actor attack speed is outside the supported range.")
	var motion: Dictionary = catalog.motion(actor_id, mode_id, action_id, action)
	if motion.is_empty() and not action.is_empty():
		motion = catalog.select_motion(actor_id, mode_id, action, sequence)
	if motion.is_empty():
		return _fail(
			(
				"Actor %s has no motion for mode=%s action_id=%s action=%s."
				% [actor_id, mode_id, action_id, action]
			)
		)
	return _play_motion(
		motion,
		mode_id,
		sequence,
		started_at_us,
		server_time_us,
		force,
		float(attack_speed_percent) / 100.0
	)


func play_mob_action(
	mode_id: String,
	action_id: String,
	sequence: int,
	started_at_us: int,
	ends_at_us: int,
	server_time_us: int,
	force := false
) -> bool:
	if str(_definition.get("kind", "")) != "mob":
		return _fail("Timed mob playback requires an ordinary mob actor.")
	var motion: Dictionary = catalog.motion(actor_id, mode_id, action_id, "")
	var source_us := int(motion.get("duration_us", 0))
	var elapsed_us := ends_at_us - started_at_us
	if motion.is_empty() or started_at_us <= 0 or elapsed_us <= 0 or elapsed_us > 60_000_000:
		return _fail("Invalid authoritative mob action interval.")
	var rate := float(source_us) / float(elapsed_us)
	if not is_finite(rate) or rate < 0.01 or rate > 2.0:
		return _fail("Mob playback rate is outside the supported range.")
	return _play_motion(motion, mode_id, sequence, started_at_us, server_time_us, force, rate)


func _play_motion(
	motion: Dictionary,
	mode_id: String,
	sequence: int,
	started_at_us: int,
	server_time_us: int,
	force: bool,
	playback_rate: float
) -> bool:
	var resolved_mode := str(motion.get("mode_id", mode_id))
	var same := (
		str(current_motion.get("action_id", "")) == str(motion.get("action_id", ""))
		and current_mode == resolved_mode
		and current_sequence == sequence
	)
	if same and not force:
		return true
	var clip_name := str(motion.get("godot_name", ""))
	if animation_player == null or not _clips.has(clip_name):
		return _fail("Actor %s model is missing declared clip %s." % [actor_id, clip_name])
	_frozen_pose = false
	if not same:
		_consumed_launches.clear()
		_consumed_effects.clear()
	current_motion = (
		motion_effect_catalog.with_effects(motion) if motion_effect_catalog != null else motion
	)
	current_mode = resolved_mode
	current_sequence = sequence
	animation_player.speed_scale = playback_rate
	animation_player.play(_clips[clip_name], 0.12)
	var duration_seconds := float(int(motion.get("duration_us", 0))) / 1_000_000.0
	var offset_seconds := 0.0
	if started_at_us > 0 and server_time_us >= started_at_us:
		offset_seconds = (
			float(server_time_us - started_at_us) / 1_000_000.0 * animation_player.speed_scale
		)
	if duration_seconds > 0.0 and offset_seconds > 0.0:
		if bool(motion.get("loop", false)):
			offset_seconds = fmod(offset_seconds, duration_seconds)
		else:
			offset_seconds = minf(offset_seconds, maxf(0.0, duration_seconds - 0.001))
		animation_player.seek(offset_seconds, true)
	# A late subscription/resync must not replay launches from before its pose.
	for launch: Dictionary in current_motion.get("projectile_launches", []):
		if int(launch.start_us) < int(round(offset_seconds * 1_000_000)):
			_consumed_launches[str(launch.source_event)] = true
	for effect: Dictionary in current_motion.get("effects", []):
		if int(effect.start_us) < int(round(offset_seconds * 1_000_000)):
			_consumed_effects[str(effect.source_event)] = true
	return true


func _process(_delta: float) -> void:
	if animation_player == null or _frozen_pose or not animation_player.is_playing():
		return
	var source_time_us := int(round(animation_player.current_animation_position * 1_000_000))
	_emit_projectiles(source_time_us)
	_emit_motion_effects(source_time_us)


func _emit_projectiles(source_time_us: int) -> void:
	for launch: Dictionary in current_motion.get("projectile_launches", []):
		var identity := str(launch.source_event)
		if _consumed_launches.has(identity) or int(launch.start_us) > source_time_us:
			continue
		_consumed_launches[identity] = true
		var origin := projectile_launch_origin(launch)
		if origin.has("position"):
			projectile_launched.emit(launch.duplicate(true), origin.position)


func _emit_motion_effects(source_time_us: int) -> void:
	for effect: Dictionary in current_motion.get("effects", []):
		var identity := str(effect.source_event)
		if _consumed_effects.has(identity) or int(effect.start_us) > source_time_us:
			continue
		_consumed_effects[identity] = true
		if bool(effect.get("enabled", true)):
			motion_effect_requested.emit(effect.duplicate(true))


func _on_animation_finished(clip: StringName) -> void:
	if current_motion.is_empty() or _frozen_pose:
		return
	if clip == _clips.get(str(current_motion.get("godot_name", "")), ""):
		# A long frame may finish playback before this node polls the clock.
		_emit_projectiles(int(current_motion.duration_us))
		_emit_motion_effects(int(current_motion.duration_us))


func projectile_launch_origin(launch: Dictionary) -> Dictionary:
	var offset: Array = launch.source_position_cm
	var point := (
		global_position + Vector3(float(offset[0]), float(offset[2]), -float(offset[1])) * 0.01
	)
	if launch.attached:
		var skeleton := _find_skeleton(model)
		var index := skeleton.find_bone(str(launch.bone)) if skeleton else -1
		if index < 0:
			return {"error": "Projectile attachment bone is missing"}
		# Original ProcessMotionEventFly adds the model-space bone translation,
		# without the actor world heading. Undo only the importer's baked yaw.
		var local_pose := (
			global_transform.affine_inverse()
			* skeleton.global_transform
			* skeleton.get_bone_global_pose(index)
		)
		var undo_yaw := Basis(
			Vector3.UP, -deg_to_rad(float(_definition.get("source_to_actor_yaw_degrees", 0)))
		)
		point += undo_yaw * local_pose.origin
	return {"position": point}


func motion_effect_transform(effect: Dictionary, source_to_actor_yaw_degrees: float) -> Dictionary:
	var offset: Array = effect.get("position_m", [])
	if not is_finite(source_to_actor_yaw_degrees) or offset.size() != 3:
		return {"error": "Effect needs finite source orientation and three offset components"}
	for value: Variant in offset:
		if not (value is int or value is float) or not is_finite(float(value)):
			return {"error": "Effect offset must be finite"}
	var attachment := str(effect.get("attachment", ""))
	if attachment not in ["follow_root", "capture_root", "follow_bone", "capture_bone"]:
		return {"error": "Unknown effect attachment mode"}
	var source_basis := global_basis * Basis(Vector3.UP, deg_to_rad(source_to_actor_yaw_degrees))
	var transform := Transform3D(source_basis, global_position)
	if attachment.ends_with("bone"):
		var skeleton := _find_skeleton(model)
		var index := skeleton.find_bone(str(effect.get("bone", ""))) if skeleton else -1
		if index < 0:
			return {"error": "Resolved effect attachment bone is missing"}
		transform = skeleton.global_transform * skeleton.get_bone_global_pose(index)
		# glTF joint axes retain Blender bone coordinates; effect vertices already
		# use the source-to-Godot axis mapping, so undo it on the right.
		transform.basis *= Basis(Vector3.RIGHT, PI / 2)
	# Original bone * translation * actor row-vector order: offset belongs to
	# actor space, not the animated bone's local axes.
	transform.origin += source_basis * Vector3(float(offset[0]), float(offset[1]), float(offset[2]))
	if not transform.is_finite():
		return {"error": "Nonfinite effect attachment transform"}
	return {"transform": transform}


func freeze_at_end() -> void:
	if animation_player == null or current_motion.is_empty():
		return
	var duration := float(int(current_motion.get("duration_us", 0))) / 1_000_000.0
	animation_player.seek(maxf(0.0, duration - 0.001), true)
	animation_player.pause()
	_frozen_pose = true


func reset_action() -> void:
	current_motion = {}
	current_mode = ""
	current_sequence = -1
	_consumed_launches.clear()
	_consumed_effects.clear()
	_frozen_pose = false
	if animation_player:
		animation_player.stop()


func set_weapon(vnum: int) -> bool:
	if vnum == weapon_vnum and (vnum == 0 or is_instance_valid(_equipment)):
		return true
	if is_instance_valid(_equipment):
		_equipment.queue_free()
		_equipment = null
	weapon_vnum = vnum
	if vnum == 0:
		return true
	var definition: Dictionary = catalog.item_for_vnum(vnum)
	if definition.is_empty():
		return _fail("Actor profile has no visible equipment for vnum %d." % vnum)
	return _attach_weapon(vnum, definition)


func _attach_weapon(vnum: int, definition: Dictionary) -> bool:
	var attachment_key := str(definition.get("actor_attachment", ""))
	var bone_name := str(_definition.get("attachment_bones", {}).get(attachment_key, ""))
	var skeleton := _find_skeleton(model)
	if skeleton == null or skeleton.find_bone(bone_name) < 0:
		return _fail("Actor %s model is missing attachment bone %s." % [actor_id, bone_name])
	var model_reference: Dictionary = definition.get("model", {})
	var packed := load(str(model_reference.get("path", ""))) as PackedScene
	if packed == null:
		return _fail("Could not load equipment model for vnum %d." % vnum)
	var attachment := BoneAttachment3D.new()
	attachment.name = "Equipment_%d" % vnum
	attachment.bone_name = bone_name
	skeleton.add_child(attachment)
	var equipment_model := packed.instantiate() as Node3D
	if equipment_model == null:
		attachment.queue_free()
		return _fail("Equipment model for vnum %d has no Node3D root." % vnum)
	attachment.add_child(equipment_model)
	var transform: Dictionary = definition.get("attachment_transform", {})
	equipment_model.position = _vector3(transform.get("translation_m", []))
	equipment_model.rotation_degrees = _vector3(transform.get("rotation_degrees", []))
	equipment_model.scale = _vector3(transform.get("scale", [1.0, 1.0, 1.0]))
	_equipment = attachment
	return true


func snapshot() -> Dictionary:
	var model_reference: Dictionary = _definition.get("model", {})
	return {
		"actor_id": actor_id,
		"model_path": str(model_reference.get("path", "")),
		"mode": current_mode,
		"action_id": str(current_motion.get("action_id", "")),
		"clip": str(current_motion.get("godot_name", "")),
		"animation": str(animation_player.current_animation) if animation_player else "",
		"animation_position":
		(
			animation_player.current_animation_position
			if animation_player and not animation_player.current_animation.is_empty()
			else 0.0
		),
		"animation_speed": animation_player.speed_scale if animation_player else 1.0,
		"sequence": current_sequence,
		"weapon_vnum": weapon_vnum,
		"equipment_attached": is_instance_valid(_equipment),
		"frozen_pose": _frozen_pose,
		"error": error_message,
	}


func _build() -> bool:
	var model_reference: Dictionary = _definition.get("model", {})
	var path := str(model_reference.get("path", ""))
	var packed := load(path) as PackedScene
	if packed == null:
		return _fail("Required actor model could not load: " + path)
	model = packed.instantiate() as Node3D
	if model == null:
		return _fail("Required actor model has no Node3D root: " + path)
	model.name = "Model"
	add_child(model)
	animation_player = _find_animation_player(model)
	if animation_player == null:
		return _fail("Required actor model has no AnimationPlayer: " + path)
	animation_player.animation_finished.connect(_on_animation_finished)
	for clip: StringName in animation_player.get_animation_list():
		_clips[str(clip)] = clip
	for mode: Dictionary in _definition.get("modes", []):
		for motion: Dictionary in mode.get("motions", []):
			var clip_name := str(motion.get("godot_name", ""))
			if not _clips.has(clip_name):
				return _fail("Required actor model is missing declared clip: " + clip_name)
			var animation := animation_player.get_animation(_clips[clip_name])
			animation.loop_mode = (
				Animation.LOOP_LINEAR if bool(motion.get("loop", false)) else Animation.LOOP_NONE
			)
	return true


func _find_animation_player(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node
	for child: Node in node.get_children():
		var found := _find_animation_player(child)
		if found:
			return found
	return null


func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child: Node in node.get_children():
		var found := _find_skeleton(child)
		if found:
			return found
	return null


func _vector3(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _fail(message: String) -> bool:
	error_message = message
	push_error(message)
	return false
