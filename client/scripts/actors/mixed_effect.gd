extends Node3D
## Complete imported particle/mesh effect. Owns all layers and their shared clock.

const Particles = preload("res://scripts/actors/particle_effect.gd")
const MeshEffect = preload("res://scripts/actors/projectile_mesh_effect.gd")
var _particles: Node3D
var _meshes: Array[Node3D] = []
var _finished := false


func configure(
	definition: Dictionary, scenes: Dictionary, textures: Dictionary, seed_value: int
) -> bool:
	if not is_inside_tree() or _particles != null or definition.get("meshes", []).is_empty():
		return false
	# Validate references before creating any visible portion of the effect.
	for mesh: Dictionary in definition.meshes:
		if not scenes.get(mesh.model) is PackedScene or mesh.geometries.size() != 1:
			return false
		if not textures.get(mesh.geometries[0].texture) is Texture2D:
			return false
	var particles := Particles.new()
	add_child(particles)
	if not particles.configure(definition.particle_effect, textures, seed_value):
		particles.free()
		return false
	_particles = particles
	for mesh: Dictionary in definition.meshes:
		var layer := MeshEffect.new()
		add_child(layer)
		if not layer.configure(mesh, scenes[mesh.model], textures[mesh.geometries[0].texture]):
			layer.free()
			_clear()
			return false
		_meshes.append(layer)
	# The original renderer draws particle systems first, then mesh layers.
	var priority := 0
	for layer: Dictionary in _particles._layers:
		for material: ShaderMaterial in layer.materials:
			material.render_priority = priority
		priority += 1
	for layer: Node3D in _meshes:
		layer._mesh.material_override.render_priority = priority
		priority += 1
	_finished = false
	return true


func advance(delta: float, camera: Camera3D) -> Dictionary:
	if _particles == null:
		return {"error": "Mixed effect is not configured"}
	if _finished:
		return {"finished": true, "alive": 0}
	var state: Dictionary = _particles.advance(delta, camera)
	if state.has("error"):
		return state
	var finished: bool = state.finished
	for mesh: Node3D in _meshes:
		var frame: Dictionary = mesh.advance(delta, camera)
		if frame.has("error"):
			return frame
		finished = finished and bool(frame.finished)
	_finished = finished
	return {"finished": finished, "alive": state.alive}


func _clear() -> void:
	if _particles != null:
		_particles.free()
		_particles = null
	for mesh: Node3D in _meshes:
		mesh.free()
	_meshes.clear()
