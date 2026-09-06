@tool
extends Node3D

const MODEL_PATH := "res://assets/imported/warrior.glb"


func _ready() -> void:
	if get_child_count() > 0:
		return
	if ResourceLoader.exists(MODEL_PATH):
		var packed := load(MODEL_PATH) as PackedScene
		if packed:
			var model := packed.instantiate()
			model.name = "Warrior"
			add_child(model)
	else:
		var placeholder := MeshInstance3D.new()
		placeholder.name = "MissingAsset"
		placeholder.mesh = CapsuleMesh.new()
		placeholder.position.y = 1.0
		add_child(placeholder)
