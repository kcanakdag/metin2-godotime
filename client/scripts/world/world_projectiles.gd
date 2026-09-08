extends Node3D
## Presentation only. Resolve the exact subscribed target life; never grant damage.

const Projectile = preload("res://scripts/actors/projectile_effect.gd")
var _flights: Dictionary = {}
var _effects: Dictionary = {}
var _textures: Dictionary = {}
var _meshes: Dictionary = {}
var _resolve: Callable
var _active: Array[Dictionary] = []
var _seen: Dictionary = {}


func configure(
	flights: Dictionary,
	effects: Dictionary,
	textures: Dictionary,
	meshes: Dictionary,
	resolve_target: Callable
) -> bool:
	if not _active.is_empty() or not resolve_target.is_valid():
		return false
	_flights = flights
	_effects = effects
	_textures = textures
	_meshes = meshes
	_resolve = resolve_target
	_seen.clear()
	return true


func launch(row: Dictionary, event: Dictionary, origin: Vector3, initial_delta: float) -> bool:
	if (
		not is_inside_tree()
		or not _resolve.is_valid()
		or not origin.is_finite()
		or not _flights.has(str(event.fly_definition))
	):
		return false
	var target_id := str(row.get("attack_target", ""))
	var life := int(row.get("attack_target_life_sequence", -1))
	var target := _target(target_id, life)
	if target.is_empty():
		return false
	var actor_id := int(row.get("id", 0))
	if actor_id <= 0 or int(row.get("activity", -1)) != 2:
		return false
	var action := (
		"%s/%s/%s/%s"
		% [row.life_sequence, row.attack_sequence, row.attack_action_id, row.action_started_at_us]
	)
	var previous: Dictionary = _seen.get(actor_id, {})
	var events: Dictionary = previous.get("events", {}) if previous.get("action") == action else {}
	var event_id := str(event.source_event)
	if events.has(event_id):
		return false
	var effect := Projectile.new()
	add_child(effect)
	if not effect.configure(
		_flights[event.fly_definition],
		_effects,
		_textures,
		origin,
		target.position,
		int(row.attack_sequence),
		initial_delta,
		_meshes
	):
		effect.queue_free()
		return false
	events[event_id] = true
	_seen[actor_id] = {"action": action, "events": events}
	_active.append(
		{
			"effect": effect,
			"target_id": target_id,
			"life": life,
			"position": target.position,
			"object": true
		}
	)
	return true


func advance(delta: float, camera: Camera3D) -> bool:
	if not is_finite(delta) or delta <= 0 or delta > 1 or not is_instance_valid(camera):
		return false
	for index: int in range(_active.size() - 1, -1, -1):
		var entry: Dictionary = _active[index]
		if entry.object:
			var current := _target(entry.target_id, entry.life)
			if current.is_empty():
				# Original CFlyTarget converts destroyed objects to their last position.
				# This transition is permanent, even if the identity reappears.
				entry.object = false
			else:
				entry.position = current.position
		var state: Dictionary = entry.effect.advance(delta, entry.position, camera, entry.object)
		if state.has("error"):
			return false
		if state.done:
			entry.effect.queue_free()
			_active.remove_at(index)
	return true


func forget_actor(id: int) -> void:
	# Existing flights outlive their source actor; only its deduplication cache retires.
	_seen.erase(id)


func clear() -> void:
	for entry: Dictionary in _active:
		entry.effect.hide()
		entry.effect.queue_free()
	_active.clear()
	_seen.clear()


func snapshot() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for entry: Dictionary in _active:
		result.append(
			{
				"target_id": entry.target_id,
				"life": entry.life,
				"target_position": entry.position,
				"object_target": entry.object,
				"position": entry.effect.flight.position
			}
		)
	return result


func _target(identity: String, life: int) -> Dictionary:
	if identity.is_empty() or identity == "0".repeat(64) or life < 0:
		return {}
	var value: Variant = _resolve.call(identity)
	if not value is Dictionary or value.is_empty():
		return {}
	if str(value.get("identity", "")) != identity or int(value.get("life_sequence", -1)) != life:
		return {}
	var point: Variant = value.get("position")
	if not point is Vector3 or not point.is_finite():
		return {}
	return {"position": point}
