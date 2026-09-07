extends SceneTree
## Exercise the narrow target board from synthetic accepted/private and public rows.

const TargetPanel = preload("res://scripts/ui/classic_target.gd")
const Connection = preload("res://scripts/net/game_connection.gd")

var _target_panel: Control
var _clear_requests := 0
var _presentation_errors: Array[String] = []
var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_test_private_target_facade()
	root.size = Vector2i(1280, 720)
	_target_panel = TargetPanel.new()
	root.add_child(_target_panel)
	await process_frame
	_target_panel.clear_requested.connect(func(): _clear_requests += 1)
	_target_panel.presentation_failed.connect(
		func(message: String): _presentation_errors.append(message)
	)
	_check(not _target_panel.snapshot().visible, "target board starts hidden")
	_check(
		_target_panel.mouse_filter == Control.MOUSE_FILTER_STOP,
		"visible target board consumes pointer input"
	)

	var target := _target(1, 4)
	var monster := _monster(1, 4, 7, 75, 100)
	_target_panel.set_target(target, [monster])
	await process_frame
	var state: Dictionary = _target_panel.snapshot()
	var expected_width := 200.0 + 7.0 * len("Lv.7 Wild Dog")
	var viewport_width := root.get_visible_rect().size.x
	_check(state.visible, "accepted target and exact live generation show the board")
	_check(state.display_name == "Lv.7 Wild Dog", "level and name come from the monster row")
	_check(
		(
			state.board_rect
			== [floor((viewport_width - expected_width) / 2.0), 10.0, expected_width, 40.0]
		),
		"enemy board uses source size and top-center placement"
	)
	_check(state.name_position == [23.0, 13.0], "enemy name uses source coordinates")
	_check(
		(
			state.gauge_position == [expected_width - 175.0, 17.0]
			and state.gauge_width == 130.0
			and state.gauge_fill_position == [12.0, 0.0]
			and state.gauge_fill_max_width == 106.0
		),
		"slot and red fill use the source gauge coordinates"
	)
	_check(is_equal_approx(state.gauge_fill_width, 79.5), "gauge reflects authoritative HP")
	_check(state.gauge_texture_width == 16, "pinned red gauge keeps its native source width")
	_check(
		state.close_position == [expected_width - 30.0, 13.0] and state.action_count == 1,
		"target board exposes only the original close affordance"
	)

	_click(state.close_center)
	await process_frame
	_check(_clear_requests == 1, "actual close click emits one ordinary clear intent")
	_check(
		_target_panel.snapshot().visible, "close waits for the authoritative target row to clear"
	)
	_target_panel.set_target({}, [monster])
	_check(not _target_panel.snapshot().visible, "cleared private row hides the board")

	_target_panel.set_target(target, [_monster(1, 5, 7, 100, 100)])
	_check(not _target_panel.snapshot().visible, "new life never satisfies a stale target")
	_target_panel.set_target(target, [_monster(1, 4, 7, 0, 100)])
	_check(not _target_panel.snapshot().visible, "dead target is hidden before cleanup arrives")
	_target_panel.set_target(target, [_monster(1, 4, 0, 100, 100)])
	_check(
		(
			not _target_panel.snapshot().visible
			and _presentation_errors == ["The selected monster has an unsupported level."]
		),
		"invalid public presentation data hides and reports the target"
	)
	_target_panel.set_target(target, [monster, monster.duplicate()])
	_check(not _target_panel.snapshot().visible, "ambiguous public rows fail closed")

	monster.health = 25
	_target_panel.set_target(target, [monster])
	_check(
		is_equal_approx(float(_target_panel.snapshot().gauge_fill_width), 26.5),
		"later public HP updates resize the same source gauge"
	)
	monster.health = 100
	_target_panel.set_target(target, [monster])
	_check(
		is_equal_approx(float(_target_panel.snapshot().gauge_fill_width), 106.0),
		"full authoritative HP uses the source 106-pixel fill span"
	)
	root.size = Vector2i(1024, 600)
	await process_frame
	await process_frame
	state = _target_panel.snapshot()
	viewport_width = root.get_visible_rect().size.x
	_check(
		(
			state.board_rect[0] == floor((viewport_width - expected_width) / 2.0)
			and state.board_rect[1] == 10.0
		),
		"target board recenters after viewport resize"
	)
	_target_panel.clear_view()
	_check(not _target_panel.snapshot().visible, "leaving the world can clear target UI")

	if not _failed:
		print("CLASSIC_TARGET_SMOKE PASS ", _checks, " checks")
	_target_panel.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _test_private_target_facade() -> void:
	var facade := Connection.new()
	facade.account_identity = "a".repeat(64)
	facade.local_identity = "b".repeat(64)
	facade.combat_target = _target(1, 4)
	_check(
		facade.selected_combat_target() == facade.combat_target,
		"owner target facade accepts both IDs"
	)
	facade.combat_target.account = "c".repeat(64)
	_check(
		facade.selected_combat_target().is_empty(),
		"foreign account with the same character ID fails the local consistency guard"
	)
	facade.combat_target = _target(1, 4)
	facade.combat_target.character_id = "d".repeat(64)
	_check(
		facade.selected_combat_target().is_empty(),
		"own account cannot surface another character target"
	)
	facade.free()


func _target(id: int, life: int) -> Dictionary:
	return {
		"account": "a".repeat(64),
		"character_id": "b".repeat(64),
		"target_id": id,
		"target_life_sequence": life,
	}


func _monster(id: int, life: int, level: int, health: int, maximum: int) -> Dictionary:
	return {
		"id": id,
		"life_sequence": life,
		"level": level,
		"name": "Wild Dog",
		"health": health,
		"max_health": maximum,
		"activity": 0,
	}


func _click(point: Array) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(point[0], point[1])
	root.push_input(motion, true)
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = motion.position
		root.push_input(event, true)


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("CLASSIC_TARGET_SMOKE FAIL " + description)
