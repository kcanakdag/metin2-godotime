class_name ActorPresentation
extends Node3D
## Shared model, manifest motion, and bone-equipment presentation.

var catalog: RefCounted
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
	current_motion = motion
	current_mode = resolved_mode
	current_sequence = sequence
	animation_player.speed_scale = float(attack_speed_percent) / 100.0
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
	return true


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
		animation_player.current_animation_position if animation_player else 0.0,
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
