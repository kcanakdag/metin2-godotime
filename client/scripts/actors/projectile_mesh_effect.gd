extends Node3D
## Selected opaque arrow material: source-color / inverse-destination-alpha.
## The adaptation requires destination alpha 1; transparent viewports reject.

const SHADER := """shader_type spatial;
render_mode blend_mix, unshaded, cull_disabled, depth_draw_never;
// Intentionally sample encoded RGB: original fixed-function blending squares it.
uniform sampler2D source_texture : repeat_enable, filter_linear;
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
    vec3 result = source * source;
    ALBEDO = OUTPUT_IS_SRGB ? compatibility_input(result) : decode_srgb(result);
    ALPHA = 1.0;
}
"""

var _mesh: MeshInstance3D
var _remaining := 0.02
var _frame := 0
var _count := 0


func configure(definition: Dictionary, scene: PackedScene, texture: Texture2D) -> bool:
	if not is_inside_tree() or get_viewport().transparent_bg or _mesh != null:
		return false
	if not _supported(definition) or scene == null or texture == null:
		return false
	var image := texture.get_image()
	if image == null or image.detect_alpha() != Image.ALPHA_NONE:
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
		mesh.mesh.get_surface_count() != 1
		or mesh.mesh.get_blend_shape_count() != int(definition.frame_count) - 1
	):
		model.free()
		return false
	for player: AnimationPlayer in model.find_children("*", "AnimationPlayer", true, false):
		player.stop()
	var shader := Shader.new()
	shader.code = SHADER
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("source_texture", texture)
	mesh.material_override = material
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(model)
	_mesh = mesh
	_count = int(definition.frame_count)
	_remaining = 0.02
	_frame = 0
	_apply_frame()
	return true


func advance(delta: float, _camera: Camera3D = null) -> Dictionary:
	if _mesh == null or not is_finite(delta) or delta <= 0 or delta > 1:
		return {"error": "Invalid mesh effect step"}
	_remaining -= delta
	# Original FrameController limits catch-up to 20 frames per update.
	for unused: int in range(20):
		if _remaining >= 0:
			break
		_remaining += 0.02
		_frame = (_frame + 1) % _count
	_apply_frame()
	return {"frame": _frame, "finished": false}


func _apply_frame() -> void:
	for index: int in range(_count - 1):
		_mesh.set_blend_shape_value(index, 1.0 if _frame == index + 1 else 0.0)


static func _supported(definition: Dictionary) -> bool:
	var recipe: Dictionary = definition.recipe
	if definition.geometries.size() != 1 or recipe.elements.size() != 1:
		return false
	var element: Dictionary = recipe.elements[0]
	if int(definition.frame_count) < 1 or int(definition.frame_count) > 256:
		return false
	if definition.geometries[0].visibility.size() != int(definition.frame_count):
		return false
	for value: Variant in definition.geometries[0].visibility:
		if float(value) != 1.0:
			return false
	return (
		float(recipe.start_time) == 0
		and recipe.animation_loop
		and int(recipe.animation_loop_count) == 0
		and float(recipe.frame_delay) == 0.02
		and int(element.billboard_type) == 0
		and element.blending_enabled
		and int(element.blending_source) == 3
		and int(element.blending_destination) == 8
		and int(element.color_operation) == 4
		and element.color_factor == [1.0, 1.0, 1.0, 1.0]
		and element.alpha_events.is_empty()
		and int(element.texture_start_frame) == 0
		and element.texture_animation_loop
		and float(element.texture_frame_delay) == 0.02
	)
