extends SceneTree

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

var _manifest_dir := ""
var _material_tracks: Array[Dictionary] = []
var _animation_players: Array[AnimationPlayer] = []
var _geometry_checks: Array[Dictionary] = []
var _camera: Camera3D


func _initialize() -> void:
	call_deferred("_run")


func _read_json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		push_error("Invalid JSON: %s" % path)
		quit(2)
		return {}
	return parsed


func _children_of_type(node: Node, type_name: StringName) -> Array[Node]:
	var result: Array[Node] = []
	for child in node.get_children():
		if child.is_class(type_name):
			result.append(child)
		result.append_array(_children_of_type(child, type_name))
	return result


func _make_material(entry: Dictionary) -> ShaderMaterial:
	var mode := "blend_mix" if entry["godot_material"]["blend"] == "blend_mix" else "blend_add"
	var shader := Shader.new()
	shader.code = SHADER_TEMPLATE % mode
	var material := ShaderMaterial.new()
	material.shader = shader
	var texture_path := _manifest_dir.path_join(entry["texture"])
	var texture: Texture2D = load(texture_path)
	if texture == null:
		push_error("Could not load target-effect texture: %s" % texture_path)
		quit(2)
		return material
	material.set_shader_parameter("source_texture", texture)
	var tint: Array = entry["source_texture_factor_srgba8"]
	material.set_shader_parameter(
		"source_tint", Color8(int(tint[0]), int(tint[1]), int(tint[2]), int(tint[3]))
	)
	_material_tracks.append({"material": material, "alpha": entry["frame_alpha"]})
	return material


func _vector3_array(value: Vector3) -> Array[float]:
	return [value.x, value.y, value.z]


func _transform_report(value: Transform3D) -> Dictionary:
	return {
		"basis_x": _vector3_array(value.basis.x),
		"basis_y": _vector3_array(value.basis.y),
		"basis_z": _vector3_array(value.basis.z),
		"origin": _vector3_array(value.origin),
	}


func _aabb_report(value: AABB) -> Dictionary:
	return {"position": _vector3_array(value.position), "size": _vector3_array(value.size)}


func _global_aabb(mesh_instance: MeshInstance3D) -> AABB:
	var local := mesh_instance.get_aabb()
	var first := mesh_instance.global_transform * local.get_endpoint(0)
	var minimum := first
	var maximum := first
	for endpoint in range(1, 8):
		var point := mesh_instance.global_transform * local.get_endpoint(endpoint)
		minimum = minimum.min(point)
		maximum = maximum.max(point)
	return AABB(minimum, maximum - minimum)


func _add_layer(
	effect_root: Node3D, effect_id: String, layer_index: int, layer: Dictionary
) -> void:
	var model_path := _manifest_dir.path_join(layer["model"])
	var packed: PackedScene = load(model_path)
	if packed == null:
		push_error("Could not load target-effect GLB: %s" % model_path)
		quit(2)
		return
	var instance := packed.instantiate()
	effect_root.add_child(instance)
	var sidecar: Dictionary = _read_json(_manifest_dir.path_join(layer["material_sidecar"]))
	var meshes := _children_of_type(instance, &"MeshInstance3D")
	if meshes.size() != 1:
		push_error("Expected one merged MeshInstance3D in %s" % model_path)
		quit(2)
		return
	var mesh_instance := meshes[0] as MeshInstance3D
	if mesh_instance.mesh.get_surface_count() != sidecar["materials"].size():
		push_error("Material sidecar surface count mismatch: %s" % model_path)
		quit(2)
		return
	for surface in sidecar["materials"].size():
		mesh_instance.set_surface_override_material(
			surface, _make_material(sidecar["materials"][surface])
		)
	(
		_geometry_checks
		. append(
			{
				"effect_id": effect_id,
				"layer_index": layer_index,
				"model": layer["model"],
				"imported_mesh_local_transform": _transform_report(mesh_instance.transform),
				"preview_mesh_global_transform": _transform_report(mesh_instance.global_transform),
				"mesh_local_aabb": _aabb_report(mesh_instance.get_aabb()),
				"preview_mesh_global_aabb": _aabb_report(_global_aabb(mesh_instance)),
			}
		)
	)
	for player_node in _children_of_type(instance, &"AnimationPlayer"):
		var player := player_node as AnimationPlayer
		var animation_names := player.get_animation_list()
		if animation_names.is_empty():
			continue
		var animation_name := animation_names[0]
		for candidate in animation_names:
			if "loop" in String(candidate).to_lower():
				animation_name = candidate
				break
		player.play(animation_name)
		player.pause()
		_animation_players.append(player)


func _add_effect(effect: Dictionary, position: Vector3) -> void:
	var effect_root := Node3D.new()
	effect_root.name = effect["effect_id"]
	effect_root.position = position
	get_root().add_child(effect_root)
	for layer_index in effect["layers"].size():
		_add_layer(effect_root, effect["effect_id"], layer_index, effect["layers"][layer_index])


func _set_frame(frame: int) -> void:
	var time := float(frame) * 0.02
	for player in _animation_players:
		player.seek(time, true)
		player.advance(0.0)
	for track in _material_tracks:
		var alpha_entry: Dictionary = track["alpha"][frame]
		(track["material"] as ShaderMaterial).set_shader_parameter(
			"frame_alpha", float(alpha_entry["effective"])
		)


func _camera_and_ground() -> void:
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color("18202a")
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color.WHITE
	settings.ambient_light_energy = 0.5
	environment.environment = settings
	get_root().add_child(environment)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(6.0, 4.0)
	ground.mesh = plane
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("263240")
	material.roughness = 1.0
	ground.material_override = material
	get_root().add_child(ground)
	_camera = Camera3D.new()
	_camera.position = Vector3(0.0, 4.1, 4.4)
	_camera.look_at_from_position(_camera.position, Vector3(0.0, 0.35, 0.0), Vector3.UP)
	_camera.fov = 38.0
	get_root().add_child(_camera)
	_camera.current = true


func _render_frame(frame: int, output: String, label: String) -> Dictionary:
	_set_frame(frame)
	for unused in 4:
		await process_frame
	var image := get_root().get_texture().get_image()
	var path := output.path_join("target-effects-%s.png" % label)
	var error := image.save_png(path)
	if error != OK:
		push_error("Could not save target-effect preview: %s" % path)
		quit(2)
		return {}
	return {
		"frame": frame,
		"time_us": frame * 20_000,
		"path": path,
		"width": image.get_width(),
		"height": image.get_height(),
		"sha256": FileAccess.get_sha256(path),
	}


func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 2:
		push_error("Usage: render_target_effects.gd -- MANIFEST OUTPUT")
		quit(2)
		return
	var manifest_path: String = arguments[0]
	var output: String = arguments[1]
	DirAccess.make_dir_recursive_absolute(output)
	_manifest_dir = "res://"
	var manifest := _read_json(manifest_path)
	_camera_and_ground()
	for effect in manifest["effects"]:
		var x := -1.35 if effect["effect_id"] == "effect.actor.hover.v1" else 1.35
		_add_effect(effect, Vector3(x, 0.0, 0.0))
	var captures: Array[Dictionary] = []
	var render_available := DisplayServer.get_name() != "headless"
	if render_available:
		for frame in [0, 5, 10]:
			captures.append(await _render_frame(frame, output, "frame%02d" % frame))
		_camera.position = Vector3(0.0, 6.0, 0.01)
		_camera.look_at_from_position(_camera.position, Vector3(0.0, 0.4, 0.0), Vector3.FORWARD)
		var grounding_capture := await _render_frame(0, output, "grounding-top")
		grounding_capture["view"] = "top_down_grounding"
		captures.append(grounding_capture)
	var report := {
		"status": "rendered" if render_available else "geometry_checked_headless",
		"engine": Engine.get_version_info().get("string", "unknown"),
		"renderer": RenderingServer.get_video_adapter_name(),
		"display_server": DisplayServer.get_name(),
		"imported_geometry": _geometry_checks,
		"captures": captures,
		"layout":
		{
			"left": "effect.actor.hover.v1 (one alpha-blended layer)",
			"right": "effect.actor.target.v1 (alpha base plus additive glow)",
		},
		"claim_limit": "Isolated Godot render; original-client visual parity is not established.",
	}
	var file := FileAccess.open(output.path_join("report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  ") + "\n")
	file.close()
	quit()
