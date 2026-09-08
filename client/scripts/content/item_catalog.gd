class_name ItemCatalog
extends RefCounted
## Public item capabilities from the generated catalog; never grants gameplay state.

const MANIFEST_PATH := "res://assets/imported/content/p0-warrior-dog/manifest.v1.json"
const HANDLER := "item.recovery.pool.v1"

static var _shared: ItemCatalog

var error_message := ""
var _items: Dictionary = {}


static func item(vnum: int) -> Dictionary:
	if _shared == null:
		_shared = ItemCatalog.new()
		if not _shared.load_required():
			push_error(_shared.error_message)
	return _shared.definition(vnum)


func load_required(path := MANIFEST_PATH) -> bool:
	if not FileAccess.file_exists(path):
		return _fail("Required item catalog is missing. Rebuild the client content.")
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not document is Dictionary:
		return _fail("Required item catalog is not valid JSON.")
	return load_document(document.get("item_catalog", {}))


func load_document(document: Dictionary) -> bool:
	_items = {}
	error_message = ""
	if document.size() != 2 or document.get("schema_version") != 2:
		return _fail("Unsupported item catalog schema.")
	var rows: Variant = document.get("items")
	if not rows is Array or rows.is_empty() or rows.size() > 65535:
		return _fail("Invalid item definition list.")
	var indexed: Dictionary = {}
	var ids: Dictionary = {}
	var previous := 0
	for value: Variant in rows:
		if not value is Dictionary or not _valid_item(value):
			return _fail("Invalid item definition.")
		var vnum := int(value.vnum)
		var content_id := str(value.id)
		if vnum <= previous or ids.has(content_id):
			return _fail("Item IDs/vnums must be unique and sorted.")
		previous = vnum
		ids[content_id] = true
		indexed[vnum] = value.duplicate(true)
	_freeze(indexed)
	_items = indexed
	return true


func definition(vnum: int) -> Dictionary:
	return _items.get(vnum, {})


func _valid_item(row: Dictionary) -> bool:
	if not _integer(row.get("attack_speed_bonus"), 0, 1000):
		return false
	var fields := [
		"id",
		"revision",
		"vnum",
		"name",
		"icon",
		"height",
		"stack_limit",
		"minimum_level",
		"allowed_classes",
		"allowed_sexes",
		"attack_speed_bonus",
		"kind",
		"weapon",
		"recovery"
	]
	if row.size() != fields.size():
		return false
	for field: String in fields:
		if not row.has(field):
			return false
	if not _valid_identity(row):
		return false
	for bounds: Array in [
		["revision", 1, 65535],
		["vnum", 1, 4294967295],
		["height", 1, 9],
		["stack_limit", 1, 200],
		["minimum_level", 0, 255],
		["allowed_classes", 1, 15],
		["allowed_sexes", 1, 3]
	]:
		if not _integer(row[bounds[0]], bounds[1], bounds[2]):
			return false
	return (
		(row.kind == "weapon" and _valid_weapon(row))
		or (row.kind == "recovery" and _valid_recovery(row))
	)


func _valid_identity(row: Dictionary) -> bool:
	if not row.id is String or not row.id.begins_with("item.") or row.id.length() > 125:
		return false
	if not row.name is String or row.name.is_empty() or row.name.length() > 80:
		return false
	if not row.icon is String or not row.icon.begins_with("icon/item/"):
		return false
	var icon_number: String = row.icon.trim_prefix("icon/item/")
	if icon_number.length() < 5 or icon_number.length() > 10:
		return false
	for code in icon_number.to_ascii_buffer():
		if code < 48 or code > 57:
			return false
	return true


func _valid_weapon(row: Dictionary) -> bool:
	var weapon: Variant = row.weapon
	if not weapon is Dictionary or weapon.size() != 4 or row.recovery != null:
		return false
	if weapon.get("class") not in ["sword", "fan"] or row.stack_limit != 1:
		return false
	for key: String in ["power_min", "power_max", "refine_attack"]:
		if not _integer(weapon.get(key), 0, 65535):
			return false
	return weapon.power_min <= weapon.power_max and weapon.power_max + weapon.refine_attack <= 65535


func _valid_recovery(row: Dictionary) -> bool:
	var effect: Variant = row.recovery
	return (
		effect is Dictionary
		and effect.size() == 3
		and row.weapon == null
		and effect.get("handler") == HANDLER
		and _integer(effect.get("hp"), 0, 65535)
		and _integer(effect.get("sp"), 0, 65535)
		and effect.hp + effect.sp > 0
	)


func _integer(value: Variant, minimum: int, maximum: int) -> bool:
	return (
		(value is int or value is float)
		and is_finite(float(value))
		and float(value) == floor(float(value))
		and value >= minimum
		and value <= maximum
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


func _fail(message: String) -> bool:
	_items = {}
	error_message = message
	return false
