class_name ChargeApproach
extends RefCounted
## Reservation emits ordinary intents; subscribed lives/charge determine continuation.
var skill_vnum := 0
var target_id := 0
var target_life := -1
var owner_life := -1
var owner_identity := ""
var target_range := 0.0
var phase := "idle"
var _deadline_ms := 0
var _next_move_ms := 0


func cancel() -> void:
	phase = "idle"
	skill_vnum = 0
	target_id = 0


func start(definition: Dictionary, owner: Dictionary, target: Dictionary, now_ms: int) -> String:
	cancel()
	if (
		not SkillCatalog.supported_handler(definition)
		or definition.get("handler") != "physical_charge_v1"
	):
		return ""
	if not _living(owner) or not _living(target) or str(owner.get("identity", "")).is_empty():
		return ""
	skill_vnum = int(definition.get("vnum", 0))
	if skill_vnum < 1 or skill_vnum > 255:
		cancel()
		return ""
	target_id = int(target.get("id", 0))
	target_life = int(target.get("life_sequence", -1))
	owner_life = int(owner.get("life_sequence", -1))
	owner_identity = str(owner.identity)
	if target_id <= 0 or target_life < 0 or owner_life < 0:
		cancel()
		return ""
	target_range = float(definition.target_range_m)
	_deadline_ms = now_ms + 5000
	_next_move_ms = now_ms
	if _distance(owner, target) < target_range:
		phase = "finishing"
		return "cast_skill"
	phase = "waiting_charge"
	return "begin_charge"


func advance(
	owner: Dictionary, target: Dictionary, charge: Dictionary, selected: Dictionary, now_ms: int
) -> String:
	if phase == "idle":
		return ""
	if (
		now_ms >= _deadline_ms
		or not _living(owner)
		or not _living(target)
		or str(owner.get("identity", "")) != owner_identity
		or int(owner.get("life_sequence", -1)) != owner_life
		or int(target.get("id", 0)) != target_id
		or int(target.get("life_sequence", -1)) != target_life
		or int(selected.get("target_id", 0)) != target_id
		or int(selected.get("target_life_sequence", -1)) != target_life
	):
		cancel()
		return "stop"
	if phase == "finishing":
		return ""
	var matched := (
		str(charge.get("character_id", "")) == owner_identity
		and int(charge.get("skill_vnum", 0)) == skill_vnum
	)
	if not matched:
		var expired := phase == "approaching"
		if expired:
			cancel()
		return "stop" if expired else ""
	phase = "approaching"
	if _distance(owner, target) < target_range * 0.9:
		phase = "finishing"
		return "cast_skill"
	var due := now_ms >= _next_move_ms
	if due:
		_next_move_ms = now_ms + 200
	return "move_to" if due else ""


func completed(reducer: String, succeeded: bool) -> void:
	if (reducer == "begin_charge" and not succeeded) or reducer == "cast_skill":
		cancel()


static func _living(row: Dictionary) -> bool:
	return (
		int(row.get("health", 0)) > 0
		and row.get("online", true) == true
		and is_finite(float(row.get("x", NAN)))
		and is_finite(float(row.get("z", NAN)))
	)


static func _distance(owner: Dictionary, target: Dictionary) -> float:
	return Vector2(float(owner.x), float(owner.z)).distance_to(
		Vector2(float(target.x), float(target.z))
	)
