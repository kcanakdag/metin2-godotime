extends Node3D
## Selected original particle rendering. Caller supplies the simulation clock.

const Simulation = preload("res://scripts/actors/particle_simulation.gd")
const Motion = preload("res://scripts/actors/particle_motion.gd")
const SHADER := """shader_type spatial;
render_mode %s, unshaded, cull_disabled, depth_draw_never;
uniform float color_multiplier = 1.0;
uniform sampler2D source_texture : source_color, repeat_enable, filter_linear;
void fragment() {
    vec4 sampled = texture(source_texture, UV);
    ALBEDO = clamp(sampled.rgb * COLOR.rgb * color_multiplier, vec3(0.0), vec3(1.0));
    ALPHA = sampled.a * COLOR.a;
}
"""
const UVS := [Vector2(0, 1), Vector2(0, 0), Vector2(1, 1), Vector2(1, 0)]
const TRIANGLES := [0, 1, 2, 2, 1, 3]

var _layers: Array[Dictionary] = []


func configure(effect: Dictionary, textures: Dictionary, random_seed: int) -> bool:
	var candidates: Array[Dictionary] = []
	for recipe: Dictionary in effect.systems:
		var style: Dictionary = recipe.particle
		if (
			int(style.SrcBlendType) != 5
			or int(style.DestBlendType) not in [2, 6]
			or int(style.ColorOperationType) not in [4, 5]
			or int(style.BillboardType) not in [0, 1, 2, 3, 4, 5]
			or style.curves.ScaleX.is_empty()
			or style.curves.ScaleY.is_empty()
			or style.packed_color_keys.is_empty()
		):
			return false
		var simulation := Simulation.new()
		if not simulation.configure(recipe, random_seed + candidates.size()):
			return false
		var materials: Array[ShaderMaterial] = []
		for path: String in style.textures:
			if not textures.get(path) is Texture2D:
				return false
			var shader := Shader.new()
			shader.code = SHADER % ("blend_add" if int(style.DestBlendType) == 2 else "blend_mix")
			var material := ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter("source_texture", textures[path])
			material.set_shader_parameter(
				"color_multiplier", 2.0 if int(style.ColorOperationType) == 5 else 1.0
			)
			materials.append(material)
		candidates.append(
			{"recipe": recipe.duplicate(true), "simulation": simulation, "materials": materials}
		)
	for layer: Dictionary in _layers:
		remove_child(layer.node)
		layer.node.queue_free()
	_layers = candidates
	for layer: Dictionary in _layers:
		var node := MeshInstance3D.new()
		node.mesh = ImmediateMesh.new()
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(node)
		node.top_level = true
		node.global_transform = Transform3D.IDENTITY
		layer.node = node
	return true


func advance(delta: float, camera: Camera3D, emitting: bool = true) -> Dictionary:
	if camera == null or not is_inside_tree():
		return {"error": "Particle renderer needs an active camera and scene"}
	var alive := 0
	var finished := true
	for layer: Dictionary in _layers:
		var result: Dictionary = layer.simulation.advance(delta, global_transform, emitting)
		if result.has("error"):
			return result
		alive += int(result.alive)
		finished = finished and bool(result.finished)
		_draw(layer, camera)
	return {"alive": alive, "finished": finished}


func _draw(layer: Dictionary, camera: Camera3D) -> void:
	var mesh: ImmediateMesh = layer.node.mesh
	mesh.clear_surfaces()
	for frame: int in range(layer.materials.size()):
		var started := false
		for particle: Dictionary in layer.simulation.particles.values():
			if int(particle.frame) != frame:
				continue
			if not started:
				mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, layer.materials[frame])
				started = true
			var billboard := int(layer.recipe.particle.BillboardType)
			var face_rotations: Array[float] = [0.0]
			if billboard == 4:
				face_rotations = [-PI / 6.0, PI / 6.0]
			elif billboard == 5:
				face_rotations = [0.0, -PI / 3.0, PI / 3.0]
			for face_rotation: float in face_rotations:
				var corners := _corners(particle, layer.recipe, camera, face_rotation)
				for index: int in TRIANGLES:
					mesh.surface_set_color(particle.color)
					mesh.surface_set_uv(UVS[index])
					mesh.surface_add_vertex(corners[index])
		if started:
			mesh.surface_end()


func _corners(
	particle: Dictionary, recipe: Dictionary, camera: Camera3D, face_rotation: float = 0.0
) -> Array[Vector3]:
	var view := -camera.global_basis.z
	var up := -camera.global_basis.x
	var cross_axis := camera.global_basis.y
	if int(recipe.particle.StretchEnable) != 0:
		up = particle.position - particle.previous_position
		if particle.attached:
			up = global_basis * up
		var length_cm := up.length() * 100.0
		up = Vector3.UP if length_cm == 0 else up.normalized() * (1.0 + log(1.0 + length_cm))
		cross_axis = up.cross(view).normalized()
	else:
		var angle := deg_to_rad(float(particle.rotation))
		var billboard := int(recipe.particle.BillboardType)
		if billboard == 3:
			up = Vector3(cos(angle), 0, sin(angle))
			cross_axis = Vector3(sin(angle), 0, -cos(angle))
		elif billboard in [2, 4, 5]:
			up = Vector3.UP
			var view_ground := Vector3(view.x, 0, view.z)
			cross_axis = up.cross(view_ground)
			cross_axis = (
				cross_axis.normalized()
				if cross_axis.length_squared() > 0.000001
				else camera.global_basis.x
			)
			if angle:
				var face_cos := -sin(angle)
				var face_sin := cos(angle)
				var rotated_up := up * face_cos - cross_axis * face_sin
				cross_axis = cross_axis * face_cos + up * face_sin
				up = rotated_up
		else:
			up = up.rotated(view, -angle)
			cross_axis = cross_axis.rotated(view, -angle)
		if face_rotation:
			up = up.rotated(Vector3.UP, face_rotation)
			cross_axis = cross_axis.rotated(Vector3.UP, face_rotation)
	cross_axis *= -float(particle.half_size.x) * float(particle.scale.x)
	up *= float(particle.half_size.y) * float(particle.scale.y)
	var center := Motion.world_position(particle, global_transform)
	return [
		center - up + cross_axis,
		center - up - cross_axis,
		center + up + cross_axis,
		center + up - cross_axis
	]
