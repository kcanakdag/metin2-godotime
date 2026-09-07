extends SceneTree
## Two-account, real-server smoke for the bounded P2 progression administration surface.

const ConnectionScript := preload("res://scripts/net/game_connection.gd")

var _config: Dictionary = {}
var _clients: Array[GameConnection] = []
var _checks: Array[String] = []
var _errors: Array[String] = []
var _suffix := ""


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var config_path := ""
	for index in range(args.size() - 1):
		if args[index] == "--admin-smoke-config":
			config_path = args[index + 1]
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	if not parsed is Dictionary or not parsed.get("tokens") is Array:
		printerr("Admin smoke requires a private configuration file.")
		quit(1)
		return
	_config = parsed
	_suffix = Crypto.new().generate_random_bytes(5).hex_encode()
	call_deferred("_run")


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	first.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[0]), "p2-admin-a"
	)
	second.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[1]), "p2-admin-b"
	)
	if not _check(
		"two_authenticated_accounts",
		await _wait_until(func(): return first.state == "lobby" and second.state == "lobby", 20.0)
	):
		_finish()
		return
	_check("independent_account_identities", first.account_identity != second.account_identity)
	if not await _ensure_character(first, "AdmA%s" % _suffix):
		_finish()
		return
	if not await _ensure_character(second, "AdmB%s" % _suffix):
		_finish()
		return
	first.enter_selected()
	second.enter_selected()
	if not _check(
		"both_control_selected_characters",
		await _wait_until(
			func(): return first.state == "connected" and second.state == "connected", 20.0
		)
	):
		_finish()
		return
	if str(_config.mode) == "prepare":
		await _prepare_default_deny(first, second)
	else:
		await _verify_bootstrap_and_provisioning(first, second)
	_finish()


func _prepare_default_deny(first: GameConnection, second: GameConnection) -> void:
	var first_before := first.selected_progression().duplicate(true)
	var second_before := second.selected_progression().duplicate(true)
	var first_help := _request_id()
	var second_help := _request_id()
	first.request_command_help(first_help)
	second.request_command_help(second_help)
	_check(
		"default_deny_first_help", await _feedback_contains(first, first_help, "Commands: /help.")
	)
	_check(
		"default_deny_second_help",
		await _feedback_contains(second, second_help, "Commands: /help.")
	)
	var first_xp := _request_id()
	var second_xp := _request_id()
	first.admin_grant_progression_xp(first_xp, "1")
	second.admin_grant_progression_xp(second_xp, "1")
	_check(
		"default_deny_first_reducer",
		await _feedback_contains(first, first_xp, "lacks progression-admin")
	)
	_check(
		"default_deny_second_reducer",
		await _feedback_contains(second, second_xp, "lacks progression-admin")
	)
	_check("default_deny_no_first_mutation", first.selected_progression() == first_before)
	_check("default_deny_no_second_mutation", second.selected_progression() == second_before)
	_check(
		"private_feedback_is_account_scoped", _feedback_private(first) and _feedback_private(second)
	)
	_check("feedback_never_enters_public_chat", first.chat.is_empty() and second.chat.is_empty())


func _verify_bootstrap_and_provisioning(first: GameConnection, second: GameConnection) -> void:
	var first_help := _request_id()
	var second_help := _request_id()
	first.request_command_help(first_help)
	second.request_command_help(second_help)
	_check("bootstrap_help_lists_admin", await _feedback_contains(first, first_help, "/xp"))
	_check(
		"ordinary_help_hides_admin",
		await _feedback_contains(second, second_help, "Commands: /help.")
	)

	var denied_before := second.selected_progression().duplicate(true)
	var denied_inventory := second.inventory.duplicate(true)
	var denied_id := _request_id()
	second.admin_grant_progression_xp(denied_id, "300")
	_check(
		"ordinary_direct_call_denied",
		await _feedback_contains(second, denied_id, "lacks progression-admin")
	)
	_check(
		"permission_denial_preserves_state",
		second.selected_progression() == denied_before and second.inventory == denied_inventory
	)

	var grant_id := _request_id()
	first.admin_grant_progression_xp(grant_id, "300")
	_check("xp_300_feedback_exact", await _feedback_contains(first, grant_id, "exactly 300"))
	var xp_ready := await _wait_until(
		func():
			var row := first.selected_progression()
			return (
				int(row.get("level", 0)) == 2
				and int(row.get("experience", -1)) == 0
				and int(row.get("level_step", -1)) == 0
				and int(row.get("unspent_stat_points", -1)) == 3
			)
	)
	_check("xp_300_normal_progression", xp_ready)
	var level_two := first.selected_progression().duplicate(true)
	_check(
		"xp_300_random_growth",
		int(level_two.random_hp) in range(36, 45) and int(level_two.random_sp) in range(18, 23)
	)
	_check("xp_300_eight_normal_potions", _potion_count(first, 27001) == 13)

	await create_timer(1.05).timeout
	first.admin_grant_progression_xp(grant_id, "301")
	_check(
		"changed_args_same_id_denied",
		await _feedback_contains(first, grant_id, "bound to different arguments")
	)
	_check(
		"changed_args_no_mutation",
		first.selected_progression() == level_two and _potion_count(first, 27001) == 13
	)
	first.admin_grant_progression_xp(grant_id, "300")
	_check(
		"original_replay_restores_outcome", await _feedback_contains(first, grant_id, "exactly 300")
	)
	_check(
		"identical_replay_no_mutation",
		first.selected_progression() == level_two and _potion_count(first, 27001) == 13
	)

	for invalid: String in ["0", "-1", "+1", "1.0", "1e3", "NaN", "１２", "4294967296"]:
		await create_timer(1.01).timeout
		var invalid_id := _request_id()
		first.admin_grant_progression_xp(invalid_id, invalid)
		_check(
			"xp_boundary_%s" % invalid.sha256_text().left(8),
			await _feedback_contains(first, invalid_id, "Usage: /xp")
		)
	_check("invalid_xp_preserves_progression", first.selected_progression() == level_two)

	await create_timer(1.01).timeout
	var level_id := _request_id()
	first.admin_raise_progression_level(level_id, "3")
	_check("level_raise_feedback", await _feedback_contains(first, level_id, "level 2 to 3"))
	_check(
		"level_raise_exact_state",
		(
			int(first.selected_progression().level) == 3
			and int(first.selected_progression().experience) == 0
			and int(first.selected_progression().level_step) == 0
		)
	)
	var level_three := first.selected_progression().duplicate(true)
	for invalid_level: String in ["3", "2", "100"]:
		await create_timer(1.01).timeout
		var invalid_level_id := _request_id()
		first.admin_raise_progression_level(invalid_level_id, invalid_level)
		_check(
			"level_boundary_%s" % invalid_level,
			await _feedback_contains(
				first, invalid_level_id, "target" if invalid_level != "100" else "Usage:"
			)
		)
	_check("invalid_levels_preserve_state", first.selected_progression() == level_three)

	await create_timer(1.01).timeout
	var provision_id := _request_id()
	await _raw_success(
		first,
		"provision_progression_operator",
		[provision_id, second.account_identity.hex_decode(), true, "P2 two-account local QA"],
		[&"String", &"__identity__", &"Bool", &"String"]
	)
	_check(
		"bootstrap_provisions_exact_account",
		await _feedback_contains(first, provision_id, "access enabled")
	)
	await create_timer(1.01).timeout
	var provisioned_xp := _request_id()
	second.admin_grant_progression_xp(provisioned_xp, "1")
	_check(
		"provisioned_account_acts_immediately",
		await _feedback_contains(second, provisioned_xp, "exactly 1")
	)
	_check("provisioned_progression_applied", int(second.selected_progression().experience) == 1)

	await create_timer(1.01).timeout
	var revoke_id := _request_id()
	await _raw_success(
		first,
		"provision_progression_operator",
		[revoke_id, second.account_identity.hex_decode(), false, "P2 two-account revoke QA"],
		[&"String", &"__identity__", &"Bool", &"String"]
	)
	_check(
		"bootstrap_revokes_exact_account",
		await _feedback_contains(first, revoke_id, "access revoked")
	)
	await create_timer(1.01).timeout
	var revoked_xp := _request_id()
	second.admin_grant_progression_xp(revoked_xp, "1")
	_check(
		"revocation_applies_to_existing_session",
		await _feedback_contains(second, revoked_xp, "lacks progression-admin")
	)
	_check("revoked_request_no_mutation", int(second.selected_progression().experience) == 1)

	await create_timer(1.01).timeout
	second.admin_grant_progression_xp(grant_id, "300")
	_check(
		"cross_account_request_id_denied",
		await _feedback_contains(second, grant_id, "belongs to another account")
	)
	_check(
		"cross_account_collision_no_mutation", int(second.selected_progression().experience) == 1
	)

	var chat_before := first.chat.size()
	_check(
		"server_rejects_slash_public_chat",
		not await _raw_success(first, "send_chat", ["/xp 10"], [&"String"])
	)
	await create_timer(0.2).timeout
	_check(
		"slash_never_inserted_public_chat",
		first.chat.size() == chat_before and second.chat.size() == chat_before
	)
	_check(
		"feedback_retention_is_bounded",
		first.command_feedback.size() <= 32 and second.command_feedback.size() <= 32
	)
	_check("feedback_remains_private", _feedback_private(first) and _feedback_private(second))

	var state_before_reconnect := first.selected_progression().duplicate(true)
	first.disconnect_game()
	first.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[0]), "p2-admin-a-reconnect"
	)
	_check("bootstrap_reconnects", await _wait_until(func(): return first.state == "lobby", 20.0))
	first.enter_selected()
	_check(
		"bootstrap_recontrols_character",
		await _wait_until(func(): return first.state == "connected", 20.0)
	)
	first.admin_grant_progression_xp(grant_id, "300")
	await create_timer(0.3).timeout
	_check(
		"reconnect_replay_original_target_no_mutation",
		first.selected_progression() == state_before_reconnect
	)


func _ensure_character(client: GameConnection, name: String) -> bool:
	if client.characters.is_empty():
		client.create_character(0, name)
		if not _check(
			"create_character_%s" % name.left(6),
			await _wait_until(func(): return client.characters.size() == 1)
		):
			return false
	var character_id := str(client.characters[0].character_id)
	client.select_character(character_id)
	return _check(
		"select_character_%s" % name.left(6),
		await _wait_until(func(): return client.local_identity == character_id)
	)


func _make_client() -> GameConnection:
	var client: GameConnection = ConnectionScript.new()
	root.add_child(client)
	client.reducer_failed.connect(func(message: String): _errors.append(message))
	_clients.append(client)
	return client


func _feedback_contains(client: GameConnection, request_id: String, text: String) -> bool:
	return await _wait_until(
		func():
			for row: Dictionary in client.command_feedback:
				if str(row.request_id) == request_id and text in str(row.message):
					return true
			return false
	)


func _feedback_private(client: GameConnection) -> bool:
	return client.command_feedback.all(
		func(row: Dictionary): return str(row.account) == client.account_identity
	)


func _potion_count(client: GameConnection, vnum: int) -> int:
	var count := 0
	for row: Dictionary in client.inventory:
		if str(row.owner) == client.local_identity and int(row.vnum) == vnum:
			count += int(row.count)
	return count


func _raw_success(client: GameConnection, reducer: String, args: Array, types: Array) -> bool:
	var observed := {"done": false, "success": false}
	var call := client._client.call_reducer(reducer, args, types)
	if call.error != OK:
		return false
	call.response.connect(
		func(response: ReducerResultMessage):
			observed.done = true
			observed.success = response.reducer_result.value == ReducerOutcomeEnum.Options.ok
	)
	return await _wait_until(func(): return observed.done) and bool(observed.success)


func _request_id() -> String:
	return Crypto.new().generate_random_bytes(16).hex_encode()


func _wait_until(predicate: Callable, timeout := 8.0) -> bool:
	var deadline := Time.get_ticks_msec() + int(timeout * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if predicate.call():
			return true
		await create_timer(0.05).timeout
	return predicate.call()


func _check(label: String, passed: bool) -> bool:
	if passed:
		_checks.append(label)
		print("PASS ", label)
	else:
		_errors.append(label)
		printerr("FAIL ", label)
	return passed


func _finish() -> void:
	var identities: Array[String] = []
	for client: GameConnection in _clients:
		identities.append(client.account_identity)
	var report := {
		"passed": _errors.is_empty(),
		"mode": str(_config.mode),
		"database": str(_config.database),
		"account_identities": identities,
		"checks": _checks,
		"errors": _errors,
	}
	var file := FileAccess.open(str(_config.report), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report))
		file.close()
	_config.clear()
	quit(0 if _errors.is_empty() else 1)
