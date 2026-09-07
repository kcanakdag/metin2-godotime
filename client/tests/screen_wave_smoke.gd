extends SceneTree
## Deterministic screen-wave timing, range, lifecycle, and camera-layer checks.

const ScreenWave = preload("res://scripts/camera/screen_wave.gd")
const OrbitCameraScript = preload("res://scripts/camera/orbit_camera.gd")
const ActorCatalogScript = preload("res://scripts/content/actor_catalog.gd")
const ACTION_ID := "actor.player.warrior-male.onehand.combo_4"
const START_US := 1_000_000
const ACTIVATION_OFFSET_US := 633_334
const DURATION_US := 200_000

var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_check_catalog_event()
	var event := _event()
	var action := _action(7, START_US)
	var wave := ScreenWave.new()
	var actor := Vector3(1, 2, 3)
	var viewer := actor + Vector3(2, 0, 0)
	_check(
		not wave.observe(
			"actor-a", action, event, actor, viewer, START_US + ACTIVATION_OFFSET_US - 1
		),
		"an observed action arms before its canonical event"
	)
	_check(
		wave.observe("actor-a", action, event, actor, viewer, START_US + ACTIVATION_OFFSET_US),
		"the full-3D two-metre boundary is inclusive"
	)
	var initial := wave.snapshot()
	_check(
		initial.active and initial.trigger_count == 1 and initial.sample_index == 0,
		"the canonical crossing triggers exactly once at sample zero"
	)
	_check(_bounded_offset(initial.offset), "the first component offset stays in bounds")
	_check(
		(
			not wave.observe(
				"actor-a", action, event, actor, viewer, START_US + ACTIVATION_OFFSET_US
			)
			and int(wave.snapshot().trigger_count) == 1
		),
		"repeated observations do not retrigger one action fingerprint"
	)
	var offsets: Array[Vector3] = [_vector(initial.offset)]
	for _index in 11:
		offsets.append(wave.advance(1.0 / 60.0 + 0.0000001))
	_check(offsets.all(func(value: Vector3): return _bounded_vector(value)), "all 60 Hz samples")
	var total := Vector3.ZERO
	for offset: Vector3 in offsets:
		total += offset
	_check(total.length() < 0.000001, "the complete deterministic component sequence is zero-mean")
	_check(
		wave.advance(1.0 / 60.0).is_zero_approx() and not wave.snapshot().active,
		"the wave ends without a residual camera offset"
	)

	var late := ScreenWave.new()
	_check(
		not late.observe("actor-late", action, event, actor, actor, START_US + 700_000),
		"an already elapsed event does not replay on first observation"
	)
	_check(
		(
			not late.observe("actor-late", action, event, actor, actor, START_US + 710_000)
			and int(late.snapshot().trigger_count) == 0
		),
		"the missed late action remains consumed"
	)

	var outside := ScreenWave.new()
	outside.observe("actor-outside", action, event, actor, actor, START_US + 600_000)
	_check(
		(
			not outside.observe(
				"actor-outside",
				action,
				event,
				actor,
				actor + Vector3(2.0001, 0, 0),
				START_US + ACTIVATION_OFFSET_US
			)
			and outside.snapshot().last_outcome == "out_of_range"
		),
		"viewer range uses actor-to-local-player distance without attenuation"
	)
	var vertical := ScreenWave.new()
	vertical.observe("actor-vertical", action, event, actor, actor, START_US + 600_000)
	_check(
		(
			not vertical.observe(
				"actor-vertical",
				action,
				event,
				actor,
				actor + Vector3(0, 2.0001, 0),
				START_US + ACTIVATION_OFFSET_US
			)
			and vertical.snapshot().last_outcome == "out_of_range"
		),
		"viewer range includes the vertical component"
	)

	var disabled := ScreenWave.new()
	disabled.set_enabled(false)
	disabled.observe("actor-disabled", action, event, actor, actor, START_US + 600_000)
	_check(
		(
			not disabled.observe(
				"actor-disabled", action, event, actor, actor, START_US + ACTIVATION_OFFSET_US
			)
			and disabled.snapshot().last_outcome == "disabled"
		),
		"the accessibility setting suppresses an armed event"
	)
	disabled.set_enabled(true)
	_check(
		not disabled.observe(
			"actor-disabled", action, event, actor, actor, START_US + ACTIVATION_OFFSET_US + 1
		),
		"enabling later does not replay the suppressed event"
	)

	var replacement := ScreenWave.new()
	replacement.observe("actor-first", action, event, actor, actor, START_US + 600_000)
	replacement.observe("actor-first", action, event, actor, actor, START_US + ACTIVATION_OFFSET_US)
	var next_action := _action(8, 2_000_000)
	replacement.observe("actor-second", next_action, event, actor, actor, 2_600_000)
	_check(
		(
			replacement.observe(
				"actor-second", next_action, event, actor, actor, 2_000_000 + ACTIVATION_OFFSET_US
			)
			and replacement.snapshot().attack_sequence == 8
			and replacement.snapshot().trigger_count == 2
		),
		"a later eligible action replaces the prior presentation wave"
	)
	var delayed_older := ScreenWave.new()
	var older_action := _action(8, 2_000_000)
	delayed_older.observe("actor-old", older_action, event, actor, actor, 2_600_000)
	var newest_action := _action(9, 2_100_000)
	delayed_older.observe("actor-new", newest_action, event, actor, actor, 2_700_000)
	delayed_older.observe(
		"actor-new", newest_action, event, actor, actor, 2_100_000 + ACTIVATION_OFFSET_US
	)
	_check(
		(
			not delayed_older.observe(
				"actor-old", older_action, event, actor, actor, 2_100_000 + ACTIVATION_OFFSET_US
			)
			and delayed_older.snapshot().attack_sequence == 9
			and delayed_older.snapshot().trigger_count == 1
			and delayed_older.snapshot().last_outcome == "older_event_ignored"
		),
		"a delayed older callback cannot replace the newest eligible wave"
	)

	var invalid := _event()
	invalid.viewer_range_m = NAN
	_check(
		not ScreenWave.new().observe("actor-invalid", action, invalid, actor, actor, START_US),
		"non-finite trusted numbers fail closed"
	)
	var unsupported_duration := _event()
	unsupported_duration.duration_us = 300_000
	_check(
		not ScreenWave.new().observe(
			"actor-duration", action, unsupported_duration, actor, actor, START_US
		),
		"the named twelve-sample policy accepts only its trusted 200 ms duration"
	)
	var lifecycle := ScreenWave.new()
	lifecycle.observe("actor-reset", action, event, actor, actor, START_US + 600_000)
	lifecycle.observe("actor-reset", action, event, actor, actor, START_US + ACTIVATION_OFFSET_US)
	lifecycle.reset()
	_check(
		(
			not lifecycle.snapshot().active
			and lifecycle.snapshot().observed_actions == 0
			and lifecycle.snapshot().trigger_count == 0
			and lifecycle.advance(1.0 / 60.0).is_zero_approx()
		),
		"connection lifecycle reset clears active and observed presentation state"
	)
	_check(
		not lifecycle.observe(
			"actor-reset", action, event, actor, actor, START_US + ACTIVATION_OFFSET_US + 1
		),
		"a reset followed by a late observation does not replay the elapsed event"
	)

	var rig := OrbitCameraScript.new()
	var camera := Camera3D.new()
	camera.name = "Camera3D"
	rig.add_child(camera)
	root.add_child(rig)
	await process_frame
	var rig_action := _action(9, 3_000_000)
	rig.observe_screen_wave(
		"actor-rig", rig_action, event, actor, actor, 3_000_000 + ACTIVATION_OFFSET_US
	)
	await process_frame
	var base := Vector3(0, sin(rig.pitch), cos(rig.pitch)) * rig.distance
	_check(
		(
			camera.position.distance_to(base) > 0.0
			and is_equal_approx(rig.distance, 12.0)
			and is_equal_approx(rig.yaw, 0.0)
		),
		"the camera effect layer leaves orbit and zoom state unchanged"
	)
	rig.set_screen_wave_enabled(false)
	await process_frame
	_check(
		camera.position.distance_to(base) < 0.000001 and not rig.screen_wave_snapshot().active,
		"disabling an active wave restores the unmodified camera basis"
	)
	rig.queue_free()
	await process_frame

	if not _failed:
		print("SCREEN_WAVE_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _check_catalog_event() -> void:
	var catalog := ActorCatalogScript.new()
	_check(catalog.load_required(), "the generated actor catalog loads from JSON")
	var event: Dictionary = catalog.motion(ActorCatalogScript.WARRIOR_ID, "", ACTION_ID).get(
		"screen_wave", {}
	)
	var wave := ScreenWave.new()
	var action := _action(7, START_US)
	wave.observe("catalog-actor", action, event, Vector3.ZERO, Vector3.ZERO, START_US)
	_check(
		wave.observe(
			"catalog-actor",
			action,
			event,
			Vector3.ZERO,
			Vector3.ZERO,
			START_US + ACTIVATION_OFFSET_US
		),
		"the actual JSON-decoded event triggers at its canonical time"
	)
	for invalid_value: Variant in [true, "633334", 633334.5, NAN, INF]:
		var invalid := event.duplicate(true)
		invalid["activation_offset_us"] = invalid_value
		var invalid_wave := ScreenWave.new()
		invalid_wave.observe("bad-event", action, invalid, Vector3.ZERO, Vector3.ZERO, START_US)
		_check(
			invalid_wave.snapshot().observed_actions == 0,
			"invalid event offsets are rejected before arming"
		)


func _action(sequence: int, start_us: int) -> Dictionary:
	return {
		"activity": 2,
		"attack_action_id": ACTION_ID,
		"attack_sequence": sequence,
		"action_started_at_us": start_us,
		"action_ends_at_us": start_us + 1_266_667,
	}


func _event() -> Dictionary:
	return {
		"activation_offset_us": ACTIVATION_OFFSET_US,
		"duration_us": DURATION_US,
		"viewer_range_m": 2.0,
	}


func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _bounded_offset(value: Array) -> bool:
	return _bounded_vector(_vector(value))


func _bounded_vector(value: Vector3) -> bool:
	return (
		value.is_finite()
		and absf(value.x) <= ScreenWave.COMPONENT_LIMIT_M
		and absf(value.y) <= ScreenWave.COMPONENT_LIMIT_M
		and absf(value.z) <= ScreenWave.COMPONENT_LIMIT_M
	)


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("SCREEN_WAVE_SMOKE FAIL " + description)
