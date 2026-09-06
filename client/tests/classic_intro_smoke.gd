extends SceneTree
## Real entry-screen controls with fixture responses; no authentication service is contacted.

const Intro = preload("res://scripts/ui/classic_intro.gd")

var _intro: Control
var _events: Array = []
var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_intro = Intro.new()
	root.add_child(_intro)
	_intro.login_requested.connect(
		func(user: String, password: String) -> void: _events.append(["login", user, password])
	)
	_intro.register_requested.connect(
		func(user: String, email: String, password: String) -> void:
			_events.append(["register", user, email, password])
	)
	_intro.create_requested.connect(
		func(slot: int, name: String) -> void: _events.append(["create", slot, name])
	)
	_intro.select_requested.connect(func(id: String) -> void: _events.append(["select", id]))
	_intro.enter_requested.connect(func() -> void: _events.append(["enter"]))
	_intro.logout_requested.connect(func() -> void: _events.append(["logout"]))
	await process_frame
	_check(_intro.snapshot().stage == "server", "original server selection is the initial stage")
	_click("server_confirm")
	_check(_intro.snapshot().stage == "server", "offline server cannot be selected")
	_intro.set_server("Yongan", true)
	await _capture("server")
	_click("server_confirm")
	await process_frame
	_check(_intro.snapshot().stage == "login", "server confirm opens original login")
	_check(
		_intro.snapshot().controls.username == [613.0, 406.0, 120.0, 18.0],
		"original login input coordinates"
	)
	_check(_intro._username.has_focus(), "username receives initial login focus")
	_intro._username.text = "FixtureAccount"
	_intro._password.text = "fixture-password"
	await _capture("login")
	_click("login_submit")
	_check(
		_events.back() == ["login", "FixtureAccount", "fixture-password"],
		"login emits entered credentials only"
	)
	_check(_intro.snapshot().stage == "login", "login waits for confirmed authentication")
	_intro.set_status("error", "Invalid credentials")
	_check(
		_intro._password.text.is_empty() and _intro._username.text == "FixtureAccount",
		"submitted password is cleared while the username remains available for retry"
	)
	var encoded := JSON.stringify(_intro.snapshot())
	_check(not "fixture-password" in encoded, "snapshot omits passwords")
	_intro.set_status("connecting", "Connecting")
	var count := _events.size()
	_click("login_submit")
	_check(_events.size() == count, "busy login cannot be submitted twice")
	_intro.set_status("idle", "")
	_click("register_open")
	await process_frame
	_check(_intro.snapshot().stage == "register", "register opens original-art account form")
	_intro._register_name.text = "FixtureAccount"
	_intro._email.text = "fixture@example.invalid"
	_intro._register_password.text = "fixture-register-password"
	await _capture("register")
	_click("register_submit")
	_check(
		(
			_events.back()
			== [
				"register", "FixtureAccount", "fixture@example.invalid", "fixture-register-password"
			]
		),
		"registration emits required account fields"
	)
	_check(_intro._register_password.text.is_empty(), "registration clears the submitted password")
	encoded = JSON.stringify(_intro.snapshot())
	_check(
		not "fixture@example.invalid" in encoded and not "fixture-register-password" in encoded,
		"snapshot omits email and registration password"
	)
	_intro.set_roster([], "")
	await process_frame
	_check(_intro.snapshot().stage == "empire", "new account enters original empire selection")
	await _capture("empire")
	_click("empire_confirm")
	await process_frame
	_check(_intro.snapshot().stage == "create", "Shinsoo selection opens warrior creation")
	_check(
		_intro._controls.female.disabled and _intro._controls.shape_2.disabled,
		"unavailable appearances remain disabled"
	)
	_check(_intro.snapshot().preview.models == 1, "creation loads original warrior model")
	_intro._character_name.text = "TestWarrior"
	await _capture("create")
	_click("create_submit")
	_check(_events.back() == ["create", 0, "TestWarrior"], "creation emits selected slot and name")
	_check(_intro.snapshot().roster_count == 0, "creation does not invent a character")
	_intro.set_roster([{"id": "char-a", "slot": 0, "name": "TestWarrior", "level": 1}], "char-a")
	_check(
		_intro.snapshot().stage == "create", "roster refresh preserves the active creation stage"
	)
	_intro.set_stage("select")
	await process_frame
	_check(not _intro._controls.enter.disabled, "confirmed selected character can enter")
	await _capture("select")
	_click("slot_next")
	_check(
		_intro.snapshot().slot == 1 and _intro._controls.create_open.visible,
		"original arrow selects the next empty slot"
	)
	_intro.set_roster(
		[
			{"id": "char-a", "slot": 0, "name": "TestWarrior"},
			{"id": "char-b", "slot": 1, "name": "SecondWarrior"}
		],
		"char-a"
	)
	_check(_intro._controls.enter.disabled, "unconfirmed character cannot enter world")
	_click("slot_previous")
	_click("slot_next")
	_check(_events.back() == ["select", "char-b"], "character selection sends stable server ID")
	_intro.set_roster(
		[
			{"id": "char-a", "slot": 0, "name": "TestWarrior"},
			{"id": "char-b", "slot": 1, "name": "SecondWarrior"}
		],
		"char-b"
	)
	_click("enter")
	_check(_events.back() == ["enter"], "Start emits enter only after selection confirmation")
	_intro.clear_session()
	_check(
		_intro._password.text.is_empty() and _intro._register_password.text.is_empty(),
		"logout clears retained passwords"
	)
	_intro.set_roster([{"id": "char-a", "slot": 0, "name": "TestWarrior", "level": 1}], "char-a")
	await _capture("")
	if not _failed:
		print("CLASSIC_INTRO_SMOKE PASS ", _checks, " checks")
	_intro.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _click(key: String) -> void:
	var rect: Array = _intro.snapshot().controls[key]
	var point := Vector2(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)
	var motion := InputEventMouseMotion.new()
	motion.position = point
	root.push_input(motion, true)
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.pressed = pressed
		root.push_input(event, true)


func _capture(stage: String) -> void:
	await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(
			"user://classic-intro" + ("-" + stage if not stage.is_empty() else "") + ".png"
		)


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
	else:
		_failed = true
		push_error("CLASSIC_INTRO_SMOKE FAIL " + description)
