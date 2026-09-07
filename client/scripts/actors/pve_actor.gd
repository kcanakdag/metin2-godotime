class_name PveActor
extends Node3D
## Subscribed monster presentation plus the existing loot presentation modes.

const ActorCatalogScript := preload("res://scripts/content/actor_catalog.gd")
const ActorPresentationScript := preload("res://scripts/actors/actor_presentation.gd")
const TargetEffectScript := preload("res://scripts/actors/target_effect.gd")
const TargetEffectCatalogScript := preload("res://scripts/content/target_effect_catalog.gd")
const TARGET_PICK_LAYER := 2

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
var _pick_body: StaticBody3D
var _pick_shape: CollisionShape3D
var _stream_visible := true
var _hovered := false
var _accepted_target := false
var _targeted := false
var _effect_catalog: Variant
var _hover_effect: Node3D
var _target_effect: Node3D


func configure(value: RefCounted, target_effect_catalog: Variant = null) -> void:
	_catalog = value
	_effect_catalog = target_effect_catalog


func _ready() -> void:
	visibility_changed.connect(_refresh_pick_state)
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
	var previous_id := int(row.get("id", 0))
	var previous_life := int(row.get("life_sequence", -1))
	row = value.duplicate()
	if (
		not first
		and (
			int(row.get("id", 0)) != previous_id
			or int(row.get("life_sequence", -1)) != previous_life
		)
	):
		_hovered = false
		_accepted_target = false
		_targeted = false
		_reset_target_effects()
	_target = Vector3(float(row.get("x", 0.0)), float(row.get("y", 0.0)), float(row.get("z", 0.0)))
	if first or position.distance_to(_target) > 8.0:
		position = _target
	if loot_mode:
		_label.text = "Red Potion (S)" if item_mode else "%d Yang" % int(row.get("gold", 0))
		_label.modulate = Color("ffd26e")
		return
	if not _ensure_presentation():
		_refresh_pick_state()
		return
	_ensure_pick_proxy()
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
	_refresh_pick_state()


func set_stream_visible(value: bool) -> void:
	_stream_visible = value
	visible = value
	_refresh_pick_state()


func set_hovered(value: bool) -> void:
	var next := value and is_pickable()
	var activating := next and not _hovered
	_hovered = next
	_sync_target_effects()
	if activating and is_instance_valid(_hover_effect):
		_hover_effect.reset_clock()


func set_targeted(value: bool) -> void:
	var activating := value and not _accepted_target
	_accepted_target = value
	_targeted = value and is_pickable()
	_sync_target_effects()
	if activating and is_instance_valid(_target_effect):
		_target_effect.reset_clock()


func is_pickable() -> bool:
	return (
		not loot_mode
		and not item_mode
		and _stream_visible
		and is_visible_in_tree()
		and is_instance_valid(_pick_shape)
		and not _pick_shape.disabled
		and int(row.get("id", 0)) > 0
		and int(row.get("life_sequence", -1)) >= 0
		and int(row.get("health", 0)) > 0
		and int(row.get("max_health", 0)) > 0
		and int(row.get("activity", 0)) != 3
	)


func combat_target_intent() -> Dictionary:
	if not is_pickable():
		return {}
	return target_identity()


func target_identity() -> Dictionary:
	if loot_mode or item_mode:
		return {}
	if int(row.get("id", 0)) <= 0 or int(row.get("life_sequence", -1)) < 0:
		return {}
	return {
		"target_id": int(row.get("id", 0)),
		"target_life_sequence": int(row.get("life_sequence", -1)),
	}


func pick_projection(camera: Camera3D, viewport_rect: Rect2) -> Dictionary:
	var result := {
		"available": false,
		"screen": [],
		"target_id": int(row.get("id", 0)),
		"target_life_sequence": int(row.get("life_sequence", -1)),
	}
	if not is_pickable() or not is_instance_valid(camera) or not is_instance_valid(_pick_body):
		return result
	var world_point := _pick_body.global_position
	if camera.is_position_behind(world_point):
		return result
	var screen_point := camera.unproject_position(world_point)
	if not screen_point.is_finite() or not viewport_rect.has_point(screen_point):
		return result
	result.available = true
	result.screen = [screen_point.x, screen_point.y]
	return result


func presentation_snapshot() -> Dictionary:
	if loot_mode:
		return {"loot": true, "item": item_mode}
	var result: Dictionary = _presentation.snapshot() if is_instance_valid(_presentation) else {}
	result["row_id"] = int(row.get("id", 0))
	result["definition_vnum"] = int(row.get("definition_vnum", 0))
	result["attack_sequence"] = int(row.get("attack_sequence", 0))
	result["pickable"] = is_pickable()
	result["hovered"] = _hovered
	result["targeted"] = _targeted
	result["hover_effect"] = _effect_snapshot(_hover_effect)
	result["target_effect"] = _effect_snapshot(_target_effect)
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


func _ensure_pick_proxy() -> void:
	if is_instance_valid(_pick_body):
		return
	var bounds: Dictionary = _catalog.actor_bounds(str(row.get("actor_id", "")))
	if bounds.is_empty():
		push_error("Subscribed monster has invalid pinned pick bounds.")
		return
	var minimum: Vector3 = bounds.minimum
	var maximum: Vector3 = bounds.maximum
	var shape := BoxShape3D.new()
	shape.size = maximum - minimum
	_pick_body = StaticBody3D.new()
	_pick_body.name = "TargetPickBody"
	_pick_body.position = (minimum + maximum) * 0.5
	_pick_body.collision_layer = TARGET_PICK_LAYER
	_pick_body.collision_mask = 0
	_pick_body.set_meta("combat_target_actor", self)
	add_child(_pick_body)
	_pick_shape = CollisionShape3D.new()
	_pick_shape.name = "TargetPickShape"
	_pick_shape.shape = shape
	_pick_body.add_child(_pick_shape)


func _refresh_pick_state() -> void:
	var active := (
		not loot_mode
		and not item_mode
		and _stream_visible
		and is_visible_in_tree()
		and is_instance_valid(_presentation)
		and int(row.get("id", 0)) > 0
		and int(row.get("life_sequence", -1)) >= 0
		and int(row.get("health", 0)) > 0
		and int(row.get("max_health", 0)) > 0
		and int(row.get("activity", 0)) != 3
	)
	if is_instance_valid(_pick_body):
		_pick_body.set_meta("target_id", int(row.get("id", 0)))
		_pick_body.set_meta("target_life_sequence", int(row.get("life_sequence", -1)))
	if is_instance_valid(_pick_shape):
		_pick_shape.disabled = not active
	_targeted = _accepted_target and active
	if not active:
		_hovered = false
	_sync_target_effects()


func _sync_target_effects() -> void:
	if _effect_catalog == null or not bool(_effect_catalog.loaded):
		return
	if _hovered and not is_instance_valid(_hover_effect):
		_hover_effect = _attach_target_effect(
			"HoverTargetEffect", TargetEffectCatalogScript.HOVER_ID
		)
	if _targeted and not is_instance_valid(_target_effect):
		_target_effect = _attach_target_effect(
			"AcceptedTargetEffect", TargetEffectCatalogScript.TARGET_ID
		)
	if is_instance_valid(_hover_effect):
		_hover_effect.visible = _hovered and is_pickable()
	if is_instance_valid(_target_effect):
		_target_effect.visible = _targeted and is_pickable()


func _attach_target_effect(node_name: String, effect_id: String) -> Node3D:
	var effect := TargetEffectScript.new()
	effect.name = node_name
	if not effect.configure(_effect_catalog, effect_id):
		var message := str(effect.error_message)
		effect.free()
		push_error("Could not attach target effect: %s" % message)
		return null
	add_child(effect)
	return effect


func _reset_target_effects() -> void:
	for effect: Node3D in [_hover_effect, _target_effect]:
		if is_instance_valid(effect):
			remove_child(effect)
			effect.queue_free()
	_hover_effect = null
	_target_effect = null


func _effect_snapshot(effect: Node3D) -> Dictionary:
	if not is_instance_valid(effect):
		return {}
	var result: Dictionary = effect.snapshot()
	result["visible"] = effect.visible and is_visible_in_tree()
	return result


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
