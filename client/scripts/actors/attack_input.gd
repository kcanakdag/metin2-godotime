extends RefCounted
## Held attack sends ordinary intents at source windows observed from server actions.

var held := false
var _last_sequence := -1
var _last_sent_ms := 0


func pressed(row: Dictionary, now_ms: int) -> void:
	held = true
	_record(row, now_ms)


func release() -> void:
	held = false


func should_send(
	row: Dictionary, catalog: ActorCatalog, server_us: int, now_ms: int, actor_id: String
) -> bool:
	if not held or row.is_empty() or int(row.get("health", 0)) <= 0:
		return false
	if now_ms - _last_sent_ms < 150:
		return false
	var end := int(row.get("action_ends_at_us", 0))
	if end == 0:
		_record(row, now_ms)
		return true
	if server_us >= end or int(row.get("attack_sequence", 0)) == _last_sequence:
		return false
	if not _in_combo_window(row, catalog, server_us, actor_id):
		return false
	_record(row, now_ms)
	return true


func _in_combo_window(
	row: Dictionary, catalog: ActorCatalog, server_us: int, actor_id: String
) -> bool:
	var action_id := str(row.get("attack_action_id", ""))
	# The common weapon chain has four steps; advanced chains remain disabled.
	if (
		not action_id.ends_with(".combo_1")
		and not action_id.ends_with(".combo_2")
		and not action_id.ends_with(".combo_3")
	):
		return false
	var motion := catalog.motion(actor_id, "", action_id)
	var combo: Variant = motion.get("combo")
	if not combo is Dictionary:
		return false
	var elapsed := server_us - int(row.get("action_started_at_us", 0))
	if (
		elapsed <= int(combo.get("pre_input_us", 0)) + 30000
		or elapsed > int(combo.get("input_limit_us", 0))
	):
		return false
	return true


func _record(row: Dictionary, now_ms: int) -> void:
	_last_sequence = int(row.get("attack_sequence", 0))
	_last_sent_ms = now_ms
