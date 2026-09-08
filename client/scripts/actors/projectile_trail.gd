extends MeshInstance3D
## Original untextured additive trail, with timestamped segment history.

const TRIANGLES := [0, 1, 2, 2, 1, 3, 2, 3, 4, 4, 3, 5]
var history: Array[Dictionary] = []
var _definition: Dictionary = {}
var _material: ShaderMaterial


func configure(definition: Dictionary) -> bool:
	if not is_inside_tree():
		return false
	var duration := float(definition.length_seconds)
	var width := float(definition.size_cm)
	if not is_finite(duration) or not is_finite(width):
		return false
	if duration >= 0 and (duration > 60 or width <= 0 or width > 10000):
		return false
	_definition = definition.duplicate(true)
	history.clear()
	mesh = ImmediateMesh.new()
	top_level = true
	global_transform = Transform3D.IDENTITY
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var shader := Shader.new()
	shader.code = """shader_type spatial;
render_mode blend_add, unshaded, cull_disabled, depth_draw_never;
void fragment() { ALBEDO = COLOR.rgb; ALPHA = COLOR.a; }
"""
	_material = ShaderMaterial.new()
	_material.shader = shader
	return true


func advance(time: float, point: Vector3, camera: Camera3D) -> bool:
	if (
		_definition.is_empty()
		or not is_finite(time)
		or time < 0
		or not point.is_finite()
		or camera == null
	):
		return false
	if not history.is_empty() and time <= float(history[0].time):
		return false
	history.push_front({"time": time, "point": point})
	while (
		not history.is_empty()
		and float(history.back().time) + float(_definition.length_seconds) < time
	):
		history.pop_back()
	_draw(time, camera)
	return true


func _draw(time: float, camera: Camera3D) -> void:
	var geometry := mesh as ImmediateMesh
	geometry.clear_surfaces()
	if history.size() <= 1:
		return
	var color := int(_definition.argb)
	var tint := Color(
		float((color >> 16) & 255) / 255,
		float((color >> 8) & 255) / 255,
		float(color & 255) / 255,
		float((color >> 24) & 255) / 255
	)
	var view := -camera.global_basis.z
	var segments: Array[Dictionary] = []
	for index: int in range(1, history.size()):
		var newer: Dictionary = history[index - 1]
		var older: Dictionary = history[index]
		var delta: Vector3 = older.point - newer.point
		var eye: Vector3 = camera.global_position - newer.point
		var up := view.cross(delta.cross(eye)).normalized()
		var right := view.cross(up)
		var width1 := float(_definition.size_cm) * 0.01
		var width2 := width1
		if not _definition.rectangular:
			width1 *= 1.0 - (time - float(newer.time)) / float(_definition.length_seconds)
			width2 *= 1.0 - (time - float(older.time)) / float(_definition.length_seconds)
		var vertices: Array[Vector3] = [
			newer.point + up * width1,
			newer.point - right * width1,
			newer.point + right * width1,
			older.point - right * width2,
			older.point + right * width2,
			older.point - up * width2,
		]
		segments.append({"depth": -eye.dot(view), "vertices": vertices})
	segments.sort_custom(func(a: Dictionary, b: Dictionary): return a.depth < b.depth)
	geometry.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _material)
	geometry.surface_set_color(tint)
	for segment: Dictionary in segments:
		for index: int in TRIANGLES:
			geometry.surface_add_vertex(segment.vertices[index])
	geometry.surface_end()
