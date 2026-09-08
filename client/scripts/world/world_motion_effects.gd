extends Node3D
## Shared presentation-only effect instances. The world supplies the render clock.

const Mixed = preload("res://scripts/actors/mixed_effect.gd")
const Effect = preload("res://scripts/actors/particle_effect.gd")
var error_message := ""
var _recipes: Dictionary = {}
var _textures: Dictionary = {}
var _mixed: Dictionary = {}
var _scenes: Dictionary = {}
var _bindings: Dictionary = {}
var _instances: Array[Dictionary] = []
var _next_seed := 0


func configure(
	recipes: Array, textures: Dictionary, mixed: Array = [], scenes: Dictionary = {}
) -> bool:
	if not _instances.is_empty() or not _bindings.is_empty():
		return false
	var indexed: Dictionary = {}
	for recipe: Dictionary in recipes:
		var path := str(recipe.get("effect_path", ""))
		if path.is_empty() or indexed.has(path):
			return false
		indexed[path] = recipe.duplicate(true)
	var mixed_index: Dictionary = {}
	for recipe: Dictionary in mixed:
		var path := str(recipe.get("source_effect", ""))
		if path.is_empty() or indexed.has(path) or mixed_index.has(path):
			return false
		mixed_index[path] = recipe.duplicate(true)
	_mixed = mixed_index
	_scenes = scenes.duplicate()
	_recipes = indexed
	_textures = textures.duplicate()
	return true


func bind_actor(actor: Node3D, source_yaw_degrees: float) -> bool:
	if (
		not is_instance_valid(actor)
		or not actor.is_inside_tree()
		or not is_finite(source_yaw_degrees)
	):
		return false
	if (
		not actor.has_signal("motion_effect_requested")
		or not actor.has_method("motion_effect_transform")
	):
		return false
	var identity := actor.get_instance_id()
	if _bindings.has(identity):
		return false
	var callback := _spawn.bind(weakref(actor), source_yaw_degrees)
	actor.motion_effect_requested.connect(callback)
	actor.tree_exiting.connect(_actor_exiting.bind(identity), CONNECT_ONE_SHOT)
	_bindings[identity] = {"actor": weakref(actor), "callback": callback}
	return true


func _actor_exiting(identity: int) -> void:
	var binding: Dictionary = _bindings.get(identity, {})
	var actor: Node3D = binding.actor.get_ref() if not binding.is_empty() else null
	if actor != null and actor.motion_effect_requested.is_connected(binding.callback):
		actor.motion_effect_requested.disconnect(binding.callback)
	_bindings.erase(identity)
	for index: int in range(_instances.size() - 1, -1, -1):
		if _instances[index].owner_id == identity and _instances[index].following:
			_remove(index)


func _spawn(event: Dictionary, reference: WeakRef, yaw: float) -> void:
	var actor: Node3D = reference.get_ref()
	if actor == null or not bool(event.get("enabled", true)):
		return
	var path := str(event.get("effect_path", ""))
	if not _recipes.has(path) and not _mixed.has(path):
		error_message = "Motion effect resource is not installed: " + path
		return
	var placement: Dictionary = actor.motion_effect_transform(event, yaw)
	if placement.has("error"):
		error_message = placement.error
		return
	var effect: Node3D = Mixed.new() if _mixed.has(path) else Effect.new()
	add_child(effect)
	effect.top_level = true
	effect.global_transform = placement.transform
	_next_seed += 1
	var configured: bool = (
		effect.configure(_mixed[path], _scenes, _textures, _next_seed)
		if _mixed.has(path)
		else effect.configure(_recipes[path], _textures, _next_seed)
	)
	if not configured:
		effect.queue_free()
		error_message = "Motion effect recipe cannot render: " + path
		return
	(
		_instances
		. append(
			{
				"node": effect,
				"actor": reference,
				"owner_id": actor.get_instance_id(),
				"event": event.duplicate(true),
				"yaw": yaw,
				"following": str(event.attachment).begins_with("follow_"),
			}
		)
	)


func advance(delta: float, camera: Camera3D) -> bool:
	if not is_finite(delta) or delta <= 0 or delta > 1 or not is_instance_valid(camera):
		return false
	for index: int in range(_instances.size() - 1, -1, -1):
		var instance: Dictionary = _instances[index]
		if instance.following:
			var actor: Node3D = instance.actor.get_ref()
			if actor == null or not actor.is_inside_tree():
				_remove(index)
				continue
			var placement: Dictionary = actor.motion_effect_transform(instance.event, instance.yaw)
			if placement.has("error"):
				error_message = placement.error
				_remove(index)
				continue
			instance.node.global_transform = placement.transform
		var state: Dictionary = instance.node.advance(delta, camera)
		if state.has("error"):
			error_message = state.error
			_remove(index)
		elif state.finished:
			_remove(index)
	return error_message.is_empty()


func _remove(index: int) -> void:
	var node: Node3D = _instances[index].node
	remove_child(node)
	node.queue_free()
	_instances.remove_at(index)
