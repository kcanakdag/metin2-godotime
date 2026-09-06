extends SceneTree
## Exercise focus, plaintext, scrollback, decay, and reconnect boundaries without a server.

const Chat = preload("res://scripts/ui/classic_chat.gd")

var _chat: Control
var _events: Array[String] = []
var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_chat = Chat.new()
	root.add_child(_chat)
	await process_frame
	_chat.submitted.connect(func(message: String) -> void: _events.append(message))
	_chat.set_connected(true)
	var rows: Array = []
	for index in 12:
		rows.append({"id": index, "name": "Warrior", "message": "Message %02d" % index})
	_chat.set_chat(rows)
	_check(_chat.snapshot()["entry_position"] == [340.0, 738.0], "native centered chat anchor")
	await create_timer(0.6).timeout
	_check(_chat.snapshot()["passive_visible_count"] == 4, "passive chat retains four newest lines")
	_chat.set_chat(rows)
	_check(
		_chat.snapshot()["passive_visible_count"] == 4, "subscription refresh does not restart fade"
	)
	_chat.focus_chat()
	_check(_chat.wants_keyboard(), "Enter chat has input focus")
	_chat.get_node("ChatEntry/Input").text = "Hello [b]Warrior[/b]"
	_key(KEY_ENTER)
	await process_frame
	_check(_events == ["Hello [b]Warrior[/b]"], "Enter emits unchanged plain text")
	_check(
		not _chat.wants_keyboard() and not _chat.snapshot()["editing"],
		"sending returns keyboard control to the world"
	)
	_chat.focus_chat()
	_key(KEY_UP)
	await process_frame
	_check(_chat.get_node("ChatEntry/Input").text == _events[0], "Up recalls sent message")
	_key(KEY_ESCAPE)
	await process_frame
	_check(not _chat.wants_keyboard() and not _chat.snapshot()["editing"], "Escape closes input")
	_chat.focus_chat()
	_key(KEY_ENTER)
	await process_frame
	_check(not _chat.snapshot()["editing"], "empty Enter closes chat")
	_chat.toggle_history()
	await process_frame
	var state: Dictionary = _chat.snapshot()
	_check(state["history_rect"] == [20.0, 20.0, 450.0, 120.0], "native chat log bounds")
	_check(
		state["history_lines"].back() == "Warrior : Message 11", "history starts at newest message"
	)
	_chat._history_input.text = "From the log"
	_key(KEY_ENTER)
	await process_frame
	_check(
		(
			_events.back() == "From the log"
			and not _chat.wants_keyboard()
			and _chat.snapshot()["history_visible"]
		),
		"history send returns keyboard control while preserving the window"
	)
	_wheel(Vector2(40, 80))
	await process_frame
	_check(_chat.snapshot()["history_scroll"] < 1, "history wheel scrolls back")
	_check(
		_chat.snapshot()["history_lines"].back() != "Warrior : Message 11",
		"scrollback changes visible rows"
	)
	await _drag(Vector2(100, 30), Vector2(170, 70))
	_check(_chat.snapshot()["history_position"] == [90.0, 60.0], "chat history title drags window")
	var handle: Array = _chat.snapshot()["history_resize_handle"]
	await _drag(Vector2(handle[0], handle[1]), Vector2(handle[0] + 120, handle[1] + 140))
	_check(_chat.snapshot()["history_size"] == [570.0, 260.0], "chat history grip resizes window")
	_chat._history_input.grab_focus()
	_key(KEY_ESCAPE)
	await process_frame
	_check(not _chat.snapshot()["history_visible"], "Escape closes chat log")
	_chat.set_chat([{"id": 13, "name": "Warrior", "message": "[b]Literal[/b]"}])
	_check(
		_chat.snapshot()["passive_lines"] == ["Warrior : [b]Literal[/b]"],
		"chat never interprets BBCode"
	)
	_chat.set_connected(false)
	_check(
		not _chat.visible and _chat.snapshot()["message_count"] == 1,
		"disconnect hides retained history"
	)
	_chat.set_connected(true)
	_check(_chat.snapshot()["message_count"] == 0, "new session cannot show previous server rows")
	_chat.set_chat(rows)
	await create_timer(5.5).timeout
	_check(_chat.snapshot()["passive_visible_count"] == 0, "passive lines fade after five seconds")
	_chat.toggle_history()
	_check(_chat.snapshot()["message_count"] == 12, "faded messages remain in chat history")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://classic-chat.png")
	if not _failed:
		print("CLASSIC_CHAT_SMOKE PASS ", _checks, " checks")
	_chat.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _key(code: Key) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = code
		event.pressed = pressed
		root.push_input(event, true)


func _wheel(at: Vector2) -> void:
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_WHEEL_UP
		event.pressed = pressed
		event.position = at
		root.push_input(event, true)


func _drag(start: Vector2, finish: Vector2) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = start
	root.push_input(motion, true)
	var down := InputEventMouseButton.new()
	down.button_index = MOUSE_BUTTON_LEFT
	down.pressed = true
	down.position = start
	root.push_input(down, true)
	await process_frame
	motion = InputEventMouseMotion.new()
	motion.position = finish
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion, true)
	await process_frame
	await process_frame
	var up := InputEventMouseButton.new()
	up.button_index = MOUSE_BUTTON_LEFT
	up.position = finish
	root.push_input(up, true)
	await process_frame


func _check(condition: bool, message: String) -> void:
	if condition:
		_checks += 1
	else:
		_failed = true
		push_error("CLASSIC_CHAT_SMOKE FAIL " + message)
