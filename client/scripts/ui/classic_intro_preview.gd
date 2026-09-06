extends SubViewportContainer
## Isolated visual preview: original warrior geometry, never a gameplay player.

const MODEL := "res://assets/imported/warrior.glb"

var _viewport: SubViewport
var _stage: Node3D
var _models: Dictionary = {}
var _selected_slot := 0
var _creating := false


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	stretch = true
	_viewport = SubViewport.new()
	_viewport.transparent_bg = true
	_viewport.own_world_3d = true
	_viewport.size = Vector2i(1010, 800)
	add_child(_viewport)
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_CLEAR_COLOR
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.8, 0.8, 0.8)
	environment.environment.ambient_light_energy = 0.8
	_stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -25, 0)
	light.light_color = Color(1, 0.9, 0.8)
	light.light_energy = 1.0
	_stage.add_child(light)
	var camera := Camera3D.new()
	camera.fov = 10
	camera.position = Vector3(0, 4.96, 14.97)
	camera.near = 0.1
	camera.far = 50
	_stage.add_child(camera)
	camera.look_at(Vector3(0, 0.95, 0))
	camera.current = true
	visibility_changed.connect(_update_rendering)
	_update_rendering()


func set_characters(rows: Array, slot: int, creating: bool) -> void:
	_selected_slot = slot
	_creating = creating
	var wanted: Dictionary = {}
	if creating:
		wanted[slot] = true
	else:
		for row: Dictionary in rows:
			wanted[int(row.get("slot", 0))] = true
	for key in _models.keys():
		if not wanted.has(key):
			_models[key].queue_free()
			_models.erase(key)
	for key in wanted:
		if not _models.has(key) and ResourceLoader.exists(MODEL):
			var model := (load(MODEL) as PackedScene).instantiate() as Node3D
			model.name = "WarriorSlot%d" % key
			_stage.add_child(model)
			_models[key] = model
			_play_wait(model)
	_update_positions(true)


func _process(delta: float) -> void:
	_update_positions(false, delta)


func snapshot() -> Dictionary:
	return {"models": _models.size(), "selected_slot": _selected_slot, "creating": _creating}


func _update_positions(immediate: bool, delta: float = 0) -> void:
	for slot in _models:
		var model: Node3D = _models[slot]
		var angle := float(posmod(int(slot) - _selected_slot, 4)) * PI / 2
		var target := Vector3(sin(angle) * 0.707, 0, cos(angle) * 0.707)
		if _creating:
			target = Vector3.ZERO
		model.position = target if immediate else model.position.lerp(target, 1 - exp(-delta * 9))


func _play_wait(node: Node) -> void:
	if node is AnimationPlayer:
		for animation in node.get_animation_list():
			if "wait" in animation:
				node.get_animation(animation).loop_mode = Animation.LOOP_LINEAR
				node.play(animation)
				return
	for child in node.get_children():
		_play_wait(child)


func _update_rendering() -> void:
	if _viewport:
		_viewport.render_target_update_mode = (
			SubViewport.UPDATE_ALWAYS if is_visible_in_tree() else SubViewport.UPDATE_DISABLED
		)
