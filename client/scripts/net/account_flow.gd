class_name AccountFlow
extends Node
## Account lobby coordinator. The game only receives the selected character's state.

const Intro = preload("res://scripts/ui/classic_intro.gd")
const AuthTransport = preload("res://scripts/net/account_auth.gd")
## A single probe can miss while the page is busy (the exported Web build runs at
## a few frames per second under software rendering), and dropping availability
## for that blip hides the server row and disables the account-list button.
const PROBE_FAILURE_TOLERANCE := 3

var _auth: AuthTransport
var _connection: GameConnection
var _intro: Control
var _hud: DevHud
var _server := ""
var _database := ""
var _profile := ""
var _active := true
var _return_to_world := false
var _refresh_at := 0
var _health_at := 0
var _health_pending := false
var _game_probe_failures := 0
var _auth_probe_failures := 0
var _restoring := false
## True while a scheduled token refresh deliberately drops the world connection.
## The lobby overlay and the HUD windows stay as the player left them until the
## refreshed session either reconnects or fails.
var _refreshing := false


func _process(_delta: float) -> void:
	if _active and not _health_pending and Time.get_ticks_msec() >= _health_at:
		_check_server()
	if (
		_active
		and _refresh_at > 0
		and Time.get_ticks_msec() >= _refresh_at
		and _connection.state in ["connected", "lobby"]
	):
		_refresh_at = 0
		_return_to_world = _connection.state == "connected"
		_restoring = true
		_refreshing = true
		_connection.disconnect_game(true)
		_auth.resume()


func configure(
	connection: GameConnection, hud: DevHud, settings: Dictionary, profile: String
) -> void:
	_connection = connection
	_hud = hud
	_server = str(settings.server_url)
	_database = str(settings.database)
	_profile = profile
	_auth = AuthTransport.new()
	add_child(_auth)
	_auth.configure(_server, _profile)
	var layer := CanvasLayer.new()
	layer.name = "AccountScreens"
	layer.layer = 20
	add_child(layer)
	_intro = Intro.new()
	layer.add_child(_intro)
	_intro.set_server("Metin2 Godotime", false)
	_intro.login_requested.connect(_login)
	_intro.register_requested.connect(_register)
	_intro.select_requested.connect(_select_character)
	_intro.create_requested.connect(_create_character)
	_intro.enter_requested.connect(_enter)
	_intro.logout_requested.connect(logout)
	_auth.token_ready.connect(_on_token)
	_auth.failed.connect(_on_auth_failed)
	_auth.status_changed.connect(
		func(message: String): _intro.set_status("authenticating", message)
	)
	_connection.roster_changed.connect(_refresh_roster)
	_connection.progression_changed.connect(_refresh_roster)
	_connection.account_changed.connect(
		func(_info: Dictionary): _refresh_roster(_connection.characters)
	)
	_connection.connection_state_changed.connect(_on_state)
	_connection.reducer_failed.connect(_on_action_failed)
	_connection.lobby_ready.connect(_on_lobby_ready)
	_connection.lobby_action_completed.connect(_on_lobby_action)
	_connection.account_reconnect_requested.connect(_reconnect)
	_hud.set_account_entry(true)
	if _auth.has_saved_session():
		_intro.set_stage("login")
		_restoring = true
		_auth.resume()


func use_legacy_entry() -> void:
	_end_refresh()
	_active = false
	_intro.hide()
	_hud.set_account_entry(false)


func logout() -> void:
	_end_refresh()
	if not _active:
		_connection.disconnect_game()
		return
	_return_to_world = false
	_refresh_at = 0
	_restoring = false
	_connection.disconnect_game()
	# The browser build only reports a finished sign-out once the local session
	# is durably cleared; showing the login screen earlier lets an immediate
	# reload restore the token the player just discarded.
	_intro.set_status("authenticating", "Signing out…")
	await _auth.logout()
	_intro.show()
	_intro.clear_session()
	_intro.set_status("ready", "Log in to continue.")


func change_character() -> void:
	_return_to_world = false
	_connection.leave_world()


func handle_key(event: InputEventKey) -> bool:
	return _active and _intro.handle_key(event)


func snapshot() -> Dictionary:
	if not is_instance_valid(_intro):
		return {}
	var result: Dictionary = _intro.snapshot()
	result["active"] = _active
	result["account_identity"] = _connection.account_identity
	result["selected_character"] = _connection.local_identity
	result["characters"] = _connection.characters
	return result


func _login(username: String, password: String) -> void:
	_end_refresh()
	_active = true
	_restoring = false
	_return_to_world = false
	_hud.set_account_entry(true)
	_auth.login(username, password)


func _register(username: String, email: String, password: String) -> void:
	_end_refresh()
	_active = true
	_restoring = false
	_return_to_world = false
	_hud.set_account_entry(true)
	_auth.register(username, email, password)


func _on_token(token: String) -> void:
	if _active:
		_restoring = false
		_refresh_at = Time.get_ticks_msec() + 240000
		_connection.connect_account(_server, _database, token, _profile)


func _on_auth_failed(message: String) -> void:
	var was_refreshing := _refreshing
	_end_refresh()
	if not _active:
		return
	_intro.show()
	if _restoring:
		_restoring = false
		_intro.clear_session()
	if was_refreshing:
		# The refreshed session never reconnected. Return to the account lobby and
		# let the world layer drop the planned-reconnect state.
		_hud.set_account_entry(true)
	_intro.set_status("error", message)


func _on_action_failed(message: String) -> void:
	if _active and _connection.state != "connected":
		_intro.set_status("error", message)


func _on_state(state: String, message: String) -> void:
	if not _active:
		return
	if state == "error":
		# A failed refresh must fall back to the ordinary login screen.
		_end_refresh()
	_intro.visible = state != "connected" and not (_refreshing and _return_to_world)
	if state == "connected":
		_return_to_world = true
		_end_refresh()
		get_viewport().gui_release_focus()
	else:
		if state == "error":
			_intro.set_stage("login")
		_intro.set_status(state, message)


func _end_refresh() -> void:
	## The HUD follows the connection state itself: "refreshing" keeps the world
	## layer, while a reconnected, failed or abandoned session resolves it.
	_refreshing = false


func _on_lobby_ready() -> void:
	if not _active:
		return
	_refresh_roster(_connection.characters)
	_intro.set_stage("empire" if _connection.characters.is_empty() else "select")
	_intro.set_status(
		"ready",
		"Create your character." if _connection.characters.is_empty() else "Choose your character."
	)
	if _return_to_world and not _connection.local_identity.is_empty():
		_connection.enter_selected()


func _on_lobby_action(action: String) -> void:
	if not _active:
		return
	if action == "create_character":
		_refresh_roster(_connection.characters)
		_intro.set_stage("select")
		_intro.set_status("ready", "Your character is ready.")
	elif action == "select_character":
		_intro.set_status("ready", "Choose your character.")


func _refresh_roster(_rows: Array) -> void:
	if not _active or _connection.account_identity.is_empty():
		return
	var roster: Array = []
	for row: Dictionary in _connection.characters:
		var entry := row.duplicate()
		entry["id"] = str(row.get("character_id", ""))
		var progression := _connection.progression_for(entry.id)
		if progression.is_empty():
			_intro.set_status("loading", "Loading authoritative character progression…")
			return
		entry["level"] = int(progression.get("level", 0))
		entry["hth"] = int(progression.get("vitality", 0))
		entry["int"] = int(progression.get("intelligence", 0))
		entry["str"] = int(progression.get("strength", 0))
		entry["dex"] = int(progression.get("dexterity", 0))
		roster.append(entry)
	_intro.set_roster(roster, _connection.local_identity)


func _enter() -> void:
	_connection.enter_selected()


func _reconnect() -> void:
	if _active:
		_restoring = true
		_auth.resume()


func _create_character(slot: int, name: String, character_class: int, sex: int) -> void:
	if _connection.state == "lobby":
		_intro.set_status("creating", "Creating your character…")
		_connection.create_character(slot, name, character_class, sex)


func _select_character(character_id: String) -> void:
	if _connection.state == "lobby":
		_intro.set_status("selecting", "Selecting your character…")
		_connection.select_character(character_id)


func _check_server() -> void:
	_health_pending = true
	# Both probes are awaited in order; a probe that misses once no longer flips
	# the lobby offline, so the short in-flight window is invisible to the player.
	var auth_ready: bool = await _health_request("/auth/health")
	var game_ready: bool = await _health_request(
		"/v1/database/" + _database.uri_encode() + "/identity"
	)
	_auth_probe_failures = 0 if auth_ready else _auth_probe_failures + 1
	_game_probe_failures = 0 if game_ready else _game_probe_failures + 1
	var auth_available := _auth_probe_failures < PROBE_FAILURE_TOLERANCE
	var game_available := _game_probe_failures < PROBE_FAILURE_TOLERANCE
	_intro.set_server("Metin2 Godotime", auth_available and game_available, auth_available)
	_health_at = Time.get_ticks_msec() + 15000
	_health_pending = false


func _health_request(path: String) -> bool:
	var request := HTTPRequest.new()
	request.timeout = 5
	request.max_redirects = 0
	request.body_size_limit = 1024
	add_child(request)
	if request.request(_server.trim_suffix("/") + path) != OK:
		request.queue_free()
		return false
	var response: Array = await request.request_completed
	request.queue_free()
	return int(response[0]) == HTTPRequest.RESULT_SUCCESS and int(response[1]) == 200
