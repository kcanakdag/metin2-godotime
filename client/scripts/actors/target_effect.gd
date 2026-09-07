class_name TargetEffect
extends Node3D
## Standalone actor-local target effect with the source client's discrete clock.

const SHADER_TEMPLATE := """shader_type spatial;
render_mode %s, unshaded, cull_disabled, depth_draw_never;
uniform sampler2D source_texture : source_color, repeat_enable, filter_linear;
uniform vec4 source_tint : source_color = vec4(1.0);
uniform float frame_alpha = 1.0;
void fragment() {
    vec4 sampled = texture(source_texture, UV);
    ALBEDO = sampled.rgb * source_tint.rgb;
    ALPHA = sampled.a * frame_alpha;
}
"""

var error_message := ""
var _catalog: TargetEffectCatalog
var _effect_id := ""
var _definition: Dictionary = {}
var _layer_tracks: Array[Dictionary] = []
var _frame := 0
var _remaining_us := 0
var _last_advances := 0


func configure(catalog: TargetEffectCatalog, effect_id: String) -> bool:
	_clear_layers()
	error_message = ""
	if catalog == null or not catalog.loaded:
		return _fail("Target-effect catalog is not loaded.")
	var definition := catalog.effect(effect_id)
	if definition.is_empty():
		return _fail("Unknown target-effect ID: %s" % effect_id)
	_catalog = catalog
	_effect_id = effect_id
	_definition = definition
	position = Vector3.ZERO
	for asset_id: Variant in definition.layers:
		if not _add_layer(catalog.asset(str(asset_id))):
			_clear_layers()
			return false
	reset_clock()
	set_process(true)
	return true


func reset_clock() -> void:
	_frame = 0
	_last_advances = 0
	_remaining_us = int(_catalog.playback().get("frame_us", 0)) if _catalog != null else 0
	_apply_frame()


func snapshot() -> Dictionary:
	var alpha: Array = []
	var morph_weights: Array = []
	var mesh_bounds: Array = []
	for layer: Dictionary in _layer_tracks:
		var values: Array = []
		for surface: Dictionary in layer.surfaces:
			values.append(surface.definition.frame_alpha_u8[_frame])
		alpha.append(values)
		var mesh := layer.mesh as MeshInstance3D
		var weights: Array[float] = []
		for blend_shape in mesh.mesh.get_blend_shape_count():
			weights.append(mesh.get_blend_shape_value(blend_shape))
		morph_weights.append(weights)
		var bounds := mesh.get_aabb()
		(
			mesh_bounds
			. append(
				{
					"position": [bounds.position.x, bounds.position.y, bounds.position.z],
					"size": [bounds.size.x, bounds.size.y, bounds.size.z],
				}
			)
		)
	return {
		"configured": not _definition.is_empty(),
		"effect_id": _effect_id,
		"frame": _frame,
		"remaining_us": _remaining_us,
		"last_advances": _last_advances,
		"layer_count": _layer_tracks.size(),
		"alpha_u8": alpha,
		"morph_weights": morph_weights,
		"mesh_bounds": mesh_bounds,
	}


func _process(delta: float) -> void:
	if _definition.is_empty() or not is_finite(delta) or delta < 0.0:
		return
	_remaining_us -= roundi(delta * 1_000_000.0)
	_last_advances = 0
	var playback := _catalog.playback()
	while _remaining_us < 0 and _last_advances < int(playback.max_advances_per_tick):
		_remaining_us += int(playback.frame_us)
		_frame = (_frame + 1) % int(playback.frame_count)
		_last_advances += 1
	if _last_advances > 0:
		_apply_frame()


func _add_layer(asset: Dictionary) -> bool:
	if asset.is_empty():
		return _fail("Target-effect layer references an unknown asset.")
	var model_path := _catalog.resource_path(str(asset.model))
	var packed: PackedScene = load(model_path)
	if packed == null:
		return _fail("Could not load target-effect model: %s" % model_path)
	var instance := packed.instantiate()
	add_child(instance)
	return _track_layer(asset, instance)


func _track_layer(asset: Dictionary, instance: Node) -> bool:
	var meshes := _children_of_type(instance, &"MeshInstance3D")
	var players := _children_of_type(instance, &"AnimationPlayer")
	if meshes.size() != 1 or players.size() != 1:
		instance.free()
		return _fail("Target-effect model has an incompatible imported node structure.")
	var mesh_instance := meshes[0] as MeshInstance3D
	if (
		mesh_instance.mesh.get_surface_count() != asset.surfaces.size()
		or mesh_instance.mesh.get_blend_shape_count() != 10
	):
		instance.free()
		return _fail("Target-effect model surface count differs from its catalog.")
	var surfaces: Array[Dictionary] = []
	for surface_definition: Dictionary in asset.surfaces:
		var material := _make_material(surface_definition)
		if material == null:
			instance.free()
			return false
		mesh_instance.set_surface_override_material(int(surface_definition.index), material)
		surfaces.append({"definition": surface_definition, "material": material})
	var player := players[0] as AnimationPlayer
	var animation_name := _loop_animation(player)
	if animation_name.is_empty():
		instance.free()
		return _fail("Target-effect model has no loop animation.")
	var animation := player.get_animation(animation_name)
	var frame_times := _animation_frame_times(animation)
	if frame_times.is_empty():
		instance.free()
		return _fail("Target-effect model animation is not the expected STEP 0.22s cycle.")
	player.play(animation_name)
	player.pause()
	(
		_layer_tracks
		. append(
			{
				"instance": instance,
				"mesh": mesh_instance,
				"player": player,
				"frame_times": frame_times,
				"surfaces": surfaces,
			}
		)
	)
	return true


func _make_material(definition: Dictionary) -> ShaderMaterial:
	var blend_mode := (
		"blend_mix" if definition.blend == "source_alpha_inverse_source_alpha" else "blend_add"
	)
	var shader := Shader.new()
	shader.code = SHADER_TEMPLATE % blend_mode
	var material := ShaderMaterial.new()
	material.shader = shader
	var texture_path := _catalog.resource_path(str(definition.texture))
	var texture: Texture2D = load(texture_path)
	if texture == null:
		_fail("Could not load target-effect texture: %s" % texture_path)
		return null
	material.set_shader_parameter("source_texture", texture)
	var tint: Array = definition.tint_srgba8
	material.set_shader_parameter(
		"source_tint", Color8(int(tint[0]), int(tint[1]), int(tint[2]), int(tint[3]))
	)
	return material


func _apply_frame() -> void:
	if _catalog == null:
		return
	for layer: Dictionary in _layer_tracks:
		var player := layer.player as AnimationPlayer
		player.seek(float(layer.frame_times[_frame]), true)
		player.advance(0.0)
		for surface: Dictionary in layer.surfaces:
			var definition: Dictionary = surface.definition
			var alpha := float(definition.frame_alpha_u8[_frame]) / 255.0
			(surface.material as ShaderMaterial).set_shader_parameter("frame_alpha", alpha)


func _loop_animation(player: AnimationPlayer) -> StringName:
	for name in player.get_animation_list():
		if "loop" in String(name).to_lower():
			return name
	return &""


func _animation_frame_times(animation: Animation) -> Array[float]:
	var result: Array[float] = []
	if (
		animation == null
		or not is_equal_approx(animation.length, 0.22)
		or animation.loop_mode == Animation.LOOP_NONE
		or animation.get_track_count() != 10
	):
		return result
	var imported_times: Dictionary = {}
	for track in animation.get_track_count():
		if (
			animation.track_get_interpolation_type(track) != Animation.INTERPOLATION_NEAREST
			or animation.track_get_type(track) != Animation.TYPE_BLEND_SHAPE
			or not String(animation.track_get_path(track)).ends_with(":Frame_%02d" % (track + 1))
			or animation.track_get_key_count(track) < 4
			or animation.track_get_key_count(track) > 12
		):
			return []
		for key in animation.track_get_key_count(track):
			var key_time := animation.track_get_key_time(track, key)
			var frame := roundi(key_time / 0.02)
			if frame < 0 or frame > 11 or not is_equal_approx(key_time, float(frame) * 0.02):
				return []
			if imported_times.has(frame) and imported_times[frame] != key_time:
				return []
			imported_times[frame] = key_time
	if imported_times.size() != 12:
		return []
	for frame in 11:
		result.append(imported_times[frame])
	return result


func _children_of_type(node: Node, type_name: StringName) -> Array[Node]:
	var result: Array[Node] = []
	for child in node.get_children():
		if child.is_class(type_name):
			result.append(child)
		result.append_array(_children_of_type(child, type_name))
	return result


func _clear_layers() -> void:
	set_process(false)
	for child in get_children():
		child.free()
	_catalog = null
	_effect_id = ""
	_definition = {}
	_layer_tracks = []
	_frame = 0
	_remaining_us = 0
	_last_advances = 0


func _fail(message: String) -> bool:
	error_message = message
	return false
