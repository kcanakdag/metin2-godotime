extends "res://scripts/world/world_motion_effects.gd"
## World-owned package and player presentation lifecycle; no gameplay authority.

const Catalog = preload("res://scripts/content/motion_effect_catalog.gd")
const PATH := "res://assets/imported/motion_effects/catalog.v1.json"
var package := Catalog.new()
var _presentations: Dictionary = {}


func prepare_catalog(actors: RefCounted) -> bool:
	return prepare(actors.characters.content_hash, actors.skills.content_hash)


func prepare(character_hash: String, skill_hash: String, path := PATH) -> bool:
	clear()
	if not package.load_required(path, character_hash, skill_hash):
		error_message = package.error_message
		return false
	if not configure(
		package.document.effects.values(),
		package.textures,
		package.document.mixed_effects.values(),
		package.scenes
	):
		error_message = "Motion effect resources could not configure"
		return false
	for identity: int in _presentations.keys():
		var presentation: Node3D = _presentations[identity].get_ref()
		if presentation == null or not presentation.is_inside_tree():
			_presentations.erase(identity)
		else:
			bind_presentation(presentation)
	return error_message.is_empty()


func watch_player(player: Node) -> void:
	if player.has_signal("presentation_created"):
		player.presentation_created.connect(bind_presentation)


func bind_presentation(presentation: Node3D) -> void:
	_presentations[presentation.get_instance_id()] = weakref(presentation)
	if package.document.is_empty():
		error_message = "Player motion effects have not been prepared"
		return
	presentation.motion_effect_catalog = package
	if not bind_actor(presentation, float(package.document.source_to_actor_yaw_degrees)):
		error_message = "Player motion effect binding failed"


func snapshot() -> Dictionary:
	return {
		"package_hash": str(package.document.get("content_hash", "")),
		"spawned": _next_seed,
		"active": _instances.size(),
		"bindings": _bindings.size(),
		"error": error_message,
	}
