extends SceneTree
## Unshipped, isolated driver for one structured progression-operator reducer call.

const BINDINGS := "res://spacetime_bindings/schema/module_game_client.gd"
const TIMEOUT_MSEC := 30000

var _client: SpacetimeDBClient
var _config: Dictionary = {}
var _deadline := 0
var _actor_account := ""
var _request_id := ""
var _finished := false


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var config_path := ""
	for index in range(args.size() - 1):
		if args[index] == "--operator-config":
			config_path = args[index + 1]
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	if not parsed is Dictionary:
		_fail("Operator driver requires a private configuration file.")
		return
	_config = parsed
	if not _valid_config():
		_fail("Operator driver configuration is invalid.")
		return
	_request_id = str(_config.get("request_id", ""))
	_deadline = Time.get_ticks_msec() + TIMEOUT_MSEC
	call_deferred("_connect")


func _valid_config() -> bool:
	return (
		str(_config.get("server", "")).begins_with("http")
		and not str(_config.get("database", "")).is_empty()
		and not str(_config.get("token", "")).is_empty()
		and str(_config.get("request_id", "")).length() == 32
		and str(_config.get("target_account", "")).length() == 64
		and _config.get("enabled") is bool
		and str(_config.get("reason", "")).length() >= 3
		and not str(_config.get("report", "")).is_empty()
	)


func _connect() -> void:
	var script: Script = load(BINDINGS)
	_client = script.new() as SpacetimeDBClient
	if _client == null:
		_fail("Generated P2 bindings could not be loaded.")
		return
	root.add_child(_client)
	_client.connected.connect(_on_connected)
	_client.connection_error.connect(func(_code: int, _reason: String): _fail("Connection failed."))
	_client.protocol_error.connect(func(_reason: String): _fail("Protocol decoding failed."))
	_client.subscription_error.connect(
		func(_reason: String): _fail("Feedback subscription failed.")
	)
	var options := SpacetimeDBConnectionOptions.new()
	options.threading = false
	options.one_time_token = true
	options.save_token = false
	options.debug_mode = false
	options.confirmed_reads = false
	options.compression = SpacetimeDBConnection.CompressionPreference.NONE
	options.token = str(_config.token)
	_client.connect_db(str(_config.server), str(_config.database), options)


func _on_connected(identity: PackedByteArray, _token: String) -> void:
	_actor_account = identity.hex_encode()
	var subscription := _client.subscribe(PackedStringArray(["SELECT * FROM command_feedback"]))
	if subscription.error != OK:
		_fail("Feedback subscription could not be started.")
		return
	subscription.applied.connect(_open_account)


func _open_account() -> void:
	_call("open_account", [], [], _provision)


func _provision() -> void:
	_call(
		"provision_progression_operator",
		[
			_request_id,
			str(_config.target_account).hex_decode(),
			bool(_config.enabled),
			str(_config.reason),
		],
		[&"String", &"__identity__", &"Bool", &"String"],
		_wait_for_feedback
	)


func _call(reducer: String, args: Array, types: Array, on_success: Callable) -> void:
	var call := _client.call_reducer(reducer, args, types)
	if call.error != OK:
		_fail("Reducer request could not be sent.")
		return
	call.response.connect(
		func(response: ReducerResultMessage):
			match response.reducer_result.value:
				ReducerOutcomeEnum.Options.ok:
					on_success.call()
				ReducerOutcomeEnum.Options.err:
					_fail("Reducer rejected the authenticated account or control lease.")
				_:
					_fail("Server returned an internal reducer error.")
	)


func _wait_for_feedback() -> void:
	call_deferred("_poll_feedback")


func _poll_feedback() -> void:
	if _finished:
		return
	for row: Resource in _client.get_local_database().get_all_rows("command_feedback"):
		if str(row.request_id) == _request_id:
			_finish(str(row.severity), str(row.message))
			return
	await create_timer(0.05).timeout
	_poll_feedback()


func _process(_delta: float) -> bool:
	if not _finished and _deadline > 0 and Time.get_ticks_msec() >= _deadline:
		_fail("Operator request timed out.")
	return false


func _finish(severity: String, message: String) -> void:
	if _finished:
		return
	_finished = true
	var report := {
		"applied": severity == "success",
		"request_id": _request_id,
		"actor_account": _actor_account,
		"severity": severity,
		"message": message,
	}
	var file := FileAccess.open(str(_config.report), FileAccess.WRITE)
	if file == null:
		quit(1)
		return
	file.store_string(JSON.stringify(report))
	file.close()
	_config.clear()
	quit(0)


func _fail(message: String) -> void:
	if _finished:
		return
	_finished = true
	printerr(message)
	_config.clear()
	quit(1)
