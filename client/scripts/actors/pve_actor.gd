class_name PveActor
extends Node3D
## Procedural prototype sentinel and gold drops, driven entirely by replicated rows.

var row: Dictionary = {}
var loot_mode := false
var item_mode := false
var _target := Vector3.ZERO
var _visual: Node3D
var _label: Label3D
var _time := 0.0
var _sequence := -1
var _swing := 0.0


func _ready() -> void:
	_visual = Node3D.new()
	add_child(_visual)
	if loot_mode:
		if item_mode:
			var icon := Sprite3D.new()
			var icon_path := "res://assets/imported/ui/icon/item/27001.png"
			if ResourceLoader.exists(icon_path):
				icon.texture = load(icon_path)
			icon.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			icon.pixel_size = 0.018
			icon.position.y = 0.35
			_visual.add_child(icon)
		else:
			_part(Vector3(0, 0.35, 0), Vector3(0.35, 0.35, 0.35), Color("ffd26e"))
	else:
		_part(Vector3(0, 1.1, 0), Vector3(0.8, 1.15, 0.55), Color("5b6867"))
		_part(Vector3(0, 1.9, -0.08), Vector3(0.6, 0.55, 0.5), Color("687c7b"))
		for side in [-1.0, 1.0]:
			_part(Vector3(side * 0.6, 1.1, 0), Vector3(0.35, 1.0, 0.35), Color("778380"))
			_part(Vector3(side * 0.24, 0.35, 0), Vector3(0.36, 0.7, 0.45), Color("465853"))
			_part(Vector3(side * 0.15, 1.95, -0.36), Vector3(0.1, 0.09, 0.04), Color("ff6650"))
	_label = Label3D.new()
	_label.position.y = 0.85 if loot_mode else 2.5
	_label.font_size = 36
	_label.pixel_size = 0.006
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(_label)


func apply_state(value: Dictionary) -> void:
	var first := row.is_empty()
	row = value
	_target = Vector3(float(row.x), float(row.y), float(row.z))
	if first or position.distance_to(_target) > 8:
		position = _target
	if loot_mode:
		_label.text = "Red Potion (S)" if item_mode else "%d Yang" % int(row.gold)
		_label.modulate = Color("ffd26e")
	else:
		_label.text = "Stone Sentinel  %d / %d" % [int(row.health), int(row.max_health)]
		_label.modulate = Color("ed9a78")
		if int(row.attack_sequence) != _sequence:
			_swing = 0.45
		_sequence = int(row.attack_sequence)


func _process(delta: float) -> void:
	if row.is_empty():
		return
	_time += delta
	_swing = maxf(0, _swing - delta)
	position = position.lerp(_target, 1 - exp(-delta * 12))
	if loot_mode:
		if not item_mode:
			_visual.rotation.y += delta
		_visual.position.y = sin(_time * 3) * 0.1
		return
	rotation.y = lerp_angle(rotation.y, float(row.heading), 1 - exp(-delta * 12))
	_visual.rotation.z = PI * 0.5 if int(row.health) == 0 else 0.0
	_visual.rotation.x = sin(_swing / 0.45 * PI) * 0.4
	_visual.position.y = absf(sin(_time * 7)) * 0.08 if int(row.activity) == 1 else 0.0


func _part(point: Vector3, size: Vector3, color: Color) -> void:
	var node := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	node.mesh = mesh
	node.position = point
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	node.material_override = material
	_visual.add_child(node)
