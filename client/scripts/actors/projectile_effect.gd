extends Node3D
## Selected particle and mesh flights and independent impact effects; no gameplay damage.

const Flight = preload("res://scripts/actors/projectile_flight.gd")
const Effect = preload("res://scripts/actors/particle_effect.gd")
const Motion = preload("res://scripts/actors/particle_motion.gd")
const MeshEffect = preload("res://scripts/actors/projectile_mesh_effect.gd")
const Trail = preload("res://scripts/actors/projectile_trail.gd")
var flight: RefCounted
var _definition: Dictionary = {}
var _effects: Dictionary = {}
var _textures: Dictionary = {}
var _mesh_effects: Dictionary = {}
var _attachments: Array[Dictionary] = []
var _impacts: Array[Node3D] = []
var _spin := Quaternion.IDENTITY
var _seed := 0


func configure(
	definition: Dictionary,
	effects: Dictionary,
	textures: Dictionary,
	start: Vector3,
	target: Vector3,
	random_seed: int,
	initial_delta: float,
	mesh_effects: Dictionary = {}
) -> bool:
	if (
		not is_inside_tree()
		or flight != null
		or not is_finite(initial_delta)
		or initial_delta < 0
		or initial_delta > 1
	):
		return false
	for attachment: Dictionary in definition.attachments:
		if (
			int(attachment.type) != 1
			or int(attachment.fly_type) not in [1, 2]
			or (not effects.has(attachment.effect) and not mesh_effects.has(attachment.effect))
			or (effects.has(attachment.effect) and mesh_effects.has(attachment.effect))
		):
			return false
	if definition.bomb_effect != null and not effects.has(definition.bomb_effect):
		return false
	var candidate := Flight.new()
	if not candidate.configure(definition.flight, start, target):
		return false
	_definition = definition.duplicate(true)
	_effects = effects
	_textures = textures
	_mesh_effects = mesh_effects
	_seed = random_seed
	flight = candidate
	_update_spin(initial_delta)
	for data: Dictionary in definition.attachments:
		if not _add_attachment(data):
			_discard_attachments()
			flight = null
			_spin = Quaternion.IDENTITY
			return false
	return true


func _add_attachment(data: Dictionary) -> bool:
	var effect: Node3D
	var configured := false
	if _mesh_effects.has(data.effect):
		var resource: Dictionary = _mesh_effects[data.effect]
		effect = MeshEffect.new()
		add_child(effect)
		configured = effect.configure(resource.definition, resource.scene, resource.texture)
	else:
		effect = Effect.new()
		add_child(effect)
		configured = effect.configure(_effects[data.effect], _textures, _seed + _attachments.size())
	if not configured:
		effect.queue_free()
		return false
	effect.global_transform = attachment_transform(data)
	var trail: MeshInstance3D = null
	if data.tail != null:
		trail = Trail.new()
		add_child(trail)
	_attachments.append({"data": data.duplicate(true), "effect": effect, "trail": trail})
	return trail == null or trail.configure(data.tail)


func _discard_attachments() -> void:
	for attachment: Dictionary in _attachments:
		attachment.effect.hide()
		attachment.effect.queue_free()
		if attachment.trail != null:
			attachment.trail.hide()
			attachment.trail.queue_free()
	_attachments.clear()


func advance(delta: float, target: Vector3, camera: Camera3D) -> Dictionary:
	if flight == null or camera == null:
		return {"error": "Projectile effect is not configured"}
	var result: Dictionary = flight.advance(delta, target)
	if result.has("error"):
		return result
	if result.event != "inactive":
		_update_spin(delta)
		for attachment: Dictionary in _attachments:
			attachment.effect.global_transform = attachment_transform(attachment.data)
			attachment.effect.advance(delta, camera)
			if attachment.trail != null:
				attachment.trail.advance(flight.elapsed, attachment.effect.global_position, camera)
		if result.event == "target_hit" and _definition.bomb_effect != null:
			var impact := Effect.new()
			add_child(impact)
			impact.global_transform = Transform3D(Basis.IDENTITY, flight.position)
			if not impact.configure(_effects[_definition.bomb_effect], _textures, _seed + 1000):
				impact.queue_free()
				return {"error": "Failed to configure impact effect"}
			_impacts.append(impact)
		if not flight.alive:
			_discard_attachments()
	for index: int in range(_impacts.size() - 1, -1, -1):
		var impact: Node3D = _impacts[index]
		var state: Dictionary = impact.advance(delta, camera)
		if state.finished:
			impact.queue_free()
			_impacts.remove_at(index)
	return {
		"event": result.event,
		"done": not flight.alive and _impacts.is_empty(),
		"attachments": _attachments.size(),
		"impacts": _impacts.size()
	}


func attachment_transform(data: Dictionary) -> Transform3D:
	var rotation: Quaternion = flight.orientation
	var point: Vector3 = flight.position
	if int(data.fly_type) == 2:
		rotation = (rotation * _spin).normalized()
		var roll := deg_to_rad(float(data.roll_degrees))
		point += (
			rotation
			* Motion.source_vector(
				[-sin(roll) * data.distance_cm, 0, -cos(roll) * data.distance_cm]
			)
		)
	return Transform3D(Basis(rotation), point)


func _update_spin(delta: float) -> void:
	var velocity: Array = _definition.flight.AngularVelocity
	var step := (
		Quaternion(Vector3.FORWARD, deg_to_rad(float(velocity[1])) * delta)
		* Quaternion(Vector3.RIGHT, deg_to_rad(float(velocity[0])) * delta)
		* Quaternion(Vector3.UP, deg_to_rad(float(velocity[2])) * delta)
	)
	_spin = (step * _spin).normalized()
