class_name TargetEffectCatalog
extends RefCounted
## Strict runtime reader for the bounded hover and combat-target effect catalog.

const CATALOG_PATH := "res://assets/imported/content/p2-target-effects/runtime-catalog.v1.json"
const SCHEMA := "mt2spacetime.target-effect-catalog"
const RESOURCE_ROOT := "res://assets/imported/content/p2-target-effects"
const HOVER_ID := "effect.actor.hover.v1"
const TARGET_ID := "effect.actor.target.v1"
const _ASSET_IDS := ["click_select", "click_glow_select"]
const _FILE_PATHS := [
	"models/click_glow_select.glb",
	"models/click_select.glb",
	"textures/click_glow_select_copy.png",
	"textures/click_glow_select_vertical_copy.png",
	"textures/click_select.png",
	"textures/click_select_vertical.png",
]

var loaded := false
var error_message := ""
var _document: Dictionary = {}
var _assets: Dictionary = {}
var _effects: Dictionary = {}


func load_required(path := CATALOG_PATH) -> bool:
	_clear()
	if not FileAccess.file_exists(path):
		return _fail("Required target-effect catalog is missing: %s" % path)
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK:
		return _fail("Required target-effect catalog is not valid JSON: %s" % path)
	var parsed: Variant = parser.data
	if not parsed is Dictionary:
		return _fail("Required target-effect catalog is not valid JSON: %s" % path)
	return load_document(parsed)


func load_document(document: Dictionary) -> bool:
	_clear()
	var candidate := document.duplicate(true)
	if (
		not _validate_header(candidate)
		or not _validate_files(candidate.files)
		or not _validate_playback(candidate.playback)
		or not _index_definitions(candidate)
	):
		return false
	if _assets.keys() != _ASSET_IDS or _effects.keys() != [HOVER_ID, TARGET_ID]:
		return _fail("Target-effect catalog omits or reorders its bounded definitions.")
	_freeze(candidate)
	_freeze(_assets)
	_freeze(_effects)
	_document = candidate
	loaded = true
	return true


func _index_definitions(document: Dictionary) -> bool:
	if document.assets.size() != 2 or document.effects.size() != 2:
		return _fail("Target-effect catalog must contain exactly two assets and two effects.")
	for value: Variant in document.assets:
		if not _index_asset(value):
			return false
	for value: Variant in document.effects:
		if not _index_effect(value):
			return false
	return true


func asset(id: String) -> Dictionary:
	return _assets.get(id, {})


func effect(id: String) -> Dictionary:
	return _effects.get(id, {})


func playback() -> Dictionary:
	return _document.get("playback", {})


func resource_path(relative: String) -> String:
	if not _document.get("files", {}).has(relative):
		return ""
	return RESOURCE_ROOT.path_join(relative)


func content_hash() -> String:
	return str(_document.get("content_hash", ""))


func _validate_header(document: Dictionary) -> bool:
	if not _exact_keys(
		document,
		[
			"schema",
			"schema_version",
			"resource_root",
			"content_hash",
			"files",
			"playback",
			"assets",
			"effects",
		]
	):
		return _fail("Target-effect catalog has unknown or missing top-level fields.")
	if (
		document.schema != SCHEMA
		or document.schema_version != 1
		or document.resource_root != RESOURCE_ROOT
		or not _is_sha256(document.content_hash)
	):
		return _fail("Target-effect catalog schema, root, or content hash is invalid.")
	if (
		not document.files is Dictionary
		or not document.playback is Dictionary
		or not document.assets is Array
		or not document.effects is Array
	):
		return _fail("Target-effect catalog collections have invalid types.")
	return true


func _validate_files(files: Dictionary) -> bool:
	if files.keys() != _FILE_PATHS:
		return _fail("Target-effect catalog packaged-file set or order changed.")
	for relative in _FILE_PATHS:
		var record: Variant = files[relative]
		if (
			not record is Dictionary
			or not _exact_keys(record, ["bytes", "sha256"])
			or not _bounded_integer(record.bytes, 1, 64 * 1024 * 1024)
			or not _is_sha256(record.sha256)
			or not _valid_relative_path(relative)
		):
			return _fail("Target-effect catalog has an invalid packaged-file record.")
		record.bytes = int(record.bytes)
	return true


func _validate_playback(value: Dictionary) -> bool:
	if not _exact_keys(
		value,
		[
			"frame_count",
			"frame_us",
			"loop",
			"advance_boundary",
			"max_advances_per_tick",
			"geometry_interpolation",
		]
	):
		return _fail("Target-effect playback has unknown or missing fields.")
	if (
		value.frame_count != 11
		or value.frame_us != 20_000
		or value.loop != true
		or value.advance_boundary != "strict_remaining_lt_zero"
		or value.max_advances_per_tick != 20
		or value.geometry_interpolation != "none"
	):
		return _fail("Target-effect playback contract is incompatible.")
	value.frame_count = int(value.frame_count)
	value.frame_us = int(value.frame_us)
	value.max_advances_per_tick = int(value.max_advances_per_tick)
	return true


func _index_asset(value: Variant) -> bool:
	if not value is Dictionary or not _exact_keys(value, ["id", "model", "surfaces"]):
		return _fail("Target-effect catalog has an invalid asset definition.")
	var id := str(value.id)
	var expected_index := _assets.size()
	if expected_index >= _ASSET_IDS.size() or id != _ASSET_IDS[expected_index]:
		return _fail("Target-effect asset ID is duplicate, unknown, or out of order.")
	var expected_model := "models/%s.glb" % id
	if value.model != expected_model or not value.surfaces is Array or value.surfaces.size() != 2:
		return _fail("Target-effect asset model or surface count is invalid.")
	for surface_index in 2:
		if not _validate_surface(id, surface_index, value.surfaces[surface_index]):
			return false
	_assets[id] = value
	return true


func _validate_surface(asset_id: String, index: int, value: Variant) -> bool:
	if (
		not value is Dictionary
		or not _exact_keys(
			value,
			[
				"index",
				"geometry",
				"texture",
				"tint_srgba8",
				"blend",
				"unshaded",
				"cull_disabled",
				"depth_draw",
				"depth_test",
				"texture_repeat",
				"frame_alpha_u8",
			]
		)
	):
		return _fail("Target-effect asset has an invalid surface definition.")
	var expected_geometry := "Cylinder01" if index == 0 else "Plane01"
	var expected_blend := (
		"source_alpha_inverse_source_alpha" if asset_id == "click_select" else "source_alpha_one"
	)
	if (
		value.index != index
		or value.geometry != expected_geometry
		or value.blend != expected_blend
		or value.unshaded != true
		or value.cull_disabled != true
		or value.depth_draw != false
		or value.depth_test != true
		or value.texture_repeat != true
		or not _valid_texture_for(asset_id, index, value.texture)
		or not _u8_equals(value.tint_srgba8, [255, 14, 0, 255])
		or not _u8_vector(value.frame_alpha_u8, 11)
	):
		return _fail("Target-effect surface material or frame values are invalid.")
	value.index = int(value.index)
	for component_index in value.tint_srgba8.size():
		value.tint_srgba8[component_index] = int(value.tint_srgba8[component_index])
	for frame_index in value.frame_alpha_u8.size():
		value.frame_alpha_u8[frame_index] = int(value.frame_alpha_u8[frame_index])
	return true


func _valid_texture_for(asset_id: String, index: int, value: Variant) -> bool:
	var suffix := "_vertical" if index == 0 else ""
	var copy := "_copy" if asset_id == "click_glow_select" else ""
	return value == "textures/%s%s%s.png" % [asset_id, suffix, copy]


func _index_effect(value: Variant) -> bool:
	if (
		not value is Dictionary
		or not _exact_keys(value, ["id", "attachment_space", "runtime_offset_m", "layers"])
	):
		return _fail("Target-effect catalog has an invalid effect definition.")
	var expected_id := HOVER_ID if _effects.is_empty() else TARGET_ID
	var expected_layers := ["click_select"] if expected_id == HOVER_ID else _ASSET_IDS
	if (
		value.id != expected_id
		or _effects.has(str(value.id))
		or value.attachment_space != "actor_local"
		or not _zero_vector(value.runtime_offset_m)
		or value.layers != expected_layers
	):
		return _fail("Target-effect ID, attachment, or layers are incompatible.")
	_effects[expected_id] = value
	return true


func _exact_keys(value: Dictionary, expected: Array) -> bool:
	if value.size() != expected.size():
		return false
	for key: Variant in expected:
		if not value.has(key):
			return false
	return true


func _valid_relative_path(value: String) -> bool:
	return (
		not value.is_empty()
		and not value.is_absolute_path()
		and not "://" in value
		and not ".." in value.split("/", false)
	)


func _u8_vector(value: Variant, count: int) -> bool:
	if not value is Array or value.size() != count:
		return false
	for component: Variant in value:
		if not _bounded_integer(component, 0, 255):
			return false
	return true


func _u8_equals(value: Variant, expected: Array) -> bool:
	if not _u8_vector(value, expected.size()):
		return false
	for index in expected.size():
		if int(value[index]) != expected[index]:
			return false
	return true


func _finite_vector(value: Variant) -> bool:
	if not value is Array or value.size() != 3:
		return false
	for component: Variant in value:
		if (not component is int and not component is float) or not is_finite(float(component)):
			return false
	return true


func _zero_vector(value: Variant) -> bool:
	if not _finite_vector(value):
		return false
	return float(value[0]) == 0.0 and float(value[1]) == 0.0 and float(value[2]) == 0.0


func _bounded_integer(value: Variant, minimum: int, maximum: int) -> bool:
	if not value is int and not value is float:
		return false
	var number := float(value)
	return is_finite(number) and number == floor(number) and number >= minimum and number <= maximum


func _is_sha256(value: Variant) -> bool:
	return (
		value is String
		and value.length() == 64
		and value == value.to_lower()
		and value.is_valid_hex_number(false)
	)


func _freeze(value: Variant) -> void:
	if value is Dictionary:
		for child: Variant in value.values():
			_freeze(child)
		value.make_read_only()
	elif value is Array:
		for child: Variant in value:
			_freeze(child)
		value.make_read_only()


func _clear() -> void:
	loaded = false
	error_message = ""
	_document = {}
	_assets = {}
	_effects = {}


func _fail(message: String) -> bool:
	loaded = false
	_document = {}
	_assets = {}
	_effects = {}
	error_message = message
	return false
