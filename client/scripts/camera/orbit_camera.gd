class_name OrbitCamera
extends Node3D

const ScreenWaveScript := preload("res://scripts/camera/screen_wave.gd")

var distance := 12.0
var yaw := 0.0
var pitch := deg_to_rad(48.0)
var target: Node3D

var _screen_wave := ScreenWaveScript.new()

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
	camera.position = offset * distance + _screen_wave.advance(delta)
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


func observe_screen_wave(
	actor_identity: String,
	action: Dictionary,
	event: Dictionary,
	actor_position: Vector3,
	viewer_position: Vector3,
	server_time_us: int
) -> bool:
	return _screen_wave.observe(
		actor_identity, action, event, actor_position, viewer_position, server_time_us
	)


func set_screen_wave_enabled(value: bool) -> void:
	_screen_wave.set_enabled(value)


func reset_screen_waves() -> void:
	_screen_wave.reset()


func screen_wave_snapshot() -> Dictionary:
	return _screen_wave.snapshot()
