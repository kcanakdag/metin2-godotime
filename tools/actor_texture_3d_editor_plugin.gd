@tool
extends EditorPlugin


func _enter_tree() -> void:
	call_deferred("exercise_scene")


func exercise_scene() -> void:
	var scene := load("res://tests/actor_texture_3d_scene.tscn") as PackedScene
	var mesh := scene.instantiate() as MeshInstance3D
	var material := mesh.get_active_material(0) as StandardMaterial3D
	if material == null or material.albedo_texture == null:
		push_error("editor 3D material did not retain the selected actor texture")
		return
	mesh.free()
	print("ACTOR_TEXTURE_EDITOR_SCENE PASS")
