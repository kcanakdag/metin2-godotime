extends Node3D
## Offline map inspection; these camera coordinates are never sent as player movement.

@export var map_name := "metin2_map_a1"
var world: Node3D
var speed := 35.0
var show_attributes := false
var map_size := Vector2(1024, 1280)
var focus := Vector3(660, 200, 575)

@onready var camera: Camera3D = $Camera3D
@onready var status: Label = $HUD/Panel/Margin/Text


func _ready() -> void:
	var arguments := OS.get_cmdline_user_args()
	var map_option := arguments.find("--map")
	if map_option >= 0 and map_option + 1 < arguments.size():
		map_name = arguments[map_option + 1]
	if not map_name.is_valid_filename():
		status.text = "Invalid map name"
		set_process(false)
		return
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.58, 0.68, 0.76)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.82, 0.87, 1.0)
	environment.ambient_light_energy = 0.7
	$WorldEnvironment.environment = environment
	var path := "res://assets/imported/maps/" + map_name + "/map.tscn"
	if not ResourceLoader.exists(path):
		status.text = "Map has not been imported. Run make import-map, then reopen this preview."
		set_process(false)
		return
	world = load(path).instantiate()
	add_child(world)
	var dimensions: Array = world.get_meta("map_size", [4, 5])
	map_size = Vector2(dimensions[0], dimensions[1]) * 256.0
	if map_name != "metin2_map_a1":
		focus = Vector3(map_size.x / 2, 180, map_size.y / 2)
	reset_view()
	update_status()


func _process(delta: float) -> void:
	var direction := Vector3.ZERO
	direction.x = (
		float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))
	)
	direction.z = (
		float(Input.is_physical_key_pressed(KEY_S)) - float(Input.is_physical_key_pressed(KEY_W))
	)
	var movement := camera.basis * direction
	movement.y += (
		float(Input.is_physical_key_pressed(KEY_E)) - float(Input.is_physical_key_pressed(KEY_Q))
	)
	var boost := 4.0 if Input.is_physical_key_pressed(KEY_SHIFT) else 1.0
	camera.position += movement.limit_length() * speed * boost * delta


func _unhandled_input(event: InputEvent) -> void:
	if not world:
		return
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		camera.rotation.y -= event.relative.x * 0.004
		camera.rotation.x = clampf(camera.rotation.x - event.relative.y * 0.004, -1.5, 1.5)
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			speed = minf(speed * 1.25, 500.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			speed = maxf(speed / 1.25, 2.0)
		update_status()
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_R:
				reset_view()
			KEY_M:
				camera.position = Vector3(map_size.x / 2, 1400, map_size.y / 2 + 1)
				camera.look_at(Vector3(map_size.x / 2, 0, map_size.y / 2))
			KEY_U:
				var markers := world.get_node("UnsupportedMarkers") as Node3D
				markers.visible = not markers.visible
			KEY_C:
				toggle_attributes()
		update_status()


func reset_view() -> void:
	camera.position = focus + Vector3(10, 65, 105)
	camera.look_at(focus)


func toggle_attributes() -> void:
	show_attributes = not show_attributes
	for node in world.get_node("Sections").find_children("*", "MeshInstance3D"):
		if node.material_override is ShaderMaterial:
			node.material_override.set_shader_parameter("show_attributes", show_attributes)


func update_status() -> void:
	if not world:
		return
	var counts: Dictionary = world.get_meta("import_counts")
	status.text = (
		("Yongan" if map_name == "metin2_map_a1" else map_name)
		+ " · original map inspection\n"
		+ (
			"%d scenery imported · %d unsupported placements\n"
			% [counts.get("converted", 0), counts.get("unsupported", 0) + counts.get("failed", 0)]
		)
		+ "WASD fly · Q/E down/up · right drag look · Shift faster · wheel speed\n"
		+ "R town · M overview · U missing markers · C terrain attributes\n"
		+ "Speed %d m/s · offline preview" % speed
	)


func dev_snapshot() -> Dictionary:
	return {
		"map_loaded": is_instance_valid(world),
		"camera": [camera.position.x, camera.position.y, camera.position.z],
		"camera_rotation": [camera.rotation.x, camera.rotation.y, camera.rotation.z],
		"speed_m_s": speed,
		"attributes": show_attributes,
		"markers": world.get_node("UnsupportedMarkers").visible if world else false,
		"counts": world.get_meta("import_counts") if world else {},
		"fps": Engine.get_frames_per_second(),
	}
