extends RefCounted
## Held attack sends ordinary intents at source windows observed from server actions.

const AttackTiming = preload("res://scripts/actors/attack_timing.gd")

var held := false
var _last_sequence := -1
var _last_sent_ms := 0
var _pending := false
var _idle_sequence := -1
var _idle_life := -1


func pressed(row: Dictionary, now_ms: int) -> bool:
	held = true
	if _pending:
		return false
	_record(row, now_ms)
	return true


func on_reducer_completed(name: String, succeeded: bool, _timestamp: int) -> void:
	if name == "perform_attack":
		completed(succeeded)


func completed(succeeded: bool) -> void:
	_pending = false
	if not succeeded:
		_idle_sequence = -1


func reset() -> void:
	held = false
	_pending = false
	_idle_sequence = -1
	_idle_life = -1
	_last_sequence = -1
	_last_sent_ms = 0


func release() -> void:
	held = false


func should_send(
	row: Dictionary, catalog: ActorCatalog, server_us: int, now_ms: int, actor_id: String
) -> bool:
	if (
		_pending
		or not held
		or row.is_empty()
		or int(row.get("health", 0)) <= 0
		or now_ms - _last_sent_ms < 150
	):
		return false
	var end := int(row.get("action_ends_at_us", 0))
	if end == 0:
		if (
			int(row.get("attack_sequence", 0)) == _idle_sequence
			and int(row.get("life_sequence", 0)) == _idle_life
		):
			return false
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
	var speed := int(row.get("attack_speed_percent", 100))
	if speed < 100 or speed > 170:
		return false
	var elapsed := server_us - int(row.get("action_started_at_us", 0))
	if (
		elapsed <= AttackTiming.scaled_us(int(combo.get("pre_input_us", 0)), speed) + 30000
		or elapsed > AttackTiming.scaled_us(int(combo.get("input_limit_us", 0)), speed)
	):
		return false
	return true


func _record(row: Dictionary, now_ms: int) -> void:
	_last_sequence = int(row.get("attack_sequence", 0))
	_last_sent_ms = now_ms
	_pending = true
	if int(row.get("action_ends_at_us", 0)) == 0:
		_idle_sequence = _last_sequence
		_idle_life = int(row.get("life_sequence", 0))
