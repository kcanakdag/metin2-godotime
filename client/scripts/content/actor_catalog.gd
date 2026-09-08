class_name ActorCatalog
extends RefCounted
## Strict reader for one generated actor presentation profile.

const MANIFEST_PATH := "res://assets/imported/content/p0-warrior-dog/manifest.v1.json"
const SCHEMA := "mt2spacetime.presentation-manifest"
const PROFILE_ID := "p0-warrior-dog"
const WARRIOR_ID := "actor.player.warrior-male"
const WILD_DOG_ID := "actor.mob.wild-dog-101"
const SWORD_ID := "item.weapon.sword-10"
const SWORD_POWER_MIN := 13
const SWORD_POWER_MAX := 15
const SWORD_REFINE_ATTACK := 0
const AUTHORED_PATH := "res://assets/imported/authored/training-dummy/manifest.v1.json"
const CharacterCatalogScript := preload("res://scripts/content/character_catalog.gd")

var manifest: Dictionary = {}
var error_message := ""
var report_errors := true
var training_target_hash := ""
var characters := CharacterCatalogScript.new()
var skills := SkillCatalog.new()
var _actors: Dictionary = {}
var _items: Dictionary = {}
var _items_by_vnum: Dictionary = {}
var _artifacts: Dictionary = {}
var _modes_by_actor: Dictionary = {}
var _motions_by_action_id: Dictionary = {}
var _motions_by_action: Dictionary = {}


func load_required(path := MANIFEST_PATH, intro_models := false) -> bool:
	if not FileAccess.file_exists(path):
		return _fail("Required actor profile is missing: %s. Run the P1 content build." % path)
	var document: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not document is Dictionary:
		return _fail("Required actor profile is not valid JSON: " + path)
	if not skills.load_required():
		return _fail(skills.error_message)
	if not characters.load_required():
		return _fail(characters.error_message)
	var authored: Dictionary = {}
	if FileAccess.file_exists(AUTHORED_PATH):
		var extra: Variant = JSON.parse_string(FileAccess.get_file_as_string(AUTHORED_PATH))
		if not extra is Dictionary or extra.get("schema_version") != 1:
			return _fail("Invalid authored actor manifest")
		authored = extra
	return load_document(document, characters.document, intro_models, authored)


func load_document(
	document: Dictionary,
	character_document: Dictionary = {},
	intro_models := false,
	authored: Dictionary = {}
) -> bool:
	_clear()
	var indexed_document: Dictionary = document.duplicate(true)
	if not _validate_header(indexed_document):
		return false
	var artifacts: Array = indexed_document.get("artifacts")
	var actors: Array = indexed_document.get("actors")
	var items: Array = indexed_document.get("items")
	for value: Variant in artifacts:
		if intro_models and value is Dictionary and value.get("id") == WARRIOR_ID:
			continue
		if not _index_artifact(value):
			return false
	for value: Variant in actors:
		if intro_models and value is Dictionary and value.get("id") == WARRIOR_ID:
			continue
		if not _index_actor(value):
			return false
	for value: Variant in items:
		if not _index_item(value):
			return false
	if (
		not _index_characters(character_document, intro_models)
		or not _validate_required_slice()
		or not _index_authored(authored)
	):
		return false
	_freeze_variant(indexed_document)
	_freeze_variant(_actors)
	_freeze_variant(_items)
	_freeze_variant(_items_by_vnum)
	_freeze_variant(_artifacts)
	_freeze_variant(_modes_by_actor)
	_freeze_variant(_motions_by_action_id)
	_freeze_variant(_motions_by_action)
	manifest = indexed_document
	return true


func _index_authored(document: Dictionary) -> bool:
	if document.is_empty():
		return true
	if not _is_sha256(document.get("definition_hash")):
		return _fail("Authored actor manifest has no definition hash")
	training_target_hash = document.definition_hash
	return _index_characters(document, false)


func _index_characters(document: Dictionary, intro_models: bool) -> bool:
	for value: Variant in document.get("artifacts", []):
		if not intro_models and value is Dictionary and value.get("id") == WARRIOR_ID:
			continue
		if not value is Dictionary or not _index_artifact(value.duplicate(true)):
			return false
	for value: Variant in document.get("actors", []):
		if not intro_models and value is Dictionary and value.get("id") == WARRIOR_ID:
			continue
		if not value is Dictionary or not _index_actor(value.duplicate(true)):
			return false
	return true


func _validate_header(document: Dictionary) -> bool:
	if (
		document.get("schema") != SCHEMA
		or document.get("schema_version") != 1
		or document.get("profile_id") != PROFILE_ID
	):
		return _fail("Actor profile schema, version, or profile ID is incompatible.")
	for key in ["content_hash", "gameplay_definition_hash", "presentation_output_hash"]:
		if not _is_sha256(document.get(key)):
			return _fail("Actor profile has an invalid %s." % key)
	if not document.get("coordinates") is Dictionary:
		return _fail("Actor profile has no coordinate contract.")
	var artifacts: Variant = document.get("artifacts")
	var actors: Variant = document.get("actors")
	var items: Variant = document.get("items")
	if not artifacts is Array or not actors is Array or not items is Array:
		return _fail("Actor profile artifacts, actors, and items must be arrays.")
	var item_catalog := ItemCatalog.new()
	if not item_catalog.load_document(document.get("item_catalog", {})):
		return _fail(item_catalog.error_message)
	return true


func _validate_required_slice() -> bool:
	if not _actors.has(WARRIOR_ID) or not _actors.has(WILD_DOG_ID) or not _items.has(SWORD_ID):
		return _fail("Actor profile omits the required Warrior, Wild Dog, or Sword+0.")
	var warrior: Dictionary = _actors[WARRIOR_ID]
	var dog: Dictionary = _actors[WILD_DOG_ID]
	var sword: Dictionary = _items[SWORD_ID]
	if (
		int(warrior.get("race_id", -1)) != 0
		or int(dog.get("vnum", -1)) != 101
		or int(sword.get("vnum", -1)) != 10
	):
		return _fail("The P1 Warrior, Wild Dog, or Sword+0 has an incompatible numeric ID.")
	if str(warrior.get("attachment_bones", {}).get("weapon_right", "")) != "equip_right_hand":
		return _fail("The P1 Warrior must declare weapon_right as equip_right_hand.")
	if int(warrior.get("default_hair_index", -1)) != 0:
		return _fail("The selected Warrior must include original default HairIndex 0.")
	for required: Array in [
		[WARRIOR_ID, "general", "normal_attack"],
		[WARRIOR_ID, "onehand", "combo_1"],
		[WILD_DOG_ID, "general", "normal_attack"],
	]:
		if not _require_action(required[0], required[1], required[2]):
			return false
	return true


func validate_world(info: Dictionary) -> bool:
	if manifest.is_empty():
		return _fail("The required actor profile has not loaded.")
	if (
		(
			not skills.content_hash.is_empty()
			and str(info.get("skill_catalog_hash", "")) != skills.content_hash
		)
		or str(info.get("training_target_hash", "")) != training_target_hash
	):
		return _fail(
			"Server and client skill or training catalogs differ. Rebuild and republish together."
		)
	if str(info.get("definition_profile", "")) != PROFILE_ID:
		return _fail("Server and client actor profiles differ. Rebuild the client content.")
	if str(info.get("definition_hash", "")) != gameplay_definition_hash():
		return _fail("Server and client action definitions differ. Rebuild and republish together.")
	if (
		not characters.content_hash.is_empty()
		and str(info.get("character_catalog_hash", "")) != characters.content_hash
	):
		return _fail("Server and client character catalogs differ. Rebuild and republish together.")
	return true


func gameplay_definition_hash() -> String:
	return str(manifest.get("gameplay_definition_hash", ""))


func actor(id: String) -> Dictionary:
	return _actors.get(id, {})


func actor_bounds(id: String) -> Dictionary:
	var definition: Dictionary = actor(id)
	var artifact_id := str(definition.get("model", {}).get("artifact_id", ""))
	var artifact: Dictionary = _artifacts.get(artifact_id, {})
	var source: Variant = artifact.get("bounds_m")
	if not source is Array or source.size() != 2:
		return {}
	var minimum: Variant = _finite_vector(source[0])
	var maximum: Variant = _finite_vector(source[1])
	if minimum == null or maximum == null:
		return {}
	var result_minimum: Vector3 = minimum
	var result_maximum: Vector3 = maximum
	if (
		result_maximum.x <= result_minimum.x
		or result_maximum.y <= result_minimum.y
		or result_maximum.z <= result_minimum.z
	):
		return {}
	return {"minimum": result_minimum, "maximum": result_maximum}


func item(id: String) -> Dictionary:
	return _items.get(id, {})


func item_for_vnum(vnum: int) -> Dictionary:
	return _items_by_vnum.get(vnum, {})


func player_actor_id(appearance: Dictionary) -> String:
	if not characters.document.is_empty():
		return characters.actor_id(
			int(appearance.get("character_class", -1)), int(appearance.get("sex", -1))
		)
	if int(appearance.get("character_class", -1)) == 0 and int(appearance.get("sex", -1)) == 0:
		return WARRIOR_ID
	return ""


func mode_for_weapon(actor_id: String, weapon_vnum: int) -> String:
	for mode: Dictionary in _modes_by_actor.get(actor_id, {}).values():
		var required: Array = mode.get("required_item_vnums", [])
		if required.is_empty() and weapon_vnum == 0:
			return str(mode.get("id", ""))
		if weapon_vnum in required:
			return str(mode.get("id", ""))
	return ""


func motion(actor_id: String, mode_id: String, action_id := "", action := "") -> Dictionary:
	if not action_id.is_empty():
		return _motions_by_action_id.get(actor_id + "\n" + action_id, {})
	var candidates: Array = _motions_by_action.get(actor_id + "\n" + mode_id + "\n" + action, [])
	if not candidates.is_empty():
		return candidates[0]
	return {}


func motions(actor_id: String, mode_id: String, action: String) -> Array:
	return _motions_by_action.get(actor_id + "\n" + mode_id + "\n" + action, [])


func mode_for_action_id(actor_id: String, action_id: String) -> String:
	return str(motion(actor_id, "", action_id).get("mode_id", ""))


func select_motion(actor_id: String, mode_id: String, action: String, selector: int) -> Dictionary:
	var candidates := motions(actor_id, mode_id, action)
	if candidates.is_empty():
		return {}
	var total := 0
	for candidate: Dictionary in candidates:
		total += int(candidate.get("weight", 0))
	if total <= 0:
		return {}
	var target := posmod(selector, total)
	for candidate: Dictionary in candidates:
		target -= int(candidate.get("weight", 0))
		if target < 0:
			return candidate
	return candidates.back()


func _index_artifact(value: Variant) -> bool:
	if not value is Dictionary:
		return _fail("Actor profile contains a non-object artifact.")
	var id := str(value.get("id", ""))
	var path := str(value.get("path", ""))
	if id.is_empty() or _artifacts.has(id) or not _valid_resource_path(path):
		return _fail("Actor profile contains a duplicate or invalid artifact.")
	if not _is_sha256(value.get("sha256")):
		return _fail("Actor artifact %s has an invalid SHA-256." % id)
	_artifacts[id] = value
	return true


func _index_actor(value: Variant) -> bool:
	if not value is Dictionary:
		return _fail("Actor profile contains a non-object actor.")
	if not _validate_actor_header(value):
		return false
	var id := str(value.get("id", ""))
	if not _index_actor_modes(id, value.get("modes")):
		return false
	_actors[id] = value
	return true


func _validate_actor_header(value: Dictionary) -> bool:
	var id := str(value.get("id", ""))
	if id.is_empty() or _actors.has(id):
		return _fail("Actor profile contains a duplicate or empty actor ID.")
	if value.get("forward") != "-Z":
		return _fail("Actor %s does not declare canonical Godot -Z forward." % id)
	if value.get("motion_vector_space") != "output_actor_local_godot":
		return _fail("Actor %s has an incompatible motion-vector coordinate space." % id)
	if not _validate_model_reference(value.get("model")):
		return _fail("Actor %s has an invalid model reference." % id)
	if not value.get("modes") is Array or value.get("modes", []).is_empty():
		return _fail("Actor %s has no motion modes." % id)
	return true


func _index_actor_modes(actor_id: String, modes: Array) -> bool:
	var mode_ids: Dictionary = {}
	var indexed_modes: Dictionary = {}
	for mode: Variant in modes:
		if not mode is Dictionary:
			return _fail("Actor %s has a non-object motion mode." % actor_id)
		var mode_id := str(mode.get("id", ""))
		if mode_id.is_empty() or mode_ids.has(mode_id) or not mode.get("motions") is Array:
			return _fail("Actor %s has an invalid or duplicate motion mode." % actor_id)
		var required: Variant = mode.get("required_item_vnums", [])
		if not required is Array:
			return _fail("Actor %s has invalid required item vnums." % actor_id)
		for index in required.size():
			if not _positive_integer(required[index]):
				return _fail("Actor %s has invalid required item vnums." % actor_id)
			required[index] = int(required[index])
		mode_ids[mode_id] = true
		indexed_modes[mode_id] = mode
		var action_ids: Dictionary = {}
		for motion_value: Variant in mode.get("motions"):
			if not _validate_motion(actor_id, mode_id, motion_value, action_ids):
				return false
	_modes_by_actor[actor_id] = indexed_modes
	return true


func _validate_motion(
	actor_id: String, mode_id: String, value: Variant, action_ids: Dictionary
) -> bool:
	if not value is Dictionary:
		return _fail("Actor %s mode %s has a non-object motion." % [actor_id, mode_id])
	var action_id := str(value.get("action_id", ""))
	var godot_name := str(value.get("godot_name", ""))
	var weight := int(value.get("weight", 0))
	var duration_value: Variant = value.get("duration_us")
	if (
		action_id.is_empty()
		or godot_name.is_empty()
		or action_ids.has(action_id)
		or weight <= 0
		or not _positive_integer(duration_value)
		or not value.get("loop") is bool
	):
		return _fail("Actor %s mode %s has invalid motion metadata." % [actor_id, mode_id])
	action_ids[action_id] = true
	value["duration_us"] = int(duration_value)
	value["mode_id"] = mode_id
	_motions_by_action_id[actor_id + "\n" + action_id] = value
	var action_key := actor_id + "\n" + mode_id + "\n" + str(value.get("action", ""))
	if not _motions_by_action.has(action_key):
		_motions_by_action[action_key] = []
	_motions_by_action[action_key].append(value)
	return true


func _index_item(value: Variant) -> bool:
	if not value is Dictionary:
		return _fail("Actor profile contains a non-object item.")
	var id := str(value.get("id", ""))
	var vnum_value: Variant = value.get("vnum")
	if id.is_empty() or _items.has(id) or not _positive_integer(vnum_value):
		return _fail("Actor profile contains a duplicate or invalid item.")
	var vnum := int(vnum_value)
	if _items_by_vnum.has(vnum):
		return _fail("Actor profile contains a duplicate item vnum.")
	if not _validate_item_details(id, value):
		return false
	value["vnum"] = vnum
	_items[id] = value
	_items_by_vnum[vnum] = value
	return true


func _validate_item_details(id: String, value: Dictionary) -> bool:
	if not _validate_model_reference(value.get("model")):
		return _fail("Item %s has an invalid model reference." % id)
	if not _validate_item_transform(id, value.get("attachment_transform")):
		return false
	if id == SWORD_ID and not _validate_selected_sword_physical(value.get("physical")):
		return _fail("The selected Sword+0 must expose its exact public physical values.")
	return true


func _validate_selected_sword_physical(value: Variant) -> bool:
	if not value is Dictionary or value.size() != 3:
		return false
	for field in ["power_min", "power_max", "refine_attack"]:
		if not value.has(field) or not _exact_integer(value[field]):
			return false
	return (
		int(value.power_min) == SWORD_POWER_MIN
		and int(value.power_max) == SWORD_POWER_MAX
		and int(value.refine_attack) == SWORD_REFINE_ATTACK
	)


func _exact_integer(value: Variant) -> bool:
	return (
		(value is int and value >= 0)
		or (
			value is float
			and is_finite(value)
			and value >= 0.0
			and value <= 9007199254740991.0
			and value == floor(value)
		)
	)


func _validate_item_transform(id: String, transform: Variant) -> bool:
	if not transform is Dictionary:
		return _fail("Item %s has no attachment transform." % id)
	for field in ["translation_m", "rotation_degrees", "scale"]:
		if not _valid_vector(transform.get(field)):
			return _fail("Item %s has an invalid %s." % [id, field])
	return true


func _validate_model_reference(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	var artifact_id := str(value.get("artifact_id", ""))
	var path := str(value.get("path", ""))
	if not _artifacts.has(artifact_id) or not _valid_resource_path(path):
		return false
	return str(_artifacts[artifact_id].get("path", "")) == path


func _require_action(actor_id: String, mode_id: String, action: String) -> bool:
	if motions(actor_id, mode_id, action).is_empty():
		return _fail("Actor profile omits %s.%s.%s." % [actor_id, mode_id, action])
	return true


func _valid_resource_path(path: String) -> bool:
	return (
		(
			path.begins_with("res://assets/imported/content/%s/" % PROFILE_ID)
			or path.begins_with("res://assets/imported/characters/actors/")
			or path.begins_with("res://assets/imported/authored/")
		)
		and path.ends_with(".glb")
		and not ".." in path
	)


func _valid_vector(value: Variant) -> bool:
	return _finite_vector(value) != null


func _finite_vector(value: Variant) -> Variant:
	if not value is Array or value.size() != 3:
		return null
	for component: Variant in value:
		if not component is int and not component is float:
			return null
		if not is_finite(float(component)):
			return null
	var result := Vector3(float(value[0]), float(value[1]), float(value[2]))
	return result if result.is_finite() else null


func _positive_integer(value: Variant) -> bool:
	if not value is int and not value is float:
		return false
	var number := float(value)
	return is_finite(number) and number > 0.0 and number <= 9.0e15 and number == floor(number)


func _is_sha256(value: Variant) -> bool:
	return (
		value is String
		and value.length() == 64
		and value == value.to_lower()
		and value.is_valid_hex_number(false)
	)


func _clear() -> void:
	manifest = {}
	training_target_hash = ""
	error_message = ""
	_actors = {}
	_items = {}
	_items_by_vnum = {}
	_artifacts = {}
	_modes_by_actor = {}
	_motions_by_action_id = {}
	_motions_by_action = {}


func _freeze_variant(value: Variant) -> void:
	if value is Dictionary:
		for child: Variant in value.values():
			_freeze_variant(child)
		value.make_read_only()
	elif value is Array:
		for child: Variant in value:
			_freeze_variant(child)
		value.make_read_only()


func _fail(message: String) -> bool:
	error_message = message
	if report_errors:
		push_error(message)
	return false
