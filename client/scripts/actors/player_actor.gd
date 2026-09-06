class_name PlayerActor
extends Node3D
## Render a server character. This node never owns gameplay coordinates.

const MODEL_PATH := "res://assets/imported/warrior.glb"

var identity := ""
var server_position := Vector3.ZERO
var server_heading := 0.0
var row: Dictionary = {}
var is_local := false
var _animation: AnimationPlayer
var _clips: Dictionary = {}
var _current_clip := ""
var _attack_sequence := -1
var _name_label: Label3D
var _initialized := false


func _ready() -> void:
	var visual := Node3D.new()
	visual.name = "Visual"
	# The GR2 fixture faces +Z; gameplay uses Godot's -Z forward convention.
	visual.rotation.y = PI
	add_child(visual)
	if ResourceLoader.exists(MODEL_PATH):
		var packed := load(MODEL_PATH) as PackedScene
		var model := packed.instantiate()
		visual.add_child(model)
		_animation = _find_animation(model)
		if _animation:
			for key in _animation.get_animation_list():
				var clip := str(key).replace(".", "_").get_slice("_", 1)
				_clips[clip] = key
				var loop := Animation.LOOP_NONE if clip == "attack" else Animation.LOOP_LINEAR
				_animation.get_animation(key).loop_mode = loop
	else:
		var mesh := MeshInstance3D.new()
		mesh.mesh = CapsuleMesh.new()
		mesh.position.y = 1.0
		visual.add_child(mesh)
	_name_label = Label3D.new()
	_name_label.name = "Nameplate"
	_name_label.position.y = 2.15
	_name_label.font_size = 42
	_name_label.pixel_size = 0.007
	_name_label.outline_size = 9
	_name_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(_name_label)


func apply_state(state_row: Dictionary, local: bool) -> void:
	row = state_row.duplicate()
	identity = str(row.identity)
	is_local = local
	server_position = Vector3(float(row.x), float(row.get("y", 0)), float(row.z))
	server_heading = float(row.heading)
	if not _initialized or position.distance_to(server_position) > 8.0:
		position = server_position
		rotation.y = server_heading
		_initialized = true
	_name_label.text = str(row.name) + ("  • YOU" if local else "")
	_name_label.modulate = Color("f0d087") if local else Color("dce8d9")
	var activity := int(row.activity)
	$Visual.rotation.z = PI * 0.5 if activity == 3 else 0.0
	_name_label.text += "  • DEFEATED" if activity == 3 else ""
	var sequence := int(row.attack_sequence)
	var clip := "attack" if activity == 2 else ("run" if activity == 1 else "wait")
	if clip != _current_clip or (clip == "attack" and sequence != _attack_sequence):
		_play_clip(clip)
	_attack_sequence = sequence


func _process(delta: float) -> void:
	if not _initialized:
		return
	var weight := 1.0 - exp(-delta * (20.0 if is_local else 12.0))
	position = position.lerp(server_position, weight)
	rotation.y = lerp_angle(rotation.y, server_heading, weight)


func _play_clip(clip: String) -> void:
	_current_clip = clip
	if _animation and _clips.has(clip):
		_animation.play(_clips[clip], 0.13)


func _find_animation(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node
	for child in node.get_children():
		var found := _find_animation(child)
		if found:
			return found
	return null
