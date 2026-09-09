extends "res://tests/multiplayer_smoke.gd"
## Real subscriptions and validated intents. Fixture secrets never enter reports.

var _tokens: Array = []
var _name_suffix := ""
var _expected_definition_hash := ""
var _network_only := false
var _movement_attacks := false


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var config_path := ""
	for i in range(args.size() - 1):
		if args[i] == "--account-config":
			config_path = args[i + 1]
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	if not config is Dictionary or not config.get("tokens") is Array:
		printerr("Account smoke requires a private --account-config JSON fixture.")
		quit(1)
		return
	_server = str(config.get("server", _server))
	_database = str(config.get("database", _database))
	_report_path = str(config.get("report", "user://account-smoke.json"))
	_tokens = config.tokens
	_network_only = bool(config.get("network_only", false))
	_movement_attacks = bool(config.get("movement_attacks", false))
	_expected_definition_hash = str(config.get("definition_hash", ""))
	_name_suffix = Crypto.new().generate_random_bytes(6).hex_encode()
	if _tokens.size() != 2 or str(_tokens[0]).is_empty() or str(_tokens[1]).is_empty():
		printerr("Account smoke requires two signed account credentials.")
		quit(1)
		return
	call_deferred("_run")


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	if not await _create_rosters(first, second):
		_finish()
		return
	var first_id := str(first.characters[0].character_id)
	var alternative_id := str(first.characters[1].character_id)
	var second_id := str(second.characters[0].character_id)
	_check(
		"characters_have_separate_identity",
		first_id != first.account_identity and second_id != second.account_identity
	)
	_check("rosters_are_private", _private_roster(first, 4) and _private_roster(second, 1))
	_check("account_state_is_private", _private_state(first) and _private_state(second))
	_check("inventory_access_is_private", _private_access(first, 4) and _private_access(second, 1))
	_check(
		"progression_is_private",
		await _wait_until(
			func(): return _private_progression(first, 4) and _private_progression(second, 1)
		)
	)
	_check("initial_warrior_progression_is_exact", first.progression.all(_initial_progression))
	_check("warrior_male_empire_one", first.characters.all(_valid_warrior))
	await _raw_rejection(
		first,
		"create_character",
		[4, "Outside", 0, 0],
		[&"U8", &"String", &"U8", &"U8"],
		"fifth_slot_rejected",
		"slot"
	)
	await _raw_rejection(
		first,
		"create_character",
		[0, "Occupied", 0, 0],
		[&"U8", &"String", &"U8", &"U8"],
		"occupied_slot_rejected",
		"occupied"
	)
	await _raw_rejection(
		second,
		"create_character",
		[1, "ac0_%s" % _name_suffix, 0, 0],
		[&"U8", &"String", &"U8", &"U8"],
		"case_insensitive_name_rejected",
		"taken"
	)
	await _raw_rejection(
		second,
		"create_character",
		[1, "bad name", 0, 0],
		[&"U8", &"String", &"U8", &"U8"],
		"invalid_name_rejected",
		"letters"
	)
	await _raw_rejection(
		second,
		"select_character",
		[first_id.hex_decode()],
		[&"__identity__"],
		"other_account_character_rejected",
		"belong"
	)
	await _raw_rejection(
		first, "set_move_input", [1.0, 0.0], [&"F32", &"F32"], "lobby_cannot_move", "Enter"
	)
	first.select_character(first_id)
	if not _check(
		"selected_character_replicates",
		await _wait_until(func(): return first.local_identity == first_id)
	):
		_finish()
		return
	first.enter_selected()
	second.enter_selected()
	if not _check(
		"both_enter_selected_world",
		await _wait_until(
			func(): return first.state == "connected" and second.state == "connected", 20.0
		)
	):
		print(
			"ACCOUNT_ENTRY_STATE ",
			JSON.stringify(
				[
					{"state": first.state, "message": first.state_message},
					{"state": second.state, "message": second.state_message}
				]
			)
		)
		_finish()
		return
	_check(
		"selected_identity_is_character",
		first.local_identity == first_id and second.local_identity == second_id
	)
	_check(
		"initial_warrior_health_is_exact",
		(
			int(_player(second, first_id).get("health", 0)) == 760
			and int(_player(second, first_id).get("max_health", 0)) == 760
		)
	)
	await _raw_rejection(
		first,
		"allocate_stat",
		[first_id.hex_decode(), "ht"],
		[&"__identity__", &"String"],
		"allocation_without_points_rejected",
		"No unspent"
	)
	await _raw_rejection(
		second,
		"allocate_stat",
		[first_id.hex_decode(), "ht"],
		[&"__identity__", &"String"],
		"foreign_stat_allocation_rejected",
		"selected"
	)
	_check(
		"mutual_subscribed_presence",
		await _wait_until(_mutual_presence.bind(first, second, first_id, second_id))
	)
	var appearances_ready := await _wait_until(
		func():
			return (
				_valid_base_appearance(first.appearance_for(second_id))
				and _valid_base_appearance(second.appearance_for(first_id))
			)
	)
	_check("public_appearance_subscribes", appearances_ready)
	if not _check(
		"owned_inventory_subscribes",
		await _wait_until(
			func(): return first.inventory.size() == 8 and second.inventory.size() == 2
		)
	):
		_finish()
		return
	_check(
		"inventory_server_read_privacy", _private_inventory(first) and _private_inventory(second)
	)
	var sword: Dictionary = _owned_sword(first, first_id)
	if not _check("selected_starter_sword", not sword.is_empty()):
		_finish()
		return
	await _raw_rejection(
		second, "equip_item", [int(sword.id)], [&"U64"], "other_account_item_rejected", "another"
	)
	first.equip_item(int(sword.id))
	_check(
		"equipping_changes_owned_character",
		await _wait_until(func(): return bool(_owned_sword(first, first_id).get("equipped", false)))
	)
	var equip_ready := await _wait_until(
		func():
			return (
				int(first.appearance_for(first_id).get("weapon_vnum", 0)) == 10
				and int(second.appearance_for(first_id).get("weapon_vnum", 0)) == 10
			)
	)
	_check("equipped_weapon_projects_to_both_clients", equip_ready)
	var second_sword: Dictionary = _owned_sword(second, second_id)
	second.equip_item(int(second_sword.id))
	var reverse_equip_ready := await _wait_until(
		func():
			return (
				bool(_owned_sword(second, second_id).get("equipped", false))
				and int(first.appearance_for(second_id).get("weapon_vnum", 0)) == 10
			)
	)
	_check("reverse_equipment_replication", reverse_equip_ready)
	first.unequip_item(int(sword.id), int(sword.cell))
	var unequip_ready := await _wait_until(
		func():
			return (
				not bool(_owned_sword(first, first_id).get("equipped", true))
				and int(second.appearance_for(first_id).get("weapon_vnum", -1)) == 0
			)
	)
	_check("unequipped_weapon_clears_public_projection", unequip_ready)
	first.equip_item(int(sword.id))
	_check(
		"reequipped_weapon_projects",
		await _wait_until(
			func(): return int(second.appearance_for(first_id).get("weapon_vnum", 0)) == 10
		)
	)
	await _movement(first, second, first_id, 1.0, "first")
	await _movement(second, first, second_id, -1.0, "second")
	if _movement_attacks:
		var replay = load("res://tests/movement_attack_smoke.gd")
		await replay.run(self, first, second, first_id, 1.0, "first")
		await replay.run(self, second, first, second_id, -1.0, "second")
	await _raw_rejection(
		first,
		"set_move_input",
		[2.0, 0.0],
		[&"F32", &"F32"],
		"invalid_movement_rejected",
		"between"
	)
	if not _network_only and not await _authenticated_pve(first, second, first_id, sword):
		_finish()
		return
	var post_pve := _player(second, first_id)
	_check(
		"post_pve_character_ready",
		(
			first.state == "connected"
			and bool(post_pve.get("online", false))
			and int(post_pve.health) > 0
		)
	)
	var duplicate := _make_client()
	var before := _errors.size()
	duplicate.connect_account(_server, _database, str(_tokens[0]), "account-smoke-duplicate")
	_check(
		"duplicate_session_rejected",
		await _wait_until(
			func(): return _errors.size() > before and "another connection" in _errors[-1]
		)
	)
	duplicate.disconnect_game()
	await _movement(first, second, first_id, -1.0, "original_after_duplicate")
	var saved_player := _player(second, first_id).duplicate(true)
	var saved_inventory := first.inventory.duplicate(true)
	var saved_progression := first.progression_for(first_id).duplicate(true)
	first.leave_world()
	_check("leave_returns_lobby", await _wait_until(func(): return first.state == "lobby"))
	_check(
		"leave_preserves_private_progression", first.progression_for(first_id) == saved_progression
	)
	_check(
		"leave_removes_presence",
		await _wait_until(func(): return _player(second, first_id).is_empty())
	)
	_check(
		"leave_removes_public_appearance",
		await _wait_until(func(): return second.appearance_for(first_id).is_empty())
	)
	await _raw_rejection(first, "perform_attack", [], [], "lobby_cannot_attack", "Enter")
	first.select_character(alternative_id)
	_check(
		"switch_selection_replicates",
		await _wait_until(func(): return first.local_identity == alternative_id)
	)
	first.enter_selected()
	var alternative_ready := await _wait_until(
		func():
			return (
				first.state == "connected"
				and not _player(second, alternative_id).is_empty()
				and _valid_base_appearance(second.appearance_for(alternative_id))
			),
		20.0
	)
	_check("alternative_character_enters", alternative_ready)
	_check("switch_keeps_old_character_offline", _player(second, first_id).is_empty())
	_check(
		"equipment_is_per_character",
		not bool(_owned_sword(first, alternative_id).get("equipped", true))
	)
	await _raw_rejection(
		first,
		"equip_item",
		[int(sword.id)],
		[&"U64"],
		"inactive_character_item_rejected",
		"another"
	)
	first.leave_world()
	_check("alternative_leaves", await _wait_until(func(): return first.state == "lobby"))
	first.select_character(first_id)
	_check(
		"original_reselected", await _wait_until(func(): return first.local_identity == first_id)
	)
	first.enter_selected()
	_check(
		"original_returns",
		await _wait_until(
			func(): return first.state == "connected" and not _player(second, first_id).is_empty(),
			20.0
		)
	)
	_check(
		"switch_preserves_character_state",
		_same_character_state(saved_player, _player(second, first_id))
	)
	_check(
		"switch_preserves_inventory",
		await _wait_until(func(): return _same_inventory(saved_inventory, first.inventory))
	)
	first.disconnect_game()
	_check(
		"disconnect_removes_presence",
		await _wait_until(func(): return _player(second, first_id).is_empty())
	)
	_check(
		"disconnect_removes_public_appearance",
		await _wait_until(func(): return second.appearance_for(first_id).is_empty())
	)
	first.connect_account(_server, _database, str(_tokens[0]), "account-smoke-reconnect")
	_check(
		"account_reconnects_to_lobby",
		await _wait_until(func(): return first.state == "lobby", 20.0)
	)
	_check("reconnect_preserves_selection", first.local_identity == first_id)
	_check("reconnect_preserves_roster_privacy", _private_roster(first, 4))
	_check(
		"reconnect_preserves_access_privacy",
		await _subscribe_access(first, "reconnect") and _private_access(first, 4)
	)
	first.enter_selected()
	_check(
		"reconnect_enters_same_character",
		await _wait_until(
			func(): return first.state == "connected" and not _player(second, first_id).is_empty(),
			20.0
		)
	)
	_check(
		"reconnect_preserves_character_state",
		_same_character_state(saved_player, _player(second, first_id))
	)
	_check(
		"reconnect_preserves_public_appearance",
		await _wait_until(
			func(): return int(second.appearance_for(first_id).get("weapon_vnum", 0)) == 10
		)
	)
	_check(
		"reconnect_preserves_inventory_without_duplicate_starters",
		await _wait_until(func(): return _same_inventory(saved_inventory, first.inventory))
	)
	_check(
		"reconnect_preserves_private_progression",
		await _wait_until(func(): return first.progression_for(first_id) == saved_progression)
	)
	second.disconnect_game()
	_check(
		"other_account_disconnect_removes_presence",
		await _wait_until(func(): return _player(first, second_id).is_empty())
	)
	_tokens.clear()
	_finish()


func _create_rosters(first: GameConnection, second: GameConnection) -> bool:
	first.connect_account(_server, _database, str(_tokens[0]), "account-smoke-a")
	second.connect_account(_server, _database, str(_tokens[1]), "account-smoke-b")
	if not _check(
		"two_authenticated_lobbies",
		await _wait_until(func(): return first.state == "lobby" and second.state == "lobby", 20.0)
	):
		return false
	_check("independent_accounts", first.account_identity != second.account_identity)
	_check("fresh_empty_rosters", first.characters.is_empty() and second.characters.is_empty())
	if not await _subscribe_access(first, "first") or not await _subscribe_access(second, "second"):
		return false
	for slot in range(4):
		first.create_character(slot, "Ac%d_%s" % [slot, _name_suffix])
		if not _check(
			"create_slot_%d" % slot,
			await _wait_until(func(): return first.characters.size() == slot + 1)
		):
			return false
	second.create_character(0, "Bc_%s" % _name_suffix)
	if not _check(
		"second_account_character", await _wait_until(func(): return second.characters.size() == 1)
	):
		return false
	return true


func _subscribe_access(client: GameConnection, label: String) -> bool:
	var subscription := client._client.subscribe(
		PackedStringArray(["SELECT * FROM inventory_access"])
	)
	if subscription.error != OK:
		return _check(label + "_access_subscription", false)
	var observed := {"applied": false}
	subscription.applied.connect(func(): observed.applied = true)
	return _check(
		label + "_access_subscription", await _wait_until(func(): return observed.applied)
	)


func _raw_rejection(
	client: GameConnection,
	reducer: String,
	args: Array,
	types: Array,
	label: String,
	reason: String
) -> void:
	var observed := {"done": false, "rejected": false}
	var intent := _versioned_item_intent(client, reducer, args, types)
	args = intent.args
	types = intent.types
	var call := client._client.call_reducer(reducer, args, types)
	if call.error != OK:
		_check(label, false)
		return
	call.response.connect(
		func(response: ReducerResultMessage):
			observed.done = true
			observed.rejected = (
				response.reducer_result.value == ReducerOutcomeEnum.Options.err
				and reason in response.reducer_result.get_err()
			)
	)
	_check(label, await _wait_until(func(): return observed.done) and observed.rejected)


func _versioned_item_intent(
	client: GameConnection, reducer: String, args: Array, types: Array
) -> Dictionary:
	var old_count := 2 if reducer in ["move_item", "unequip_item"] else 1
	if (
		reducer in ["move_item", "equip_item", "unequip_item", "use_item"]
		and args.size() == old_count
	):
		var revision := 0
		for item: Dictionary in client.inventory:
			if int(item.id) == int(args[0]):
				revision = int(item.revision)
				break
		return {"args": args + [revision], "types": types + [&"U32"]}
	return {"args": args, "types": types}


func _movement(
	actor: GameConnection,
	observer: GameConnection,
	identity: String,
	direction: float,
	label: String
) -> void:
	var start := _position(_player(observer, identity))
	actor.set_move_input(direction, 0.0)
	await create_timer(0.3).timeout
	actor.stop_moving()
	_check(
		label + "_movement_replicates",
		await _wait_until(
			func(): return _position(_player(observer, identity)).distance_to(start) > 0.2
		)
	)
	await create_timer(0.2).timeout


func _authenticated_pve(
	actor: GameConnection, observer: GameConnection, actor_id: String, sword: Dictionary
) -> bool:
	var safe_position := _position(_player(observer, actor_id))
	if not await _pve_definition_and_approach(actor, observer, actor_id):
		return false
	if not await _pve_frozen_hit(actor, observer, actor_id, sword):
		return false
	if not await _pve_leave_cancellation(actor, observer, actor_id, sword):
		return false
	if not await _pve_prepare_death(actor, observer, actor_id, sword):
		return false
	if not await _pve_death_cancellation(actor, observer, actor_id):
		return false
	return await _pve_reward(actor, observer, actor_id, safe_position)


func _pve_definition_and_approach(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	var dog := _monster(observer)
	var definition_valid := _check(
		"wild_dog_trusted_definition",
		(
			int(dog.get("definition_vnum", 0)) == 101
			and dog.get("actor_id") == "actor.mob.wild-dog-101"
			and dog.get("name") == "Wild Dog"
			and dog.get("model_key") == "stray_dog"
			and dog.get("motion_set") == "actor.mob.wild-dog-101.general"
			and dog.get("attack_action_id") == "actor.mob.wild-dog-101.general.normal_attack.v1"
		)
	)
	var identity_valid := _check(
		"trusted_definition_identity",
		(
			actor.world_info.get("definition_profile") == "p0-warrior-dog"
			and actor.world_info.get("definition_hash") == _expected_definition_hash
			and actor.server_time_us > 0
		)
	)
	var dog_available := _check(
		"wild_dog_available",
		await _wait_until(func(): return int(_monster(observer).get("health", 0)) > 0, 16.0)
	)
	if not definition_valid or not identity_valid or not dog_available:
		return false
	dog = _monster(observer)
	var player_position := _position(_player(observer, actor_id))
	var dog_position := _position(dog)
	if player_position.distance_to(dog_position) <= 5.0:
		var away := player_position - dog_position
		if away.is_zero_approx():
			away = Vector2.LEFT
		var target := player_position + away.normalized() * 6.0
		actor.move_to(target.x, target.y)
		await _wait_until(
			func():
				return (
					_position(_player(observer, actor_id)).distance_to(
						_position(_monster(observer))
					)
					> 5.0
				),
			10.0
		)
		actor.stop_moving()
		await create_timer(0.2).timeout
	if not _check(
		"out_of_range_precondition",
		_position(_player(observer, actor_id)).distance_to(_position(_monster(observer))) > 4.0
	):
		return false

	# An accepted action outside its trusted reach has no latent hit that can apply
	# after the dog later moves closer.
	var dog_health := int(dog.health)
	var sequence := int(_player(observer, actor_id).attack_sequence)
	actor.perform_attack()
	if not _check(
		"out_of_range_action_replicates",
		await _wait_until(
			func(): return int(_player(observer, actor_id).get("attack_sequence", 0)) > sequence
		)
	):
		return false
	await create_timer(0.7).timeout
	_check("out_of_range_action_cannot_hit_later", int(_monster(observer).health) == dog_health)
	await create_timer(0.2).timeout

	dog = _monster(observer)
	var approach := Vector2(float(dog.x) - 2.35, float(dog.z))
	actor.move_to(approach.x, approach.y)
	var reached_dog := await _wait_until(
		func():
			return (
				_position(_player(observer, actor_id)).distance_to(_position(_monster(observer)))
				<= 2.6
			),
		10.0
	)
	if not _check("move_into_trusted_melee_reach", reached_dog):
		return false
	actor.stop_moving()
	await create_timer(0.9).timeout
	return true


func _pve_frozen_hit(
	actor: GameConnection, observer: GameConnection, actor_id: String, sword: Dictionary
) -> bool:
	# Reducers from one connection are ordered: the action freezes its equipped
	# onehand definition and damage before the following unequip intent is applied.
	var dog_health := int(_monster(observer).health)
	var sequence := int(_player(observer, actor_id).attack_sequence)
	actor.perform_attack()
	if not _check(
		"onehand_action_replicates",
		await _wait_until(
			func(): return int(_player(observer, actor_id).get("attack_sequence", 0)) > sequence
		)
	):
		return false
	var action_row := _player(observer, actor_id)
	var action_start := int(action_row.action_started_at_us)
	_check(
		"onehand_action_timing_is_source_derived",
		(
			action_row.attack_action_id == "actor.player.warrior-male.onehand.combo_1"
			and int(action_row.action_ends_at_us) - action_start == 1_000_000
			and observer.server_time_us < action_start + 192_308
			and int(_monster(observer).health) == dog_health
		)
	)
	actor.unequip_item(int(sword.id), int(sword.cell))
	_check(
		"mid_swing_unequip_projects",
		await _wait_until(
			func(): return int(observer.appearance_for(actor_id).get("weapon_vnum", -1)) == 0
		)
	)
	if not _check(
		"source_hit_window_applies_frozen_damage_once",
		await _wait_until(func(): return int(_monster(observer).health) == dog_health - 35)
	):
		return false
	var frozen_health := int(_monster(observer).health)
	await _wait_until(func(): return observer.server_time_us > action_start + 1_050_000, 2.0)
	_check(
		"hit_is_exactly_once_across_later_ticks", int(_monster(observer).health) == frozen_health
	)
	_check(
		"mid_swing_equipment_does_not_rewrite_action",
		action_row.attack_action_id == "actor.player.warrior-male.onehand.combo_1"
	)
	return true


func _pve_leave_cancellation(
	actor: GameConnection, observer: GameConnection, actor_id: String, sword: Dictionary
) -> bool:
	# Leaving consumes the pending hit before its window. Re-entering the same
	# life cannot revive that intent.
	actor.equip_item(int(sword.id))
	if not await _wait_until(
		func(): return int(observer.appearance_for(actor_id).get("weapon_vnum", 0)) == 10
	):
		return _check("pve_reequip_projects", false)
	await create_timer(0.9).timeout
	var dog_health := int(_monster(observer).health)
	var sequence := int(_player(observer, actor_id).attack_sequence)
	actor.perform_attack()
	if not await _wait_until(
		func(): return int(_player(observer, actor_id).get("attack_sequence", 0)) > sequence
	):
		return _check("cancelled_action_started", false)
	actor.leave_world()
	if not await _wait_until(func(): return actor.state == "lobby"):
		return _check("pending_hit_leave_reaches_lobby", false)
	await create_timer(0.55).timeout
	_check("leave_cancels_pending_hit", int(_monster(observer).health) == dog_health)
	actor.enter_selected()
	if not await _wait_until(func(): return actor.state == "connected", 20.0):
		return _check("pending_hit_reentry", false)
	_check("reentry_does_not_restore_pending_hit", int(_monster(observer).health) == dog_health)
	return true


func _pve_prepare_death(
	actor: GameConnection, observer: GameConnection, actor_id: String, sword: Dictionary
) -> bool:
	if not _check(
		"death_scenario_moves_observer_away", await _move_observer_away_from_dog(observer)
	):
		return false
	var dog := _monster(observer)
	actor.move_to(float(dog.x) - 2.35, float(dog.z))
	if not await _wait_until(
		func():
			return (
				_position(_player(observer, actor_id)).distance_to(_position(_monster(observer)))
				<= 2.6
			),
		10.0
	):
		return _check("death_scenario_reaches_dog", false)
	actor.stop_moving()
	actor.unequip_item(int(sword.id), int(sword.cell))
	var unequipped := await _wait_until(
		func():
			return (
				not bool(_owned_sword(actor, actor_id).get("equipped", true))
				and int(observer.appearance_for(actor_id).get("weapon_vnum", -1)) == 0
			)
	)
	return _check("death_scenario_unequips_before_action", unequipped)


func _move_observer_away_from_dog(observer: GameConnection) -> bool:
	var observer_id := observer.local_identity
	var observer_position := _position(_player(observer, observer_id))
	var dog_position := _position(_monster(observer))
	if observer_position.distance_to(dog_position) > 5.0:
		return true
	var away := observer_position - dog_position
	if away.is_zero_approx():
		away = Vector2.LEFT
	var target := observer_position + away.normalized() * 7.0
	observer.move_to(target.x, target.y)
	var separated := await _wait_until(
		func():
			return (
				_position(_player(observer, observer_id)).distance_to(_position(_monster(observer)))
				> 5.0
			),
		10.0
	)
	observer.stop_moving()
	return separated


func _pve_death_cancellation(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	# At 20 HP, start an unarmed action just after the dog's next action starts.
	# The dog hits at 320195us; the unarmed hit is later at 456410us, so death
	# must cancel the player's still-pending hit.
	if not _check(
		"dog_reduces_player_to_last_hit",
		await _wait_until(func(): return int(_player(observer, actor_id).health) == 20, 60.0)
	):
		return false
	var dog_sequence := int(_monster(observer).attack_sequence)
	if not _check(
		"dog_starts_lethal_action",
		await _wait_until(
			func(): return int(_monster(observer).attack_sequence) > dog_sequence, 3.0
		)
	):
		return false
	var dog_health := int(_monster(observer).health)
	var sequence := int(_player(observer, actor_id).attack_sequence)
	actor.perform_attack()
	var unarmed_started := await _wait_until(
		func():
			var row := _player(observer, actor_id)
			return (
				int(row.attack_sequence) > sequence
				and row.attack_action_id == "actor.player.warrior-male.general.normal_attack.v1"
			)
	)
	if not _check("unarmed_pending_action_started", unarmed_started):
		return false
	var player_action := _player(observer, actor_id)
	var dog_action := _monster(observer)
	var dog_hit_at := int(dog_action.action_started_at_us) + 320_195
	var player_hit_at := int(player_action.action_started_at_us) + 456_410
	_check(
		"lethal_hit_is_scheduled_before_player_hit",
		(
			dog_hit_at < player_hit_at
			and observer.server_time_us < dog_hit_at
			and int(dog_action.action_ends_at_us) - int(dog_action.action_started_at_us) == 933_333
		)
	)
	if not _check(
		"authoritative_player_death",
		await _wait_until(func(): return int(_player(observer, actor_id).health) == 0, 2.0)
	):
		return false
	await create_timer(0.35).timeout
	_check("death_cancels_pending_player_hit", int(_monster(observer).health) == dog_health)
	var dead_life := int(_player(observer, actor_id).life_sequence)
	var respawned := await _wait_until(
		func():
			var row := _player(observer, actor_id)
			return (
				int(row.get("health", 0)) == int(row.get("max_health", 0))
				and int(row.get("max_health", 0)) == 760
				and int(row.get("life_sequence", 0)) > dead_life
			),
		10.0
	)
	if not _check("player_respawn_advances_life_generation", respawned):
		return false
	return true


func _pve_reward(
	actor: GameConnection, observer: GameConnection, actor_id: String, safe_position: Vector2
) -> bool:
	# Kill the same dog life with two more frozen sword hits. Its health moves
	# 65 -> 30 -> 0, and one reserved reward row is created and collected once.
	var current_sword := _owned_sword(actor, actor_id)
	actor.equip_item(int(current_sword.id))
	await _wait_until(func(): return bool(_owned_sword(actor, actor_id).get("equipped", false)))
	var dog := _monster(observer)
	actor.move_to(float(dog.x) - 2.35, float(dog.z))
	if not await _wait_until(
		func():
			return (
				_position(_player(observer, actor_id)).distance_to(_position(_monster(observer)))
				<= 2.6
			),
		10.0
	):
		return _check("return_to_dog_after_respawn", false)
	actor.stop_moving()
	var loot_before := observer.loot.size()
	var experience_before := int(actor.progression_for(actor_id).get("experience", -1))
	for expected_health in [30, 0]:
		await create_timer(0.9).timeout
		actor.perform_attack()
		if not _check(
			"sword_hit_reaches_%d_health" % expected_health,
			await _wait_until(func(): return int(_monster(observer).health) == expected_health, 2.0)
		):
			return false
	if not _check(
		"lethal_hit_creates_one_reward",
		await _wait_until(func(): return observer.loot.size() == loot_before + 1)
	):
		return false
	_check(
		"ordinary_wild_dog_grants_exact_experience",
		await _wait_until(_has_experience.bind(actor, actor_id, experience_before + 15))
	)
	await create_timer(0.4).timeout
	_check("death_and_reward_are_exactly_once", observer.loot.size() == loot_before + 1)
	var reward: Dictionary = observer.loot[-1]
	var gold_before := int(_player(observer, actor_id).gold)
	actor.pickup_loot(int(reward.id))
	var reward_collected := await _wait_until(
		func():
			return (
				int(_player(observer, actor_id).gold) == gold_before + 5
				and observer.loot.size() == loot_before
			)
	)
	_check("reserved_reward_collects_once", reward_collected)
	actor.move_to(safe_position.x, safe_position.y)
	var returned := await _wait_until(
		func(): return _position(_player(observer, actor_id)).distance_to(safe_position) < 0.1, 10.0
	)
	return _check("return_to_safe_area_after_pve", returned)


func _mutual_presence(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	return not _player(first, second_id).is_empty() and not _player(second, first_id).is_empty()


func _monster(client: GameConnection) -> Dictionary:
	return client.monsters[0] if not client.monsters.is_empty() else {}


func _valid_warrior(row: Dictionary) -> bool:
	return row.empire == 1 and row.character_class == 0 and row.sex == 0


func _valid_base_appearance(row: Dictionary) -> bool:
	return (
		not row.is_empty()
		and row.size() == 5
		and int(row.get("empire", 0)) == 1
		and int(row.get("character_class", -1)) == 0
		and int(row.get("sex", -1)) == 0
		and int(row.get("weapon_vnum", -1)) == 0
	)


func _private_roster(client: GameConnection, expected_count: int) -> bool:
	var rows := client._client.get_local_database().get_all_rows("account_character")
	return (
		rows.size() == expected_count
		and rows.all(
			func(row: Resource): return row.account.hex_encode() == client.account_identity
		)
	)


func _private_state(client: GameConnection) -> bool:
	var rows := client._client.get_local_database().get_all_rows("account_state")
	return rows.size() == 1 and rows[0].account.hex_encode() == client.account_identity


func _private_access(client: GameConnection, expected_count: int) -> bool:
	var rows := client._client.get_local_database().get_all_rows("inventory_access")
	var owned := client.characters.map(func(row: Dictionary): return str(row.character_id))
	if rows.size() != expected_count:
		return false
	for row: Resource in rows:
		if row.account.hex_encode() != client.account_identity:
			return false
		if row.character_id.hex_encode() not in owned:
			return false
	return true


func _private_inventory(client: GameConnection) -> bool:
	var owned := client.characters.map(func(row: Dictionary): return str(row.character_id))
	var rows := client._client.get_local_database().get_all_rows("inventory_item")
	if rows.is_empty():
		return false
	for row: Resource in rows:
		if row.owner.hex_encode() not in owned:
			return false
		if row.account.hex_encode() != client.account_identity:
			return false
	return true


func _private_progression(client: GameConnection, expected_count: int) -> bool:
	var rows := client._client.get_local_database().get_all_rows("character_progression")
	var owned := client.characters.map(func(row: Dictionary): return str(row.character_id))
	if rows.size() != expected_count:
		return false
	for row: Resource in rows:
		if row.account.hex_encode() != client.account_identity:
			return false
		if row.character_id.hex_encode() not in owned:
			return false
	return true


func _has_experience(client: GameConnection, character_id: String, experience: int) -> bool:
	return int(client.progression_for(character_id).get("experience", -1)) == experience


func _initial_progression(row: Dictionary) -> bool:
	return (
		int(row.get("level", 0)) == 1
		and int(row.get("experience", -1)) == 0
		and int(row.get("next_exp", 0)) == 300
		and int(row.get("level_step", -1)) == 0
		and int(row.get("unspent_stat_points", -1)) == 0
		and int(row.get("strength", 0)) == 6
		and int(row.get("vitality", 0)) == 4
		and int(row.get("dexterity", 0)) == 3
		and int(row.get("intelligence", 0)) == 3
		and int(row.get("random_hp", -1)) == 0
		and int(row.get("random_sp", -1)) == 0
		and int(row.get("current_sp", 0)) == 260
		and int(row.get("max_sp", 0)) == 260
	)


func _owned_sword(client: GameConnection, identity: String) -> Dictionary:
	for row: Dictionary in client.inventory:
		if str(row.owner) == identity and int(row.vnum) == 10:
			return row
	return {}


func _same_character_state(first: Dictionary, second: Dictionary) -> bool:
	for field in ["identity", "name", "x", "y", "z", "health", "max_health", "gold"]:
		if first.get(field) != second.get(field):
			return false
	return true


func _same_inventory(first: Array, second: Array) -> bool:
	var a := first.duplicate(true)
	var b := second.duplicate(true)
	a.sort_custom(func(left: Dictionary, right: Dictionary): return int(left.id) < int(right.id))
	b.sort_custom(func(left: Dictionary, right: Dictionary): return int(left.id) < int(right.id))
	return a == b
