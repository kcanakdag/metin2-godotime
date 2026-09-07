# gdlint: disable=max-returns
extends SceneTree
## Qualify the two target-effect models and four lossless textures from an actual PCK.

const RESOURCE_ROOT := "res://assets/imported/content/p2-target-effects"

var failures: Array[String] = []
var report_path := ""


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("Target-effect PCK audit requires expected and report paths")
		quit(1)
		return
	report_path = args[1]
	_write_report({"passed": false, "status": "started"})
	var expected_value: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not expected_value is Dictionary:
		_fail("Target-effect PCK expectations are not valid JSON")
		_finish({})
		return
	var expected := expected_value as Dictionary
	if (
		expected.get("schema") != "mt2spacetime.target-effect-pack-expectations"
		or expected.get("schema_version") != 1
		or not expected.get("models") is Array
		or not expected.get("textures") is Array
	):
		_fail("Target-effect PCK expectations have an incompatible schema")
		_finish({})
		return
	var catalog_path := str(expected.get("catalog_path", ""))
	var catalog_bytes := FileAccess.get_file_as_bytes(catalog_path)
	var catalog: Variant = JSON.parse_string(catalog_bytes.get_string_from_utf8())
	if (
		catalog_bytes.is_empty()
		or _sha256(catalog_bytes) != expected.get("catalog_sha256")
		or not catalog is Dictionary
		or catalog.get("content_hash") != expected.get("catalog_content_hash")
	):
		_fail("Packaged target-effect catalog differs from the staged catalog")
	var loader_script := load("res://scripts/content/target_effect_catalog.gd") as GDScript
	if loader_script == null:
		_fail("Packaged target-effect runtime catalog loader could not load")
	else:
		var runtime_catalog: RefCounted = loader_script.new()
		if not runtime_catalog.call("load_required", catalog_path):
			_fail(
				(
					"Packaged target-effect runtime catalog rejected its catalog: "
					+ str(runtime_catalog.get("error_message"))
				)
			)

	var model_results: Array[Dictionary] = []
	for model_value: Variant in expected.models:
		if not model_value is Dictionary:
			_fail("Target-effect model expectation is invalid")
			continue
		var result := _audit_model(model_value)
		if not result.is_empty():
			model_results.append(result)

	var texture_results: Array[Dictionary] = []
	for texture_value: Variant in expected.textures:
		if not texture_value is Dictionary:
			_fail("Target-effect texture expectation is invalid")
			continue
		var result := _audit_texture(texture_value)
		if not result.is_empty():
			texture_results.append(result)

	var derived := _audit_derived_images(expected.textures)
	_finish(
		{
			"catalog_sha256": str(expected.get("catalog_sha256", "")),
			"catalog_content_hash": str(expected.get("catalog_content_hash", "")),
			"models": model_results,
			"textures": texture_results,
			"engine_extracted_texture_resources": derived,
		}
	)


func _audit_model(expected: Dictionary) -> Dictionary:
	var path := str(expected.get("path", ""))
	if not path.begins_with(RESOURCE_ROOT + "/models/") or not path.ends_with(".glb"):
		_fail("Target-effect model path is outside the fixed resource root")
		return {}
	var packed := load(path) as PackedScene
	if packed == null:
		_fail("Packaged target-effect model could not load: " + path)
		return {}
	var instance := packed.instantiate()
	get_root().add_child(instance)
	var meshes := _children_of_type(instance, &"MeshInstance3D")
	var players := _children_of_type(instance, &"AnimationPlayer")
	if meshes.size() != 1 or players.size() != 1:
		_fail("Packaged target-effect model node structure changed: " + path)
		instance.free()
		return {}
	var mesh_instance := meshes[0] as MeshInstance3D
	var mesh := mesh_instance.mesh
	if (
		mesh == null
		or mesh.get_surface_count() != int(expected.get("surface_count", -1))
		or mesh.get_blend_shape_count() != int(expected.get("blend_shape_count", -1))
	):
		_fail("Packaged target-effect mesh surface or blend-shape count changed: " + path)
		instance.free()
		return {}
	var player := players[0] as AnimationPlayer
	var animation_name := _loop_animation(player)
	if animation_name.is_empty():
		_fail("Packaged target-effect model has no loop animation: " + path)
		instance.free()
		return {}
	var animation := player.get_animation(animation_name)
	if not _validate_animation(animation, expected, path):
		instance.free()
		return {}
	player.play(animation_name)
	player.pause()
	var frame_count := int(expected.get("frame_count", -1))
	for frame in frame_count:
		player.seek(float(frame) * 0.02, true)
		player.advance(0.0)
		for blend_shape in mesh.get_blend_shape_count():
			var wanted := 1.0 if frame == blend_shape + 1 else 0.0
			if not is_equal_approx(mesh_instance.get_blend_shape_value(blend_shape), wanted):
				_fail(
					(
						"Packaged target-effect frame %d has wrong Frame_%02d weight: %s"
						% [frame, blend_shape + 1, path]
					)
				)
				instance.free()
				return {}
	var result := {
		"path": path,
		"surfaces": mesh.get_surface_count(),
		"blend_shapes": mesh.get_blend_shape_count(),
		"animation": str(animation_name),
		"animation_length": animation.length,
		"tracks": animation.get_track_count(),
		"frames_verified": frame_count,
	}
	instance.free()
	return result


func _validate_animation(animation: Animation, expected: Dictionary, path: String) -> bool:
	if (
		animation == null
		or not is_equal_approx(animation.length, float(expected.get("animation_length", -1.0)))
		or animation.loop_mode == Animation.LOOP_NONE
		or animation.get_track_count() != int(expected.get("track_count", -1))
	):
		_fail("Packaged target-effect animation length, loop, or track count changed: " + path)
		return false
	var names: Dictionary = {}
	var boundaries: Dictionary = {}
	for track in animation.get_track_count():
		var track_path := String(animation.track_get_path(track))
		var name := track_path.get_slice(":", track_path.get_slice_count(":") - 1)
		if (
			animation.track_get_type(track) != Animation.TYPE_BLEND_SHAPE
			or animation.track_get_interpolation_type(track) != Animation.INTERPOLATION_NEAREST
			or not name.begins_with("Frame_")
			or name in names
		):
			_fail(
				"Packaged target-effect animation is not ten unique nearest blend tracks: " + path
			)
			return false
		names[name] = true
		for key in animation.track_get_key_count(track):
			var key_time := animation.track_get_key_time(track, key)
			var frame := roundi(key_time / 0.02)
			if frame < 0 or frame > 11 or not is_equal_approx(key_time, frame * 0.02):
				_fail("Packaged target-effect animation has an unexpected key boundary: " + path)
				return false
			boundaries[frame] = true
	for index in 10:
		if not names.has("Frame_%02d" % (index + 1)):
			_fail("Packaged target-effect animation is missing a named blend track: " + path)
			return false
	for boundary in 12:
		if not boundaries.has(boundary):
			_fail("Packaged target-effect animation omits a source frame boundary: " + path)
			return false
	return true


func _audit_texture(expected: Dictionary) -> Dictionary:
	var path := str(expected.get("path", ""))
	if not path.begins_with(RESOURCE_ROOT + "/textures/") or not path.ends_with(".png"):
		_fail("Target-effect texture path is outside the fixed resource root")
		return {}
	var texture := load(path) as Texture2D
	if texture == null:
		_fail("Packaged target-effect texture could not load: " + path)
		return {}
	var image := texture.get_image()
	if image == null or image.is_compressed() or image.has_mipmaps():
		_fail("Packaged target-effect texture is not lossless RGBA without mipmaps: " + path)
		return {}
	image.convert(Image.FORMAT_RGBA8)
	var rgba_sha256 := _sha256(image.get_data())
	if (
		image.get_width() != int(expected.get("width", -1))
		or image.get_height() != int(expected.get("height", -1))
		or rgba_sha256 != expected.get("rgba_sha256")
	):
		_fail("Packaged target-effect decoded pixels differ from the staged PNG: " + path)
		return {}
	return {
		"path": path,
		"width": image.get_width(),
		"height": image.get_height(),
		"rgba_sha256": rgba_sha256,
	}


func _audit_derived_images(texture_expectations: Array) -> Array[Dictionary]:
	var by_name: Dictionary = {}
	for value: Variant in texture_expectations:
		if value is Dictionary:
			by_name[str(value.path).get_file()] = value
	var result: Array[Dictionary] = []
	var directory := DirAccess.open(RESOURCE_ROOT + "/models")
	if directory == null:
		_fail("Cannot inspect target-effect model directory in exported PCK")
		return result
	directory.list_dir_begin()
	var name := directory.get_next()
	while not name.is_empty():
		var logical_name := name.trim_suffix(".import")
		if not directory.current_is_dir() and logical_name.ends_with(".png"):
			var matched := ""
			for source_name: String in by_name:
				if logical_name.ends_with("_" + source_name):
					matched = source_name
					break
			if matched.is_empty():
				_fail("Unknown engine-extracted target-effect texture in PCK: " + logical_name)
			else:
				var expected: Dictionary = by_name[matched]
				var derived_expected := expected.duplicate()
				derived_expected.path = RESOURCE_ROOT + "/models/" + logical_name
				var audited := _audit_texture_any_root(derived_expected)
				if not audited.is_empty():
					audited["derived_from"] = str(expected.path)
					result.append(audited)
		name = directory.get_next()
	directory.list_dir_end()
	result.sort_custom(
		func(left: Dictionary, right: Dictionary) -> bool: return left.path < right.path
	)
	return result


func _audit_texture_any_root(expected: Dictionary) -> Dictionary:
	var path := str(expected.path)
	var texture := load(path) as Texture2D
	if texture == null:
		_fail("Engine-extracted target-effect texture could not load: " + path)
		return {}
	var image := texture.get_image()
	if image == null or image.is_compressed() or image.has_mipmaps():
		_fail("Engine-extracted target-effect texture is not lossless: " + path)
		return {}
	image.convert(Image.FORMAT_RGBA8)
	var rgba_sha256 := _sha256(image.get_data())
	if (
		image.get_width() != int(expected.width)
		or image.get_height() != int(expected.height)
		or rgba_sha256 != expected.rgba_sha256
	):
		_fail("Engine-extracted target-effect pixels differ from their source: " + path)
		return {}
	return {
		"path": path,
		"width": image.get_width(),
		"height": image.get_height(),
		"rgba_sha256": rgba_sha256,
	}


func _loop_animation(player: AnimationPlayer) -> StringName:
	for name in player.get_animation_list():
		if "loop" in String(name).to_lower():
			return name
	return &""


func _children_of_type(node: Node, type_name: StringName) -> Array[Node]:
	var result: Array[Node] = []
	for child in node.get_children():
		if child.is_class(type_name):
			result.append(child)
		result.append_array(_children_of_type(child, type_name))
	return result


func _sha256(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()


func _fail(message: String) -> void:
	failures.append(message)


func _write_report(value: Dictionary) -> void:
	var report := FileAccess.open(report_path, FileAccess.WRITE)
	if report == null:
		push_error("Could not write target-effect PCK audit report")
		return
	report.store_string(JSON.stringify(value, "  ") + "\n")
	report.close()


func _finish(result: Dictionary) -> void:
	if not failures.is_empty():
		result["passed"] = false
		result["failures"] = failures
		_write_report(result)
		for failure in failures:
			push_error(failure)
		quit(1)
		return
	result["passed"] = true
	result["godot_version"] = Engine.get_version_info().get("string", "")
	_write_report(result)
	print("TARGET_EFFECT_PACK_AUDIT " + JSON.stringify(result))
	quit(0)
