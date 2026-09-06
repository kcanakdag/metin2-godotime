class_name OrbitCamera
extends Node3D

var distance := 12.0
var yaw := 0.0
var pitch := deg_to_rad(48.0)
var target: Node3D

@onready var camera: Camera3D = $Camera3D


func _process(delta: float) -> void:
	if is_instance_valid(target):
		var desired := target.global_position + Vector3.UP * 0.8
		global_position = (
			desired
			if global_position.distance_to(desired) > 40.0
			else global_position.lerp(desired, 1.0 - exp(-delta * 9.0))
		)
	var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
	camera.position = offset * distance
	camera.look_at(global_position)


func orbit(relative: Vector2) -> void:
	yaw -= relative.x * 0.006
	pitch = clampf(pitch + relative.y * 0.004, deg_to_rad(25), deg_to_rad(72))


func zoom(amount: float) -> void:
	distance = clampf(distance + amount, 5.0, 20.0)


func move_direction(input: Vector2) -> Vector2:
	var right := Vector3(cos(yaw), 0, -sin(yaw))
	var forward := Vector3(-sin(yaw), 0, -cos(yaw))
	var direction := right * input.x + forward * -input.y
	return Vector2(direction.x, direction.z)


func ground_point(screen_position: Vector2) -> Variant:
	var origin := camera.project_ray_origin(screen_position)
	var direction := camera.project_ray_normal(screen_position)
	return Plane(Vector3.UP, 0.0).intersects_ray(origin, direction)
