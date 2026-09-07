extends SubViewportContainer
## Isolated class preview using the same converted appearance catalog as the world.

const ActorCatalogScript := preload("res://scripts/content/actor_catalog.gd")
const ActorPresentationScript := preload("res://scripts/actors/actor_presentation.gd")
const CAMERA_FACING_YAW := PI

var _viewport: SubViewport
var _stage: Node3D
var _models: Dictionary = {}
var _selected_slot := 0
var _creating := false
var _catalog := ActorCatalogScript.new()
var _error_message := ""


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if not _catalog.load_required(ActorCatalogScript.MANIFEST_PATH, true):
		_error_message = _catalog.error_message
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


func class_definition(class_id: int) -> Dictionary:
	return _catalog.characters.definition(class_id)


func title_art(class_id: int) -> String:
	var id := _catalog.characters.actor_id(class_id, 0)
	var model_key := str(_catalog.actor(id).get("model_key", ""))
	return "locale/en/ui/select/name_" + model_key.get_slice("_", 0)


func set_characters(rows: Array, slot: int, creating: bool, appearance: Dictionary = {}) -> void:
	_selected_slot = int(appearance.get("character_class", 0)) if creating else slot
	_creating = creating
	var wanted: Dictionary = {}
	if creating:
		for class_id in 4:
			wanted[class_id] = _catalog.characters.actor_id(class_id, int(appearance.get("sex", 0)))
	else:
		for row: Dictionary in rows:
			wanted[int(row.get("slot", 0))] = _catalog.player_actor_id(row)
	for key in _models.keys():
		if not wanted.has(key) or _models[key].actor_id != wanted[key]:
			_stage.remove_child(_models[key])
			_models[key].queue_free()
			_models.erase(key)
	for key in wanted:
		if not _models.has(key) and _error_message.is_empty():
			var model := ActorPresentationScript.new()
			model.name = "CharacterSlot%d" % key
			if not model.configure(_catalog, str(wanted[key])):
				_error_message = model.error_message
				model.queue_free()
				continue
			_stage.add_child(model)
			_models[key] = model
			# Converted actors use canonical -Z forward. The fixed intro camera is
			# on +Z, so turn this presentation toward it instead of showing its back.
			model.rotation.y = CAMERA_FACING_YAW
			model.set_weapon(0)
			model.play_action("intro", "", "wait", int(key))
			model.position = _target_position(int(key))
	_update_positions(false)


func _process(delta: float) -> void:
	_update_positions(false, delta)


func snapshot() -> Dictionary:
	var camera_facing := true
	var actors: Dictionary = {}
	var motions: Dictionary = {}
	for model: Node3D in _models.values():
		actors[model.name] = model.actor_id
		motions[model.name] = model.snapshot()
		camera_facing = (
			camera_facing and absf(wrapf(model.rotation.y - CAMERA_FACING_YAW, -PI, PI)) < 0.000001
		)
	return {
		"models": _models.size(),
		"actors": actors,
		"motions": motions,
		"selected_slot": _selected_slot,
		"creating": _creating,
		"camera_facing": camera_facing,
		"error": _error_message,
	}


func _update_positions(immediate: bool, delta: float = 0) -> void:
	for slot in _models:
		var model: Node3D = _models[slot]
		var target := _target_position(int(slot))
		model.position = target if immediate else model.position.lerp(target, 1 - exp(-delta * 9))


func _target_position(slot: int) -> Vector3:
	var angle := float(posmod(slot - _selected_slot, 4)) * PI / 2
	return Vector3(sin(angle) * sqrt(0.5), 0, cos(angle) * sqrt(0.5))


func _update_rendering() -> void:
	if _viewport:
		_viewport.render_target_update_mode = (
			SubViewport.UPDATE_ALWAYS if is_visible_in_tree() else SubViewport.UPDATE_DISABLED
		)
