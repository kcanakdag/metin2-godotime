extends RefCounted
## Optional selected ground-model package; item identity remains server-owned.

const PATH := "res://assets/imported/ground_items/catalog.v1.json"
const PREFIX := "res://assets/imported/ground_items/models/"
static var _shared: RefCounted
var error_message := ""
var _items: Dictionary = {}
var _models: Dictionary = {}
var _resources: Dictionary = {}


static func model(vnum: int) -> PackedScene:
	if _shared == null:
		_shared = load("res://scripts/content/ground_item_catalog.gd").new()
		if FileAccess.file_exists(PATH) and not _shared.load_required():
			push_error(_shared.error_message)
	return _shared.scene(vnum)


func load_required(path := PATH) -> bool:
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not document is Dictionary:
		return _fail("Invalid ground-item catalog")
	return load_document(document)


func load_document(document: Dictionary) -> bool:
	_items.clear()
	_models.clear()
	_resources.clear()
	error_message = ""
	if document.get("schema_version") != 1:
		return _fail("Unsupported ground-item catalog")
	var models: Variant = document.get("models")
	var items: Variant = document.get("items")
	if (
		not models is Dictionary
		or not items is Array
		or not 1 <= items.size()
		or items.size() > 256
	):
		return _fail("Invalid ground-item catalog tables")
	var validated: Dictionary = {}
	for key: Variant in models:
		var path := _model_path(models[key])
		if not key is String or path.is_empty():
			return _fail("Invalid ground model entry or package path")
		validated[key] = path
	var selected: Dictionary = {}
	for entry: Variant in items:
		if not _valid_item(entry, selected, validated):
			return _fail("Invalid ground item or model reference")
		selected[int(entry.vnum)] = validated[entry.model_id]
	_items = selected
	_models = validated
	return true


func _model_path(entry: Variant) -> String:
	if not entry is Dictionary:
		return ""
	var path: Variant = entry.get("path")
	if not path is String or not path.begins_with(PREFIX) or not path.ends_with(".glb"):
		return ""
	var name: String = path.trim_prefix(PREFIX)
	if name.contains("/") or name.contains("\\") or name.contains(".."):
		return ""
	return path


func _valid_item(entry: Variant, selected: Dictionary, models: Dictionary) -> bool:
	if not entry is Dictionary or not entry.get("model_id") is String:
		return false
	var value: Variant = entry.get("vnum")
	if not (value is int or value is float) or not is_finite(float(value)):
		return false
	var vnum := int(value)
	return (
		value == vnum
		and vnum > 0
		and vnum <= 0xFFFFFFFF
		and not selected.has(vnum)
		and models.has(entry.model_id)
	)


func scene(vnum: int) -> PackedScene:
	if not _items.has(vnum):
		return null
	var path: String = _items[vnum]
	if not _resources.has(path):
		var packed := load(path) as PackedScene
		if packed == null:
			_fail("Ground model could not load: " + path)
			push_error(error_message)
			return null
		_resources[path] = packed
	return _resources[path]


func _fail(message: String) -> bool:
	_items.clear()
	_models.clear()
	_resources.clear()
	error_message = message
	return false
