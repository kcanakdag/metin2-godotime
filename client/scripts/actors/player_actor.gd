class_name PlayerActor
extends Node3D
## Render one subscribed character. This node never owns gameplay coordinates or hit timing.

const ActorPresentationScript := preload("res://scripts/actors/actor_presentation.gd")

var identity := ""
var server_position := Vector3.ZERO
var server_heading := 0.0
var row: Dictionary = {}
var appearance: Dictionary = {}
var is_local := false

var _catalog: RefCounted
var _presentation: Node3D
var _name_label: Label3D
var _initialized := false
var _last_health := -1
var _damage_sequence := 0
var _damage_until_ticks_us := 0
var _life_sequence := -1
var _last_server_time_us := 0


func configure(value: RefCounted) -> void:
	_catalog = value


func _ready() -> void:
	_name_label = Label3D.new()
	_name_label.name = "Nameplate"
	_name_label.position.y = 2.15
	_name_label.font_size = 24
	_name_label.pixel_size = 0.007
	_name_label.outline_size = 4
	_name_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(_name_label)


func apply_state(
	state_row: Dictionary, local: bool, appearance_row: Dictionary, server_time_us: int
) -> void:
	row = state_row.duplicate()
	identity = str(row.get("identity", ""))
	is_local = local
	server_position = Vector3(
		float(row.get("x", 0.0)), float(row.get("y", 0.0)), float(row.get("z", 0.0))
	)
	server_heading = float(row.get("heading", 0.0))
	if not _initialized or position.distance_to(server_position) > 8.0:
		position = server_position
		rotation.y = server_heading
		_initialized = true
	_name_label.text = str(row.get("name", ""))
	_name_label.modulate = Color("f0d087") if local else Color("dce8d9")
	if appearance_row.is_empty():
		if is_instance_valid(_presentation):
			_presentation.visible = false
		return
	if not _apply_appearance(appearance_row):
		return
	_presentation.visible = true
	var weapon_vnum := int(appearance.get("weapon_vnum", 0))
	var mode: String = _catalog.mode_for_weapon(_presentation.actor_id, weapon_vnum)
	if mode.is_empty() or not _presentation.set_weapon(weapon_vnum):
		return
	var activity := int(row.get("activity", 0))
	var health := int(row.get("health", 0))
	var attack_sequence := int(row.get("attack_sequence", 0))
	var life_sequence := int(row.get("life_sequence", 0))
	var started_at_us := int(row.get("action_started_at_us", 0))
	var ends_at_us := int(row.get("action_ends_at_us", 0))
	var clock_became_ready := _last_server_time_us <= 0 and server_time_us > 0
	_last_server_time_us = server_time_us
	if _life_sequence >= 0 and life_sequence != _life_sequence:
		_damage_until_ticks_us = 0
		_last_health = health
		_presentation.reset_action()
	_life_sequence = life_sequence
	if activity == 3:
		_presentation.play_action(
			mode, "", "death", life_sequence, started_at_us, server_time_us, clock_became_ready
		)
		if started_at_us > 0:
			var death_motion: Dictionary = _catalog.motion(
				_presentation.actor_id, mode, "", "death"
			)
			var death_duration := int(death_motion.get("duration_us", 0))
			if death_duration > 0 and server_time_us - started_at_us >= death_duration:
				_presentation.freeze_at_end()
	elif activity == 2 and ends_at_us > server_time_us:
		_presentation.play_action(
			mode,
			str(row.get("attack_action_id", "")),
			"",
			attack_sequence,
			started_at_us,
			server_time_us,
			clock_became_ready,
			int(row.get("attack_speed_percent", 100))
		)
	elif Time.get_ticks_usec() < _damage_until_ticks_us:
		pass
	elif _last_health >= 0 and health < _last_health:
		_damage_sequence += 1
		var damage: Dictionary = _catalog.select_motion(
			_presentation.actor_id, mode, "front_damage", _damage_sequence
		)
		if _presentation.play_action(
			mode, str(damage.get("action_id", "")), "", _damage_sequence, 0, 0, true
		):
			_damage_until_ticks_us = Time.get_ticks_usec() + int(damage.get("duration_us", 0))
	else:
		_presentation.play_action(mode, "", "run" if activity == 1 else "wait", 0)
	_last_health = health


func presentation_snapshot() -> Dictionary:
	var result: Dictionary = _presentation.snapshot() if is_instance_valid(_presentation) else {}
	var presentation_local: Vector3 = (
		_presentation.position if is_instance_valid(_presentation) else Vector3.ZERO
	)
	var model_local: Vector3 = (
		_presentation.model.position
		if is_instance_valid(_presentation) and is_instance_valid(_presentation.model)
		else Vector3.ZERO
	)
	result["identity"] = identity
	result["visible"] = is_instance_valid(_presentation) and _presentation.visible
	result["server_position"] = [server_position.x, server_position.y, server_position.z]
	result["presentation_local_position"] = [
		presentation_local.x, presentation_local.y, presentation_local.z
	]
	result["model_local_position"] = [model_local.x, model_local.y, model_local.z]
	result["attack_sequence"] = int(row.get("attack_sequence", 0))
	return result


func _process(delta: float) -> void:
	if not _initialized:
		return
	var weight := 1.0 - exp(-delta * (20.0 if is_local else 12.0))
	position = position.lerp(server_position, weight)
	rotation.y = lerp_angle(rotation.y, server_heading, weight)
	if _damage_until_ticks_us > 0 and Time.get_ticks_usec() >= _damage_until_ticks_us:
		_damage_until_ticks_us = 0
		var activity := int(row.get("activity", 0))
		if activity in [0, 1] and is_instance_valid(_presentation):
			var mode: String = _catalog.mode_for_weapon(
				_presentation.actor_id, int(appearance.get("weapon_vnum", 0))
			)
			_presentation.play_action(mode, "", "run" if activity == 1 else "wait", 0)


func _apply_appearance(value: Dictionary) -> bool:
	if str(value.get("character_id", "")) != identity:
		push_error("Player appearance does not match its subscribed character.")
		return false
	var next_actor_id: String = _catalog.player_actor_id(value)
	if next_actor_id.is_empty():
		push_error("No actor presentation supports this subscribed class and sex.")
		return false
	if not is_instance_valid(_presentation) or _presentation.actor_id != next_actor_id:
		if is_instance_valid(_presentation):
			_presentation.queue_free()
		_presentation = ActorPresentationScript.new()
		_presentation.name = "Visual"
		if not _presentation.configure(_catalog, next_actor_id):
			return false
		add_child(_presentation)
	appearance = value.duplicate()
	return true
