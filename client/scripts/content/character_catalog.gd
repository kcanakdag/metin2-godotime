class_name CharacterCatalog
extends RefCounted
## Immutable class/appearance join generated from selected original definitions.

const PATH := "res://assets/imported/characters/catalog.v1.json"

var document: Dictionary = {}
var classes: Array = []
var error_message := ""
var content_hash := ""
var _appearances: Dictionary = {}
var _classes: Dictionary = {}


func load_required() -> bool:
	if not FileAccess.file_exists(PATH):
		return _fail("Character catalog is missing. Run the character content build.")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if not parsed is Dictionary or not load_document(parsed):
		return _fail("Character catalog is invalid. " + error_message)
	content_hash = FileAccess.get_sha256(PATH)
	return true


func load_document(source: Dictionary) -> bool:
	document = {}
	classes = []
	_appearances = {}
	_classes = {}
	error_message = ""
	if source.get("schema") != "mt2spacetime.characters" or source.get("version") != 1:
		return _fail("Unsupported character catalog.")
	for key in ["classes", "actors", "artifacts"]:
		if not source.get(key) is Array:
			return _fail("Character catalog requires " + key)
	if source.classes.size() != 4 or source.actors.size() != 8 or source.artifacts.size() != 8:
		return _fail("Character catalog is incomplete.")
	for row: Variant in source.classes:
		if not _index_class(row):
			return false
	document = source.duplicate(true)
	classes = document.classes
	return true


func definition(class_id: int) -> Dictionary:
	return _classes.get(class_id, {})


func actor_id(class_id: int, sex: int) -> String:
	return str(_appearances.get(Vector2i(class_id, sex), ""))


func _index_class(value: Variant) -> bool:
	if not value is Dictionary:
		return _fail("Invalid class record.")
	var class_id := int(value.get("class_id", -1))
	if class_id < 0 or class_id > 3 or _classes.has(class_id):
		return _fail("Invalid or duplicate class ID.")
	if not value.get("initial_points") is Dictionary or not value.get("variants") is Array:
		return _fail("Class is missing progression or appearance definitions.")
	if value.variants.size() != 2:
		return _fail("Class requires both original appearances.")
	for variant: Variant in value.variants:
		if not _index_appearance(class_id, variant):
			return false
	_classes[class_id] = value.duplicate(true)
	return true


func _index_appearance(class_id: int, variant: Variant) -> bool:
	if not variant is Dictionary:
		return _fail("Invalid appearance record.")
	var sex := int(variant.get("sex", -1))
	var key := Vector2i(class_id, sex)
	var id := str(variant.get("actor_id", ""))
	if sex not in [0, 1] or _appearances.has(key) or not id.begins_with("actor.player."):
		return _fail("Invalid or duplicate appearance.")
	_appearances[key] = id
	return true


func _fail(message: String) -> bool:
	error_message = message
	return false
