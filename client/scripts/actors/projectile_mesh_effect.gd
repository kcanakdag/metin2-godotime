extends Node3D
## Selected original source-color mesh materials: opaque arrow or additive skill.
## The adaptation requires destination alpha 1; transparent viewports reject.

const FrameClock = preload("res://scripts/actors/mesh_frame_clock.gd")

const SHADER := """shader_type spatial;
render_mode blend_mix, unshaded, cull_disabled, depth_draw_never;
// Intentionally sample encoded RGB: original fixed-function blending squares it.
uniform sampler2D source_texture : repeat_enable, filter_linear;
uniform int color_operation = 4;
uniform vec3 color_factor = vec3(1.0);
vec3 decode_srgb(vec3 value) {
    return mix(value / 12.92, pow((value + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), value));
}
// Invert Compatibility's approximate color round trip. Coefficients describe
// the pinned engine transfer function; see docs/third-party.md. Newton's method
// is bounded here because the polynomial derivative is positive on [0, 1].
vec3 compatibility_input(vec3 encoded) {
    vec3 target = pow((encoded + 0.055) / 1.055, vec3(2.4));
    vec3 value = max(encoded, vec3(0.05));
    for (int i = 0; i < 5; i++) {
        vec3 polynomial = value * (value * (value * 0.305306011 + 0.682171111) + 0.012522878);
        vec3 derivative = value * (value * 0.915918033 + 1.364342222) + 0.012522878;
        value -= (polynomial - target) / derivative;
    }
    return clamp(value, vec3(0.0), vec3(1.0));
}
void fragment() {
    vec3 source = texture(source_texture, UV).rgb;
    // Fixed-function argument 1 is packed TFACTOR; argument 2 is texture.
    if (color_operation != 3) source *= color_factor;
    if (color_operation == 6) source = min(source * 4.0, vec3(1.0));
    vec3 result = source * source;
    ALBEDO = OUTPUT_IS_SRGB ? compatibility_input(result) : decode_srgb(result);
    ALPHA = 1.0;
}
"""

var materials: Array[ShaderMaterial] = []
var _mesh: MeshInstance3D
var _clock := FrameClock.new()
var _frame := 0
var _count := 0


func configure(definition: Dictionary, scene: PackedScene, textures: Variant) -> bool:
	if not is_inside_tree() or get_viewport().transparent_bg or _mesh != null:
		return false
	if (
		not _supported(definition)
		or scene == null
		or not (textures is Texture2D or textures is Dictionary)
	):
		return false
	var model := scene.instantiate() as Node3D
	var meshes: Array[Node] = model.find_children("*", "MeshInstance3D", true, false)
	if model is MeshInstance3D:
		meshes.push_front(model)
	if meshes.size() != 1:
		model.free()
		return false
	var mesh := meshes[0] as MeshInstance3D
	if (
		mesh.mesh.get_surface_count() != definition.geometries.size()
		or mesh.mesh.get_blend_shape_count() != int(definition.frame_count) - 1
	):
		model.free()
		return false
	for player: AnimationPlayer in model.find_children("*", "AnimationPlayer", true, false):
		player.stop()
	var loaded_materials: Array[ShaderMaterial] = []
	for index: int in range(definition.geometries.size()):
		var texture: Texture2D = (
			textures
			if textures is Texture2D
			else textures.get(definition.geometries[index].texture)
		)
		if texture == null or texture.get_image() == null:
			model.free()
			return false
		var element: Dictionary = definition.recipe.elements[index]
		var shader := Shader.new()
		shader.code = additive_shader() if int(element.blending_destination) == 2 else SHADER
		var material := ShaderMaterial.new()
		material.shader = shader
		material.set_shader_parameter("source_texture", texture)
		material.set_shader_parameter("color_operation", int(element.color_operation))
		material.set_shader_parameter("color_factor", packed_factor(element.color_factor))
		loaded_materials.append(material)
		mesh.set_surface_override_material(index, material)
	if loaded_materials.size() == 1:
		mesh.material_override = loaded_materials[0]
	materials = loaded_materials
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(model)
	_mesh = mesh
	_count = int(definition.frame_count)
	var recipe: Dictionary = definition.recipe
	_clock.configure(
		_count,
		float(recipe.frame_delay),
		bool(recipe.animation_loop),
		int(recipe.animation_loop_count),
		float(recipe.start_time)
	)
	visible = _clock.snapshot().visible
	_frame = 0
	_apply_frame()
	return true


func advance(delta: float, _camera: Camera3D = null) -> Dictionary:
	if _mesh == null or not is_finite(delta) or delta <= 0 or delta > 1:
		return {"error": "Invalid mesh effect step"}
	var state: Dictionary = _clock.advance(delta)
	_frame = int(state.frame)
	visible = bool(state.visible)
	_apply_frame()
	return state


func _apply_frame() -> void:
	for index: int in range(_count - 1):
		_mesh.set_blend_shape_value(index, 1.0 if _frame == index + 1 else 0.0)


static func _supported(definition: Dictionary) -> bool:
	var recipe: Dictionary = definition.recipe
	if (
		definition.geometries.is_empty()
		or definition.geometries.size() > 32
		or recipe.elements.size() != definition.geometries.size()
	):
		return false
	if int(definition.frame_count) < 1 or int(definition.frame_count) > 256:
		return false
	for geometry: Dictionary in definition.geometries:
		if geometry.visibility.size() != int(definition.frame_count):
			return false
		for value: Variant in geometry.visibility:
			if not is_finite(float(value)):
				return false
	if not FrameClock.new().configure(
		int(definition.frame_count),
		float(recipe.frame_delay),
		bool(recipe.animation_loop),
		int(recipe.animation_loop_count),
		float(recipe.start_time)
	):
		return false
	for element: Dictionary in recipe.elements:
		if not _element_supported(element, recipe):
			return false
	return true


static func _element_supported(element: Dictionary, recipe: Dictionary) -> bool:
	return (
		_billboard_supported(element, recipe)
		and element.blending_enabled
		and int(element.blending_source) == 3
		and int(element.blending_destination) in [2, 8]
		and int(element.color_operation) in [3, 4, 6]
		and _factor_supported(element.get("color_factor"))
		and element.alpha_events.is_empty()
		and int(element.texture_start_frame) == 0
		and element.texture_animation_loop
		and float(element.texture_frame_delay) == 0.02
	)


static func additive_shader() -> String:
	return SHADER.replace("blend_mix", "blend_add")


static func _billboard_supported(element: Dictionary, recipe: Dictionary) -> bool:
	var kind := int(element.billboard_type)
	if kind == 0:
		return true
	# Source MOVE compares successive position samples. A singleton has zero
	# displacement and retains identity orientation, including under a moving actor.
	var keys: Variant = recipe.get("position_events")
	return (
		kind == 3
		and keys is Array
		and keys.size() == 1
		and keys[0] is Dictionary
		and keys[0].get("movement_type") == "MOVING_TYPE_DIRECT"
	)


static func _factor_supported(value: Variant) -> bool:
	if not value is Array or value.size() != 4:
		return false
	for component: Variant in value:
		if not component is float and not component is int:
			return false
		if not is_finite(float(component)) or float(component) < 0 or float(component) > 1:
			return false
	return float(value[3]) == 1.0


static func packed_factor(value: Array) -> Vector3:
	# D3DXCOLOR conversion rounds each channel to the nearest byte.
	return (
		Vector3(
			floorf(value[0] * 255 + 0.5), floorf(value[1] * 255 + 0.5), floorf(value[2] * 255 + 0.5)
		)
		/ 255.0
	)
