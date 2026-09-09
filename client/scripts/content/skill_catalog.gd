class_name SkillCatalog
extends RefCounted
## Selected immutable capabilities; ranks and cooldowns come only from subscriptions.
const PATH := "res://assets/imported/skills/catalog.v1.json"
var document: Dictionary = {}
var content_hash := ""
var error_message := ""


func load_required() -> bool:
	document = {}
	content_hash = ""
	error_message = ""
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if (
		not parsed is Dictionary
		or parsed.get("schema") != "mt2spacetime.skills"
		or parsed.get("version") != 1
	):
		error_message = "Missing or incompatible skill catalog. Run the skill content build."
		return false
	var rows: Variant = parsed.get("skills")
	if not rows is Array or rows.is_empty() or rows.size() > 64:
		return false
	var ids: Dictionary = {}
	for row: Variant in rows:
		if not row is Dictionary or not supported_handler(row):
			return false
		var id := int(row.get("vnum", 0))
		if id < 1 or id > 255 or ids.has(id) or int(row.get("maximum_rank", 0)) not in range(1, 21):
			return false
		if (
			int(row.get("cooldown_us", 0)) <= 0
			or not str(row.get("icon", "")).begins_with("skill/")
		):
			return false
		ids[id] = true
	document = parsed
	content_hash = FileAccess.get_sha256(PATH)
	return true


static func _bounded_number(value: Variant, low: float, high: float, whole: bool) -> bool:
	if not (value is int or value is float):
		return false
	var number := float(value)
	return (
		is_finite(number)
		and number >= low
		and number <= high
		and (not whole or number == floor(number))
	)


static func supported_handler(row: Dictionary) -> bool:
	var handler := str(row.get("handler", ""))
	if handler in ["physical_splash_v1", "physical_area_v1"]:
		return not row.has("charge") and not row.has("buff")
	if handler == "self_buff_v1":
		return (
			not row.has("charge")
			and row.get("buff") is Dictionary
			and row.get("requires_target") is bool
			and row.requires_target == false
			and row.get("weapon_class") == "any"
			and _bounded_number(row.get("target_range_m"), 0, 0, true)
			and _bounded_number(row.get("radius_m"), 0, 0, true)
			and _rank_table(row.get("rank_costs"), 0, 10000, false)
			and _rank_table(row.get("rank_cooldowns_us"), 1000000, 600000000, true)
		)
	if handler != "physical_charge_v1":
		return false
	var charge: Variant = row.get("charge")
	if not charge is Dictionary:
		return false
	return (
		not row.has("buff")
		and row.get("requires_target") is bool
		and row.get("requires_target") == true
		and row.get("weapon_class") == "sword_or_two_handed"
		and _bounded_number(row.get("hits_per_life"), 1, 1, true)
		and _bounded_number(row.get("target_range_m"), 0.01, 100.0, false)
		and _bounded_number(charge.get("duration_us"), 1, 600000000, true)
		and _bounded_number(charge.get("speed_bonus"), 0, 1000, true)
		and _bounded_number(charge.get("push_distance_m"), 0, 8, false)
		and _bounded_number(charge.get("main_target_stun_us"), 0, 60000000, true)
	)


static func _rank_table(values: Variant, low: int, high: int, seconds: bool) -> bool:
	if not values is Array or values.size() != 21:
		return false
	for value: Variant in values:
		if not _bounded_number(value, low, high, true):
			return false
		if seconds and int(value) % 1000000 != 0:
			return false
	return true


func definition(vnum: int) -> Dictionary:
	for row: Dictionary in document.get("skills", []):
		if int(row.vnum) == vnum:
			return row
	return {}


func available(class_id: int) -> Array:
	return document.get("skills", []).filter(func(row): return int(row.class_id) == class_id)


func cost(vnum: int, rank: int) -> int:
	var row := definition(vnum)
	if row.is_empty() or rank < 0 or rank > 20:
		return 0
	if row.get("handler") == "self_buff_v1":
		return int(row.rank_costs[rank])
	return (
		int(row.sp_base)
		+ int(float(row.sp_per_power) * float(document.rank_power_percent[rank]) / 100.0)
	)


func cooldown_us(vnum: int, rank: int) -> int:
	var row := definition(vnum)
	if row.is_empty() or rank < 0 or rank > 20:
		return 0
	if row.get("handler") == "self_buff_v1":
		return int(row.rank_cooldowns_us[rank])
	return int(row.cooldown_us)
