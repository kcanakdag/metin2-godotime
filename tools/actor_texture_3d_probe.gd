extends SceneTree


func _init() -> void:
	var scene := load("res://tests/actor_texture_3d_scene.tscn") as PackedScene
	var mesh := scene.instantiate() as MeshInstance3D
	var material := mesh.get_active_material(0) as StandardMaterial3D
	if material == null or material.albedo_texture == null:
		mesh.free()
		push_error("3D material did not retain the selected actor texture")
		quit(1)
		return
	mesh.free()
	call_deferred("complete")


func complete() -> void:
	print("ACTOR_TEXTURE_3D PASS")
	quit(0)
