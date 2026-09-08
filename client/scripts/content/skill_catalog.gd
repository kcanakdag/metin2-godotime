class_name SkillCatalog
extends RefCounted
## Selected immutable capabilities; ranks and cooldowns come only from subscriptions.
const PATH := "res://assets/imported/skills/catalog.v1.json"
var document: Dictionary = {}
var content_hash := ""
var error_message := ""


func load_required() -> bool:
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
		if (
			not row is Dictionary
			or row.get("handler") not in ["physical_splash_v1", "physical_area_v1"]
		):
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
	return (
		int(row.sp_base)
		+ int(float(row.sp_per_power) * float(document.rank_power_percent[rank]) / 100.0)
	)
