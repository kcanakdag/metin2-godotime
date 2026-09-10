extends SceneTree
## Focused checks for the planned session refresh. A scheduled token refresh
## deliberately drops the world connection, so the HUD must keep the windows the
## player already opened and only leave the world when the refreshed session fails
## or is abandoned.

const Hud = preload("res://scripts/ui/dev_hud.gd")

var _hud: CanvasLayer
var _checks: Array[String] = []
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_hud = Hud.new()
	root.add_child(_hud)
	await process_frame
	_hud.set_connection_state("connected", "")
	_hud.set_player_info(
		{"health": 60, "max_health": 100, "gold": 123, "x": 660, "z": 575, "heading": 0}
	)
	(
		_hud
		. set_inventory(
			[
				{"id": 11, "vnum": 10, "count": 1, "cell": 0, "equipped": false},
				{"id": 12, "vnum": 27001, "count": 3, "cell": 1, "equipped": false},
			]
		)
	)
	# Escape opens the system menu first; it would close the inventory instead.
	_key(KEY_ESCAPE)
	_key(KEY_I)
	_key(KEY_K)
	_key(KEY_C)
	await process_frame
	_check(_hud.inventory_snapshot()["visible"], "inventory opens for the connected player")
	_check(_world_layer_visible(), "connected world layer shows the opened windows")
	_check(_hud._system.visible, "the system menu opens for the connected player")
	_check(not _hud._session_refresh, "a connected session is not refreshing")
	_click(_hud.inventory_snapshot()["slot_centers"][0], MOUSE_BUTTON_LEFT)
	await process_frame
	_check(_hud.inventory_snapshot()["dragging"], "the player is carrying an item")

	_hud.set_connection_state("refreshing", "Refreshing your session…")
	await process_frame
	_check(_hud._state == "refreshing", "the refresh state reaches the HUD")
	_check(_hud._session_refresh, "the HUD tracks the planned refresh")
	_check(_world_layer_visible(), "planned refresh keeps inventory, status, skills and minimap")
	_check(_hud._system.visible, "planned refresh keeps the system menu open")
	_check(not _hud._connection.visible, "planned refresh keeps the login panel hidden")
	_check(not _hud.inventory_snapshot()["dragging"], "planned refresh releases the carried item")

	_hud.set_connection_state("subscribing", "Refreshing your session…")
	await process_frame
	_check(_hud._session_refresh, "the refresh survives the reconnect subscription")
	_check(_world_layer_visible(), "reconnecting still shows the windows the player opened")

	_hud.set_connection_state("connected", "")
	await process_frame
	_check(not _hud._session_refresh, "a reconnected session ends the refresh")
	_check(_world_layer_visible(), "reconnect keeps the windows the player opened")

	_hud.set_connection_state("refreshing", "Refreshing your session…")
	await process_frame
	_check(_world_layer_visible(), "a second planned refresh keeps the windows")
	_hud.set_connection_state("error", "Session expired.")
	await process_frame
	_check(not _hud._session_refresh, "a failed refresh stops being a refresh")
	_check(_world_layer_hidden(), "a failed refresh hides the world windows")
	_check(_hud._connection.visible, "a failed refresh returns to the login panel")

	# A failed refresh is an ordinary world exit: the player re-enters the world and
	# opens the windows again.
	_hud.set_connection_state("connected", "")
	_hud.set_account_entry(false)
	_key(KEY_ESCAPE)
	_key(KEY_I)
	_key(KEY_K)
	_key(KEY_C)
	await process_frame
	_check(_world_layer_visible(), "the player is back in the world after reconnecting")
	_hud.set_connection_state("refreshing", "Refreshing your session…")
	await process_frame
	_check(_world_layer_visible(), "a third planned refresh keeps the reopened windows")
	_hud.set_account_entry(true)
	await process_frame
	_check(not _hud._session_refresh, "abandoning the refresh clears it")
	_check(_world_layer_hidden(), "abandoning the refresh hides the world windows")
	_check(not _hud._connection.visible, "the account intro owns the abandoned refresh screen")

	_hud.set_account_entry(false)
	_hud.set_connection_state("connected", "")
	_key(KEY_ESCAPE)
	_key(KEY_I)
	_key(KEY_K)
	_key(KEY_C)
	await process_frame
	_check(_world_layer_visible(), "opening the inventory works again after the refresh")
	_hud.set_connection_state("disconnected", "Disconnected.")
	await process_frame
	_check(_world_layer_hidden(), "an ordinary disconnect still hides the world windows")
	_check(_hud._connection.visible, "an ordinary disconnect shows the login panel")

	if not _failed:
		print("CLASSIC_REFRESH_SMOKE PASS ", _checks.size(), " checks")
	_hud.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func _world_layer_visible() -> bool:
	return (
		_hud._inventory.visible
		and _hud._minimap.visible
		and _hud._skills_panel.visible
		and _hud._status.visible
		and _hud._hotbar.visible
		and _hud.buff_strip.visible
	)


func _world_layer_hidden() -> bool:
	return (
		not _hud._inventory.visible
		and not _hud._minimap.visible
		and not _hud._skills_panel.visible
		and not _hud._status.visible
		and not _hud._hotbar.visible
		and not _hud.buff_strip.visible
		and not _hud._system.visible
	)


func _key(code: Key) -> bool:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	event.echo = false
	return _hud.handle_key(event)


func _click(point: Array, button: MouseButton) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(point[0], point[1])
	root.push_input(motion, true)
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = button
		event.pressed = pressed
		event.position = motion.position
		root.push_input(event, true)


func _check(passed: bool, description: String) -> void:
	if not passed:
		push_error("CLASSIC_REFRESH_SMOKE FAIL " + description)
		_failed = true
		return
	_checks.append(description)
