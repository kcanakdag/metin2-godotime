@tool
extends Node3D

const ActorCatalogScript := preload("res://scripts/content/actor_catalog.gd")
const ActorPresentationScript := preload("res://scripts/actors/actor_presentation.gd")

var catalog := ActorCatalogScript.new()
var presentation: Node3D
var error_message := ""
var selected_weapon_vnum := 0


func _ready() -> void:
	if get_child_count() > 0:
		presentation = get_child(0) as Node3D
		return
	if not catalog.load_required():
		error_message = catalog.error_message
		return
	presentation = ActorPresentationScript.new()
	presentation.name = "Warrior"
	if not presentation.configure(catalog, ActorCatalogScript.WARRIOR_ID):
		error_message = presentation.error_message
		return
	add_child(presentation)
	set_weapon(0)
	var motions := available_motions()
	if not motions.is_empty():
		play_motion(motions[0])


func available_motions() -> Array[Dictionary]:
	if not is_instance_valid(presentation):
		return []
	var actor: Dictionary = catalog.actor(ActorCatalogScript.WARRIOR_ID)
	var result: Array[Dictionary] = []
	for mode: Dictionary in actor.get("modes", []):
		var required: Array = mode.get("required_item_vnums", [])
		if (
			(selected_weapon_vnum == 0 and not required.is_empty())
			or (selected_weapon_vnum != 0 and selected_weapon_vnum not in required)
		):
			continue
		for motion: Dictionary in mode.get("motions", []):
			(
				result
				. append(
					{
						"mode_id": str(mode.get("id", "")),
						"action_id": str(motion.get("action_id", "")),
						"action": str(motion.get("action", "")),
						"sequence": int(motion.get("variant", 1)) - 1,
						"loop": bool(motion.get("loop", false)),
						"duration_us": int(motion.get("duration_us", 0)),
					}
				)
			)
	return result


func set_weapon(vnum: int) -> bool:
	if not is_instance_valid(presentation) or not presentation.set_weapon(vnum):
		return false
	selected_weapon_vnum = vnum
	return true


func play_motion(motion: Dictionary) -> bool:
	if not is_instance_valid(presentation):
		return false
	return presentation.play_action(
		str(motion.get("mode_id", "")),
		str(motion.get("action_id", "")),
		str(motion.get("action", "")),
		int(motion.get("sequence", 0)),
		0,
		0,
		true
	)


func play_named(action: String) -> bool:
	if not is_instance_valid(presentation):
		return false
	var manifest_action := "normal_attack" if action == "attack" else action
	for motion in available_motions():
		if str(motion.get("action", "")) == manifest_action:
			return play_motion(motion)
	return false


func set_timeline_fraction(value: float) -> bool:
	if not is_instance_valid(presentation) or presentation.animation_player == null:
		return false
	var duration := float(int(presentation.current_motion.get("duration_us", 0))) / 1_000_000.0
	if duration <= 0.0:
		return false
	presentation.animation_player.seek(clampf(value, 0.0, 1.0) * duration, true)
	presentation.animation_player.pause()
	return true


func snapshot() -> Dictionary:
	return presentation.snapshot() if is_instance_valid(presentation) else {"error": error_message}
