extends SceneTree
## UI projections and intent emission; authoritative learning is tested on a real server.

const SkillsPanel = preload("res://scripts/ui/classic_skills.gd")
const Taskbar = preload("res://scripts/ui/classic_taskbar.gd")
var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var panel := SkillsPanel.new()
	var bar := Taskbar.new()
	root.add_child(panel)
	root.add_child(bar)
	await process_frame
	panel.set_state({"character_class": 0, "level": 5}, [])
	panel.show()
	_check(panel.snapshot().points == "Skill points: 1", "level five shows one point")
	var slot: Control = panel._list.get_child(1)
	_check(slot._icon.texture != null, "original Three-Way Cut icon loads")
	var spin_slot: Control = panel._list.get_child(6)
	_check(
		spin_slot.row.skill_vnum == 2 and spin_slot._icon.texture != null,
		"Sword Spin remains available with original icon"
	)
	_check(slot._get_drag_data(Vector2.ZERO) == null, "unlearned skill cannot drag")
	var plus: TextureButton = panel._list.get_child(4)
	_check(not plus.disabled, "level five permits learning")
	var requested: Array = []
	panel.learn_requested.connect(func(vnum): requested.append(vnum))
	plus.pressed.emit()
	_check(requested == [1], "learn button emits skill intent")
	_check(panel.snapshot().rows.is_empty(), "learning waits for server subscription")
	var learned := [{"skill_vnum": 1, "rank": 1, "points_spent": 1, "ready_at_us": 15000000}]
	panel.set_state({"character_class": 0, "level": 5}, learned)
	_check(panel.snapshot().points == "Skill points: 0", "subscription spends displayed point")
	plus = panel._list.get_child(4)
	_check(plus.disabled, "spent points disable upgrade")
	bar.set_skills(learned, 1000000)
	bar.bind_skill(0, 1)
	_check(bar.item_at(0).skill_vnum == 1, "quickslot binds learned skill")
	_check(bar.item_at(0).cooldown_seconds == 14, "quickslot uses server cooldown clock")
	bar.update_skill_clock(16000000)
	_check(bar.item_at(0).cooldown_seconds == 0, "cooldown display expires")
	bar.set_skills([], 16000000)
	_check(bar.item_at(0).rank == 0, "removed skill becomes inactive")
	panel.set_state({"character_class": 0, "level": 4}, [])
	plus = panel._list.get_child(4)
	_check(plus.disabled, "level four cannot learn")
	panel.set_state({"character_class": 0, "level": 5}, learned)
	bar.set_skills(learned, 1000000)
	await process_frame
	for index in [2, 3]:
		var added_slot: Control = panel._list.get_child(index * 5 + 1)
		_check(added_slot._icon.texture != null, "batch skill original icon loads")
	var scroll: ScrollContainer = panel._list.get_parent()
	for _step in 3:
		var wheel := InputEventMouseButton.new()
		wheel.position = scroll.get_global_rect().get_center()
		wheel.global_position = wheel.position
		wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
		wheel.pressed = true
		root.push_input(wheel)
		await process_frame
	_check(scroll.scroll_vertical > 0, "wheel input scrolls expanded skill list")
	var final_slot: Control = panel._list.get_child(16)
	_check(
		scroll.get_global_rect().encloses(final_slot.get_global_rect()),
		"last skill is accessible inside viewport"
	)
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://skills-ui-component.png")
	if not _failed:
		print("SKILLS_UI_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _check(passed: bool, label: String) -> void:
	if passed:
		_checks += 1
	else:
		_failed = true
		push_error("SKILLS_UI_SMOKE FAIL " + label)
