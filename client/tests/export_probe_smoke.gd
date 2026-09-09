extends SceneTree
## Isolated allowlist and reducer-ACK checks for export-only instrumentation.

const ExportProbe := preload("res://tests/export_probe.gd")

var _checks := 0
var _failed := false


class CountingProbe:
	extends ExportProbe
	var publications := 0

	func _publish_monster_action_view() -> void:
		publications += 1
		super._publish_monster_action_view()


class ProbeCameraRig:
	extends Node3D

	var distance := 12.0
	var yaw := 0.0
	var pitch := deg_to_rad(48.0)
	var wave := {
		"active": true,
		"fingerprint": "actor-a\nactor.player.warrior-male.onehand.combo_4\n9\n1000000",
		"action_id": "actor.player.warrior-male.onehand.combo_4",
		"attack_sequence": 9,
		"action_started_at_us": 1_000_000,
		"activation_us": 1_633_334,
		"duration_us": 200_000,
		"elapsed_us": 0,
		"sample_index": 0,
		"offset": [0.01, -0.02, 0.03],
		"trigger_count": 1,
		"last_outcome": "triggered",
		"policy": "deterministic-zero-mean-60hz-v1",
	}

	func _init() -> void:
		name = "OrbitCamera"
		var camera := Camera3D.new()
		camera.name = "Camera3D"
		var base := Vector3(0, sin(pitch), cos(pitch)) * distance
		camera.position = base + Vector3(0.01, -0.02, 0.03)
		add_child(camera)

	func screen_wave_snapshot() -> Dictionary:
		return wave.duplicate(true)


class ProbePanel:
	extends RefCounted

	func snapshot() -> Dictionary:
		return {"visible": false}


class ProbeHud:
	extends RefCounted
	var npc_panel := ProbePanel.new()


class ProbeWorld:
	extends Node

	var connection := GameConnection.new()
	var events: Array[InputEvent] = []
	var hud := ProbeHud.new()
	var _pve := {}
	var _hovered_npc: NpcActor

	func _init() -> void:
		add_child(connection)
		add_child(ProbeCameraRig.new())
		var players := Node.new()
		players.name = "Players"
		add_child(players)

	func dev_snapshot() -> Dictionary:
		return {}

	func _unhandled_input(event: InputEvent) -> void:
		events.append(event)


class ProbeActor:
	extends Node3D

	var identity := ""

	func presentation_snapshot() -> Dictionary:
		return {
			"action_id": "actor.player.warrior-male.onehand.combo_1",
			"sequence": 8,
			"attack_sequence": 8,
			"server_position": [1.0, 2.0, 3.0],
			"presentation_local_position": [0.0, 0.0, 0.0],
			"model_local_position": [0.0, 0.0, 0.0],
		}


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var batch_probe := CountingProbe.new()
	var population: Array = []
	for index: int in range(2800):
		population.append({"id": index + 1, "life_sequence": 0, "health": 100})
	batch_probe._on_monsters_changed(population)
	_check(
		batch_probe.publications == 1 and batch_probe._monster_action_history.size() == 256,
		"full population publishes one bounded action history per update"
	)
	_check(
		(
			batch_probe._monster_action_history[0].id == 2545
			and batch_probe._monster_action_history[-1].id == 2800
		),
		"batched history preserves newest-record order"
	)
	batch_probe._on_monsters_changed(population)
	_check(batch_probe.publications == 1, "unchanged population does not republish history")
	population[0].health = 99
	batch_probe._on_monsters_changed(population)
	_check(
		batch_probe.publications == 2 and batch_probe._monster_action_history[-1].id == 1,
		"single changed monster publishes its latest action record"
	)
	batch_probe.free()
	_check(GameConnection.EXPECTED_PROTOCOL_VERSION == 29, "client accepts only protocol 29")
	# Use the real scene without entering the tree, so this verifies the probe's
	# node lookup without starting account flow or a game connection.
	var scene := load("res://scenes/main.tscn") as PackedScene
	var actual_world := scene.instantiate()
	var actual_probe := ExportProbe.new()
	actual_world.add_child(actual_probe)
	actual_probe._capture_screen_wave()
	_check(
		(
			actual_probe._screen_wave_history.size() == 1
			and actual_probe._screen_wave_history[0].camera_local_position.size() == 3
		),
		"probe reads the actual main scene camera without a synthetic node-name contract",
	)
	actual_world.free()
	var writer := ExportProbe.new()
	writer._report = ProjectSettings.globalize_path("user://atomic-probe.json")
	_check(writer._publish_native_snapshot('{"revision":1}') == OK, "initial snapshot publishes")
	var reader := FileAccess.open(writer._report, FileAccess.READ)
	_check(
		writer._publish_native_snapshot('{"revision":2,"monsters":[]}') == OK,
		"complete native snapshot atomically replaces its predecessor",
	)
	_check(
		(
			JSON.parse_string(reader.get_as_text()).revision == 1
			and JSON.parse_string(FileAccess.get_file_as_string(writer._report)).revision == 2
			and not FileAccess.file_exists(writer._report + ".tmp")
		),
		"an existing reader keeps a complete old snapshot while new readers see the replacement",
	)
	reader.close()
	DirAccess.remove_absolute(writer._report)
	writer.free()
	root.size = Vector2i(1280, 800)
	var world := ProbeWorld.new()
	root.add_child(world)
	var probe := ExportProbe.new()
	probe._report = ProjectSettings.globalize_path("user://active-probe.json")
	world.add_child(probe)
	await process_frame
	probe._capture_screen_wave()
	_check(
		(
			probe._screen_wave_history.size() == 1
			and (
				probe._screen_wave_history[0].action_id
				== "actor.player.warrior-male.onehand.combo_4"
			)
			and probe._screen_wave_history[0].sample_index == 0
			and probe._screen_wave_history[0].camera_local_position.size() == 3
			and probe._screen_wave_history[0].base_camera_local_position.size() == 3
		),
		"probe retains the transient screen wave and applied camera-layer position"
	)
	probe._capture_screen_wave()
	_check(probe._screen_wave_history.size() == 1, "unchanged screen wave samples are deduplicated")
	world.get_node("OrbitCamera").wave.sample_index = 1
	world.get_node("OrbitCamera").wave.elapsed_us = 16_667
	probe._capture_screen_wave()
	_check(
		probe._screen_wave_history.size() == 2,
		"a subsequent 60 Hz screen-wave sample remains observable",
	)

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
			"x": 1.0,
			"y": 2.0,
			"z": 3.0,
			"heading": 0.75,
			"activity": 2,
			"attack_action_id": "actor.player.warrior-male.onehand.combo_1",
			"attack_sequence": 8,
			"action_started_at_us": 1_000_000,
			"action_ends_at_us": 2_000_000,
		}
	]
	var actor := ProbeActor.new()
	actor.identity = world.connection.local_identity
	actor.position = Vector3(0.8, 2.0, 2.7)
	world.get_node("Players").add_child(actor)
	probe._elapsed = 0.0
	world.connection.players_changed.emit(world.connection.players)
	_check(
		(
			probe._public_action_history.size() == 1
			and probe._public_action_history[0].public_action.size() == 9
			and probe._public_action_history[0].public_action.x == 1.0
			and probe._public_action_history[0].public_action.heading == 0.75
			and probe._public_action_history[0].presentation.size() == 6
			and not probe._public_action_history[0].has("token")
		),
		"probe retains bounded public action and presentation evidence"
	)
	_check(
		probe._elapsed == 0.2 and not probe._last_own_action_fingerprint.is_empty(),
		"own subscribed action transition schedules one prompt native snapshot",
	)
	var rendered_position: Array = probe._public_action_history[0].rendered_position
	_check(
		(
			rendered_position.size() == 3
			and (
				(
					Vector3(
						float(rendered_position[0]),
						float(rendered_position[1]),
						float(rendered_position[2])
					)
					. distance_to(actor.position)
				)
				< 0.0001
			)
		),
		"probe captures the rendered actor transform with float32 tolerance"
	)
	probe._elapsed = 0.0
	world.connection.players_changed.emit(world.connection.players)
	_check(
		probe._public_action_history.size() == 1 and probe._elapsed == 0.0,
		"unchanged player projection neither duplicates history nor schedules a transition snapshot",
	)
	world.connection.monsters = [{"id": 101, "life_sequence": 4, "health": 100, "name": "Wild Dog"}]
	probe._elapsed = 0.0
	world.connection.monsters_changed.emit(world.connection.monsters)
	_check(
		(
			probe._monster_health_history.size() == 1
			and probe._monster_health_history[0].size() == 4
			and probe._monster_health_history[0].id == 101
			and probe._monster_health_history[0].life_sequence == 4
			and probe._monster_health_history[0].health == 100
			and probe._monster_health_history[0].observed_at_ticks_ms is int
			and not probe._monster_health_history[0].has("name")
			and probe._elapsed == 0.2
		),
		"probe retains a bounded public monster-health change and schedules its native snapshot",
	)
	_check(
		(
			probe._monster_action_history.size() == 1
			and probe._monster_action_history[0].size() == 12
			and probe._monster_action_history[0].id == 101
			and probe._monster_action_history[0].life_sequence == 4
			and probe._monster_action_history[0].health == 100
			and not probe._monster_action_history[0].has("name")
		),
		"probe retains a bounded public monster action-position sample",
	)
	probe._elapsed = 0.0
	world.connection.monsters_changed.emit(world.connection.monsters)
	_check(
		(
			probe._monster_health_history.size() == 1
			and probe._monster_action_history.size() == 1
			and probe._elapsed == 0.0
		),
		"unchanged public monster state neither duplicates history nor schedules a snapshot",
	)
	world.connection.monsters[0].activity = 2
	world.connection.monsters[0].attack_action_id = ("actor.mob.wild-dog-101.general.front_knockdown")
	world.connection.monsters[0].attack_sequence = 4
	world.connection.monsters[0].action_started_at_us = 4_000_000
	world.connection.monsters[0].action_ends_at_us = 5_166_667
	world.connection.monsters[0].x = 3.25
	world.connection.monsters[0].y = 0.0
	world.connection.monsters[0].z = 3.0
	world.connection.monsters_changed.emit(world.connection.monsters)
	_check(
		(
			probe._monster_action_history.size() == 2
			and (
				probe._monster_action_history[-1].attack_action_id
				== "actor.mob.wild-dog-101.general.front_knockdown"
			)
			and is_equal_approx(float(probe._monster_action_history[-1].x), 3.25)
		),
		"reaction history binds the authoritative action start to its public coordinate",
	)
	for index: int in range(130):
		world.connection.monsters[0].life_sequence = index + 5
		world.connection.monsters[0].health = 100 - index % 101
		world.connection.monsters_changed.emit(world.connection.monsters)
	_check(
		(
			probe._monster_health_history.size() == 128
			and probe._monster_health_history[0].life_sequence == 7
			and probe._monster_health_history[-1].life_sequence == 134
		),
		"monster health history retains only the newest 128 public changes",
	)
	for index: int in range(260):
		world.connection.monsters[0].x = 4.0 + index
		world.connection.monsters_changed.emit(world.connection.monsters)
	_check(
		(
			probe._monster_action_history.size() == 256
			and is_equal_approx(float(probe._monster_action_history[-1].x), 263.0)
		),
		"monster action history retains only the newest 256 public projections",
	)
	for index: int in range(260):
		world.connection.players[0].x = 2.0 + index
		world.connection.players_changed.emit(world.connection.players)
	_check(
		(
			probe._public_action_history.size() == 256
			and probe._public_action_history[-1].public_action.x == 261.0
		),
		"public action history retains only the newest 256 projections"
	)
	world.connection.last_reducer_rtt_ms = 123
	world.connection.snapshot_profiled.emit("monster", 2800, 1000, 2000)
	_check(probe._snapshot_timings.is_empty(), "fast snapshots do not fill the slow trace")
	for index: int in range(65):
		world.connection.snapshot_profiled.emit("monster", index, 1000, 49_000)
	_check(
		(
			probe._snapshot_timings.size() == 64
			and probe._snapshot_timings[-1].row_count == 64
			and probe._snapshot_timings[-1].conversion_us == 1000
			and probe._snapshot_timings[-1].dispatch_us == 49_000
			and probe._snapshot_timings[-1].size() == 5
		),
		"slow trace bounds records and preserves both phases without row contents"
	)
	world.connection.reducer_completed.emit("move_to", true, 1_301_000)
	_check(
		probe._request_timings[-1].response_elapsed_ms == 123,
		"timing captures the completing request's elapsed time"
	)
	world.connection.reducer_completed.emit("begin_charge", false, 0)
	_check(
		probe._request_timings[-1].response_elapsed_ms == null,
		"local send failure does not reuse the previous response duration"
	)
	world.connection.reducer_completed.emit("send_chat", true, 1_301_001)
	_check(probe._request_timings.size() == 2, "timing excludes unrelated requests")
	for index: int in range(65):
		world.connection.reducer_completed.emit("stop_moving", true, 1_301_002 + index)
	_check(
		(
			probe._request_timings.size() == 64
			and probe._request_timings[-1].sequence == 67
			and probe._request_timings[-1].size() == 6
		),
		"timing retains only 64 typed records without request arguments"
	)
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
			and ack.public_action.size() == 9
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
			and ack.public_action.x == 261.0
			and ack.public_action.y == 2.0
			and ack.public_action.z == 3.0
			and ack.public_action.heading == 0.75
		),
		"successful ACK records only typed outcome and current public action projection"
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
	var errors_before := probe._errors.size()
	probe._elapsed = 0.0
	world.connection.reducer_failed.emit("Combo follow-up input is too late.")
	_check(
		(
			probe._errors.size() == errors_before + 1
			and probe._errors[-1] == "Combo follow-up input is too late."
			and probe._elapsed == 0.2
		),
		"reducer failure schedules its diagnostic in the next native snapshot",
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
