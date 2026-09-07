extends SceneTree
## Isolated allowlist and reducer-ACK checks for export-only instrumentation.

const ExportProbe := preload("res://tests/export_probe.gd")

var _checks := 0
var _failed := false


class ProbeWorld:
	extends Node

	var connection := GameConnection.new()
	var events: Array[InputEvent] = []
	var _pve := {}

	func _init() -> void:
		add_child(connection)
		var players := Node.new()
		players.name = "Players"
		add_child(players)

	func dev_snapshot() -> Dictionary:
		return {}

	func _unhandled_input(event: InputEvent) -> void:
		events.append(event)


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var world := ProbeWorld.new()
	root.add_child(world)
	var probe := ExportProbe.new()
	world.add_child(probe)
	await process_frame

	probe._dispatch({"action": "inventory"})
	await process_frame
	_check(
		_key_events(world.events, KEY_I) == [true, false],
		"inventory command injects one fixed I-key tap"
	)
	world.events.clear()
	var command_path := ProjectSettings.globalize_path("user://probe-command.json")
	var command_file := FileAccess.open(command_path, FileAccess.WRITE)
	command_file.store_string(JSON.stringify({"sequence": 7, "action": "inventory"}))
	command_file.close()
	probe._commands = command_path
	probe._elapsed = 0.0
	probe._process(0.01)
	await process_frame
	probe._process(0.01)
	await process_frame
	_check(
		_key_events(world.events, KEY_I) == [true, false] and probe._sequence == 7,
		"native command is consumed once before the 200 ms snapshot deadline"
	)
	probe._commands = ""
	world.events.clear()
	probe._dispatch({"action": "pointer_right_click", "x": 320.0, "y": 240.0})
	await process_frame
	_check(
		_mouse_buttons(world.events, MOUSE_BUTTON_RIGHT) == [true, false],
		"right-click command injects one fixed right-button click"
	)
	_check(_motion_count(world.events) == 1, "right-click command first injects pointer motion")
	world.events.clear()
	probe._dispatch({"action": "pointer_right_click", "x": INF, "y": 240.0})
	await process_frame
	_check(world.events.is_empty(), "nonfinite right-click point injects no input")
	_check(
		probe._errors.size() == 1 and "finite in-viewport" in probe._errors[0],
		"invalid right-click point reports the bounded probe error"
	)

	world.connection.local_identity = "01".repeat(32)
	world.connection.account_identity = "02".repeat(32)
	world.connection.server_time_us = 1_300_000
	world.connection.players = [
		{
			"identity": world.connection.local_identity,
			"activity": 2,
			"attack_action_id": "actor.player.warrior-male.onehand.combo_1",
			"attack_sequence": 8,
			"action_started_at_us": 1_000_000,
			"action_ends_at_us": 2_000_000,
		}
	]
	world.connection.reducer_completed.emit("move_to", true, 1_301_000)
	world.connection.combat_target = {
		"account": world.connection.account_identity,
		"character_id": world.connection.local_identity,
		"target_id": 101,
		"target_life_sequence": 4,
	}
	world.connection.reducer_completed.emit("select_combat_target", true, 1_302_000)
	_check(
		(
			probe._select_combat_target_acks.size() == 1
			and probe._select_combat_target_acks[0].sequence == 1
			and probe._select_combat_target_acks[0].succeeded
			and probe._select_combat_target_acks[0].reducer_timestamp_us == 1_302_000
			and (
				probe._select_combat_target_acks[0].combat_target == world.connection.combat_target
			)
			and not probe._select_combat_target_acks[0].has("args")
		),
		"probe retains typed select-target completion without reducer arguments"
	)
	world.connection.reducer_completed.emit("perform_attack", true, 1_303_000)
	var acks: Array[Dictionary] = probe._perform_attack_acks
	_check(acks.size() == 1, "probe retains only perform_attack reducer completions")
	var ack := acks[0]
	_check(
		(
			ack.size() == 6
			and ack.public_action.size() == 5
			and not ack.has("args")
			and not ack.has("token")
		),
		"ACK projection contains no reducer arguments, tokens, or extra fields"
	)
	_check(
		(
			ack.get("succeeded") is bool
			and ack.succeeded
			and ack.reducer_timestamp_us == 1_303_000
			and ack.server_time_us == 1_300_000
			and ack.public_action.attack_action_id == "actor.player.warrior-male.onehand.combo_1"
			and ack.public_action.attack_sequence == 8
			and ack.public_action.action_started_at_us == 1_000_000
			and ack.public_action.action_ends_at_us == 2_000_000
		),
		"successful ACK records only typed outcome and current public action timing"
	)
	world.connection.reducer_completed.emit("perform_attack", false, 1_304_000)
	_check(
		(
			probe._perform_attack_acks.size() == 2
			and probe._perform_attack_acks[-1].sequence == 2
			and probe._perform_attack_acks[-1].succeeded is bool
			and not probe._perform_attack_acks[-1].succeeded
		),
		"rejected ACK is typed and monotonically sequenced"
	)

	var completions: Array = []
	world.connection.reducer_completed.connect(
		func(reducer_name: String, succeeded: bool, timestamp_us: int):
			completions.append(
				{"name": reducer_name, "succeeded": succeeded, "timestamp_us": timestamp_us}
			)
	)
	world.connection._pending_calls[41] = {
		"name": "perform_attack", "started": Time.get_ticks_msec(), "joining": false
	}
	var accepted := ReducerResultMessage.new()
	accepted.request_id = 41
	accepted.timestamp = 1_305_000
	accepted.reducer_result = ReducerOutcomeEnum.create_ok_empty()
	world.connection._on_reducer_response(accepted, world.connection._session)
	_check(
		completions == [{"name": "perform_attack", "succeeded": true, "timestamp_us": 1_305_000}],
		"accepted reducer response emits its typed completion"
	)
	world.connection._pending_calls[42] = {
		"name": "perform_attack", "started": Time.get_ticks_msec(), "joining": false
	}
	var rejected := ReducerResultMessage.new()
	rejected.request_id = 42
	rejected.timestamp = 1_306_000
	rejected.reducer_result = ReducerOutcomeEnum.create_err(
		PackedByteArray([0, 0, 0, 0, 100, 101, 110, 105, 101, 100])
	)
	world.connection._on_reducer_response(rejected, world.connection._session)
	_check(
		(
			completions[-1]
			== {"name": "perform_attack", "succeeded": false, "timestamp_us": 1_306_000}
		),
		"rejected reducer response emits failure without exposing reducer arguments"
	)
	world.connection._pending_calls[43] = {
		"name": "perform_attack", "started": Time.get_ticks_msec(), "joining": false
	}
	accepted.request_id = 43
	world.connection._on_reducer_response(accepted, world.connection._session + 1)
	_check(
		completions.size() == 2 and world.connection._pending_calls.has(43),
		"stale-session reducer response emits no completion"
	)
	for index: int in range(35):
		world.connection.reducer_completed.emit("perform_attack", index % 2 == 0, 1_307_000 + index)
	_check(
		(
			probe._perform_attack_acks.size() == 32
			and probe._perform_attack_acks[0].sequence == 8
			and probe._perform_attack_acks[-1].sequence == 39
		),
		"probe retains only the newest 32 typed attack completions"
	)

	print("EXPORT_PROBE_SMOKE %s %d checks" % ["FAIL" if _failed else "PASS", _checks])
	quit(1 if _failed else 0)


func _key_events(events: Array[InputEvent], keycode: Key) -> Array[bool]:
	var result: Array[bool] = []
	for event: InputEvent in events:
		if event is InputEventKey and event.keycode == keycode:
			result.append(event.pressed)
	return result


func _mouse_buttons(events: Array[InputEvent], button: MouseButton) -> Array[bool]:
	var result: Array[bool] = []
	for event: InputEvent in events:
		if event is InputEventMouseButton and event.button_index == button:
			result.append(event.pressed)
	return result


func _motion_count(events: Array[InputEvent]) -> int:
	return events.filter(func(event: InputEvent): return event is InputEventMouseMotion).size()


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failed = true
		push_error(message)
