class_name ScreenWave
extends RefCounted
## Deterministic presentation-only camera wave derived from subscribed actions.

const SAMPLE_RATE_HZ := 60
const WAVE_DURATION_US := 200_000
const COMPONENT_STEPS := 300
const COMPONENT_STEP_M := 0.001
const COMPONENT_LIMIT_M := 0.1495
const MAX_VIEWER_RANGE_M := 50.0
const MAX_OBSERVED_ACTIONS := 64

var enabled := true

var _observed: Dictionary = {}
var _observed_order: Array[String] = []
var _active: Dictionary = {}
var _elapsed_seconds := 0.0
var _offset := Vector3.ZERO
var _sample_index := -1
var _seed := 0
var _trigger_count := 0
var _last_outcome := "none"


func set_enabled(value: bool) -> void:
	enabled = value
	if not enabled:
		_clear_active()


func reset() -> void:
	_observed.clear()
	_observed_order.clear()
	_clear_active()
	_trigger_count = 0
	_last_outcome = "reset"


func observe(
	actor_identity: String,
	action: Dictionary,
	event: Dictionary,
	actor_position: Vector3,
	viewer_position: Vector3,
	server_time_us: int
) -> bool:
	if not _valid_observation(
		actor_identity, action, event, actor_position, viewer_position, server_time_us
	):
		_last_outcome = "invalid"
		return false
	var action_id := str(action.get("attack_action_id", ""))
	var sequence := int(action.get("attack_sequence", -1))
	var started_at_us := int(action.get("action_started_at_us", 0))
	var key := "%s\n%s\n%d\n%d" % [actor_identity, action_id, sequence, started_at_us]
	var activation_us := started_at_us + int(event.activation_offset_us)
	var duration_us := int(event.duration_us)
	var state: Dictionary = _observed.get(key, {})
	if state.is_empty():
		state = {"armed": server_time_us <= activation_us, "handled": false}
		_remember(key, state)
		if server_time_us > activation_us:
			state.handled = true
			_observed[key] = state
			_last_outcome = "missed_before_observation"
	if bool(state.handled) or server_time_us < activation_us:
		_sync_active(key, activation_us, duration_us, server_time_us)
		return false
	state.handled = true
	_observed[key] = state
	var rejected := ""
	if not bool(state.armed) or server_time_us >= activation_us + duration_us:
		rejected = "missed_expired"
	elif not enabled:
		rejected = "disabled"
	var range_m := float(event.viewer_range_m)
	if (
		rejected.is_empty()
		and actor_position.distance_squared_to(viewer_position) > range_m * range_m
	):
		rejected = "out_of_range"
	if not rejected.is_empty():
		_last_outcome = rejected
		return false
	if (
		not _active.is_empty()
		and str(_active.get("fingerprint", "")) != key
		and activation_us < int(_active.get("activation_us", 0))
	):
		_last_outcome = "older_event_ignored"
		return false
	_activate(key, action_id, sequence, started_at_us, activation_us, duration_us, server_time_us)
	return true


func advance(delta: float) -> Vector3:
	if _active.is_empty():
		return Vector3.ZERO
	if not is_finite(delta) or delta < 0.0:
		_last_outcome = "invalid_delta"
		_clear_active()
		return Vector3.ZERO
	_elapsed_seconds += delta
	var duration_seconds := float(int(_active.duration_us)) / 1_000_000.0
	if _elapsed_seconds >= duration_seconds:
		_last_outcome = "completed"
		_clear_active()
		return Vector3.ZERO
	_update_sample()
	return _offset


func snapshot() -> Dictionary:
	return {
		"enabled": enabled,
		"active": not _active.is_empty(),
		"fingerprint": str(_active.get("fingerprint", "")),
		"action_id": str(_active.get("action_id", "")),
		"attack_sequence": int(_active.get("attack_sequence", -1)),
		"action_started_at_us": int(_active.get("action_started_at_us", 0)),
		"activation_us": int(_active.get("activation_us", 0)),
		"duration_us": int(_active.get("duration_us", 0)),
		"elapsed_us": int(round(_elapsed_seconds * 1_000_000.0)),
		"sample_index": _sample_index,
		"offset": [_offset.x, _offset.y, _offset.z],
		"trigger_count": _trigger_count,
		"observed_actions": _observed.size(),
		"last_outcome": _last_outcome,
		"policy": "deterministic-zero-mean-60hz-v1",
		"component_limit_m": COMPONENT_LIMIT_M,
	}


func _activate(
	key: String,
	action_id: String,
	sequence: int,
	started_at_us: int,
	activation_us: int,
	duration_us: int,
	server_time_us: int
) -> void:
	_active = {
		"fingerprint": key,
		"action_id": action_id,
		"attack_sequence": sequence,
		"action_started_at_us": started_at_us,
		"activation_us": activation_us,
		"duration_us": duration_us,
	}
	_elapsed_seconds = float(server_time_us - activation_us) / 1_000_000.0
	_seed = _stable_hash(key)
	_sample_index = -1
	_trigger_count += 1
	_last_outcome = "triggered"
	_update_sample()


func _sync_active(key: String, activation_us: int, duration_us: int, server_time_us: int) -> void:
	if str(_active.get("fingerprint", "")) != key:
		return
	var elapsed := float(server_time_us - activation_us) / 1_000_000.0
	_elapsed_seconds = maxf(_elapsed_seconds, elapsed)
	if server_time_us >= activation_us + duration_us:
		_last_outcome = "completed"
		_clear_active()
	else:
		_update_sample()


func _update_sample() -> void:
	if _active.is_empty():
		return
	var index := maxi(0, int(floor(_elapsed_seconds * SAMPLE_RATE_HZ)))
	if index == _sample_index:
		return
	_sample_index = index
	_offset = Vector3(_component(index, 0), _component(index, 1), _component(index, 2))


func _component(sample: int, axis: int) -> float:
	var duration_seconds := float(WAVE_DURATION_US) / 1_000_000.0
	var half_samples := maxi(1, int(ceil(float(SAMPLE_RATE_HZ) * duration_seconds / 2.0)))
	var pair_index := sample % half_samples
	var step := (_seed + pair_index * 73 + axis * 101) % COMPONENT_STEPS
	var value := (float(step) - 149.5) * COMPONENT_STEP_M
	return -value if sample >= half_samples else value


func _remember(key: String, state: Dictionary) -> void:
	_observed[key] = state
	_observed_order.append(key)
	while _observed_order.size() > MAX_OBSERVED_ACTIONS:
		_observed.erase(_observed_order.pop_front())


func _clear_active() -> void:
	_active = {}
	_elapsed_seconds = 0.0
	_offset = Vector3.ZERO
	_sample_index = -1
	_seed = 0


func _valid_observation(
	actor_identity: String,
	action: Dictionary,
	event: Dictionary,
	actor_position: Vector3,
	viewer_position: Vector3,
	server_time_us: int
) -> bool:
	if (
		actor_identity.is_empty()
		or int(action.get("activity", -1)) != 2
		or str(action.get("attack_action_id", "")).is_empty()
		or not action.get("attack_sequence") is int
		or int(action.get("attack_sequence", -1)) < 0
		or not action.get("action_started_at_us") is int
		or int(action.get("action_started_at_us", 0)) <= 0
		or server_time_us <= 0
		or not actor_position.is_finite()
		or not viewer_position.is_finite()
	):
		return false
	if (
		not _exact_nonnegative_integer(event.get("activation_offset_us"))
		or not _exact_nonnegative_integer(event.get("duration_us"))
		or int(event.get("duration_us", 0)) != WAVE_DURATION_US
		or not (event.get("viewer_range_m") is float or event.get("viewer_range_m") is int)
	):
		return false
	var range_m := float(event.viewer_range_m)
	return is_finite(range_m) and range_m > 0.0 and range_m <= MAX_VIEWER_RANGE_M


func _exact_nonnegative_integer(value: Variant) -> bool:
	# Godot JSON decodes numeric metadata as floats. Reject fractional and unsafe values.
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


func _stable_hash(value: String) -> int:
	var result := 2166136261
	for byte: int in value.to_utf8_buffer():
		result = ((result ^ byte) * 16777619) & 0x7fffffff
	return result
