class_name NpcActor
extends Node3D
## Converted stationary NPC with a picking-only proxy; no movement collision.

var error_message := ""
var spawn_id := ""
var _animation: AnimationPlayer
var _idle: Array = []
var _remaining := 0.0
var _random := RandomNumberGenerator.new()


func configure(definition: Dictionary, spawn: Dictionary, packed: PackedScene) -> bool:
	spawn_id = str(spawn.id)
	position = Vector3(spawn.position[0], spawn.position[1], spawn.position[2])
	rotation.y = float(spawn.yaw)
	var visual := packed.instantiate() as Node3D
	if visual == null:
		error_message = "NPC model has no 3D root."
		return false
	add_child(visual)
	var players := visual.find_children("*", "AnimationPlayer", true, false)
	if players.size() != 1:
		error_message = "NPC model requires one animation player."
		return false
	_animation = players[0] as AnimationPlayer
	_idle = definition.idle.duplicate(true)
	for motion: Dictionary in _idle:
		if (
			not _animation.has_animation(motion.clip)
			or _animation.get_animation(motion.clip).length <= 0.0
		):
			error_message = "NPC model is missing a declared idle animation."
			return false
	_random.seed = spawn_id.hash()
	var label := Label3D.new()
	label.name = "NameLabel"
	label.text = definition.name
	label.position.y = float(definition.label_height)
	label.font_size = 36
	label.pixel_size = 0.006
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	# Pinned original root/colorinfo.py CHR_NAME_RGB_NPC.
	label.modulate = Color8(122, 231, 93)
	add_child(label)
	_add_pick_proxy(float(definition.label_height) - 0.2)
	_next_idle()
	return true


func _process(delta: float) -> void:
	if _animation == null:
		return
	_remaining -= delta
	if _remaining <= 0.0:
		_next_idle()


func _next_idle() -> void:
	var roll := _random.randi_range(0, 99)
	for motion: Dictionary in _idle:
		roll -= int(motion.weight)
		if roll < 0:
			_animation.play(motion.clip, 0.15)
			_animation.seek(0, true)
			_remaining = _animation.get_animation(motion.clip).length
			return


func _add_pick_proxy(height: float) -> void:
	var body := StaticBody3D.new()
	body.name = "NpcPickBody"
	body.collision_layer = WorldPicker.TARGET_COLLISION_LAYER
	body.collision_mask = 0
	body.set_meta("npc_actor", self)
	body.set_meta("spawn_id", spawn_id)
	body.position.y = height * 0.5
	var shape := CapsuleShape3D.new()
	shape.radius = 0.45
	shape.height = maxf(height, shape.radius * 2)
	var collider := CollisionShape3D.new()
	collider.shape = shape
	body.add_child(collider)
	add_child(body)


func set_hovered(value: bool) -> void:
	$NameLabel.modulate = Color.WHITE if value else Color8(122, 231, 93)
