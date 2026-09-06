@tool
extends Node3D

const ActorCatalogScript := preload("res://scripts/content/actor_catalog.gd")
const ActorPresentationScript := preload("res://scripts/actors/actor_presentation.gd")

var catalog := ActorCatalogScript.new()
var presentation: Node3D
var error_message := ""


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
	presentation.set_weapon(0)
	presentation.play_action("general", "", "wait", 0)


func play_named(action: String) -> bool:
	if not is_instance_valid(presentation):
		return false
	var manifest_action := "normal_attack" if action == "attack" else action
	return presentation.play_action("general", "", manifest_action, 0, 0, 0, true)


func snapshot() -> Dictionary:
	return presentation.snapshot() if is_instance_valid(presentation) else {"error": error_message}
