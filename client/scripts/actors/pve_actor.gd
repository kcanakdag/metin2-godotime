class_name PveActor
extends Node3D
## Subscribed monster presentation plus the existing loot presentation modes.

const ActorCatalogScript := preload("res://scripts/content/actor_catalog.gd")
const ActorPresentationScript := preload("res://scripts/actors/actor_presentation.gd")

var row: Dictionary = {}
var loot_mode := false
var item_mode := false

var _catalog: RefCounted
var _presentation: Node3D
var _target := Vector3.ZERO
var _visual: Node3D
var _label: Label3D
var _time := 0.0
var _last_health := -1
var _damage_sequence := 0
var _damage_until_ticks_us := 0
var _life_sequence := -1
var _last_server_time_us := 0


func configure(value: RefCounted) -> void:
	_catalog = value


func _ready() -> void:
	_visual = Node3D.new()
	_visual.name = "LootVisual" if loot_mode else "ActorVisual"
	add_child(_visual)
	if loot_mode:
		_build_loot()
	_label = Label3D.new()
	_label.position.y = 0.85 if loot_mode else 1.45
	_label.font_size = 36
	_label.pixel_size = 0.006
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(_label)


func apply_state(value: Dictionary, server_time_us := 0) -> void:
	var first := row.is_empty()
	row = value.duplicate()
	_target = Vector3(float(row.get("x", 0.0)), float(row.get("y", 0.0)), float(row.get("z", 0.0)))
	if first or position.distance_to(_target) > 8.0:
		position = _target
	if loot_mode:
		_label.text = "Red Potion (S)" if item_mode else "%d Yang" % int(row.get("gold", 0))
		_label.modulate = Color("ffd26e")
		return
	if not _ensure_presentation():
		return
	_label.text = (
		"%s  %d / %d"
		% [
			str(row.get("name", "Wild Dog")),
			int(row.get("health", 0)),
			int(row.get("max_health", 0)),
		]
	)
	_label.modulate = Color("ed9a78")
	var activity := int(row.get("activity", 0))
	var health := int(row.get("health", 0))
	var sequence := int(row.get("attack_sequence", 0))
	var life_sequence := int(row.get("life_sequence", 0))
	var started_at_us := int(row.get("action_started_at_us", 0))
	var ends_at_us := int(row.get("action_ends_at_us", 0))
	var mode := "general"
	var clock_became_ready := _last_server_time_us <= 0 and server_time_us > 0
	_last_server_time_us = server_time_us
	if _life_sequence >= 0 and life_sequence != _life_sequence:
		_damage_until_ticks_us = 0
		_last_health = health
		_presentation.reset_action()
	_life_sequence = life_sequence
	if activity == 3:
		_presentation.play_action(
			mode,
			"",
			"front_death",
			life_sequence,
			started_at_us,
			server_time_us,
			clock_became_ready
		)
		var death_motion: Dictionary = _catalog.motion(
			_presentation.actor_id, mode, "", "front_death"
		)
		var death_duration := int(death_motion.get("duration_us", 0))
		if death_duration > 0 and server_time_us - started_at_us >= death_duration:
			_presentation.freeze_at_end()
	elif activity == 2 and ends_at_us > server_time_us:
		_presentation.play_action(
			mode,
			str(row.get("attack_action_id", "")),
			"",
			sequence,
			started_at_us,
			server_time_us,
			clock_became_ready
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
	if loot_mode:
		return {"loot": true, "item": item_mode}
	var result: Dictionary = _presentation.snapshot() if is_instance_valid(_presentation) else {}
	result["row_id"] = int(row.get("id", 0))
	result["definition_vnum"] = int(row.get("definition_vnum", 0))
	result["attack_sequence"] = int(row.get("attack_sequence", 0))
	return result


func _process(delta: float) -> void:
	if row.is_empty():
		return
	_time += delta
	position = position.lerp(_target, 1.0 - exp(-delta * 12.0))
	if loot_mode:
		if not item_mode:
			_visual.rotation.y += delta
		_visual.position.y = sin(_time * 3.0) * 0.1
		return
	rotation.y = lerp_angle(rotation.y, float(row.get("heading", 0.0)), 1.0 - exp(-delta * 12.0))
	if _damage_until_ticks_us > 0 and Time.get_ticks_usec() >= _damage_until_ticks_us:
		_damage_until_ticks_us = 0
		var activity := int(row.get("activity", 0))
		if activity in [0, 1] and is_instance_valid(_presentation):
			_presentation.play_action("general", "", "run" if activity == 1 else "wait", 0)


func _ensure_presentation() -> bool:
	if is_instance_valid(_presentation):
		return true
	if _catalog == null:
		push_error("Monster actor has no content catalog.")
		return false
	var actor_id := str(row.get("actor_id", ""))
	if actor_id != ActorCatalogScript.WILD_DOG_ID or int(row.get("definition_vnum", 0)) != 101:
		push_error("Subscribed monster has no matching P1 actor definition.")
		return false
	_presentation = ActorPresentationScript.new()
	_presentation.name = "Presentation"
	if not _presentation.configure(_catalog, actor_id):
		return false
	_visual.add_child(_presentation)
	return true


func _build_loot() -> void:
	if item_mode:
		var icon := Sprite3D.new()
		var icon_path := "res://assets/imported/ui/icon/item/27001.png"
		if ResourceLoader.exists(icon_path):
			icon.texture = load(icon_path)
		icon.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		icon.pixel_size = 0.018
		icon.position.y = 0.35
		_visual.add_child(icon)
	else:
		_part(Vector3(0, 0.35, 0), Vector3(0.35, 0.35, 0.35), Color("ffd26e"))


func _part(point: Vector3, size: Vector3, color: Color) -> void:
	var node := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	node.mesh = mesh
	node.position = point
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	node.material_override = material
	_visual.add_child(node)
