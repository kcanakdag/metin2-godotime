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
	elif str(_config.mode) == "skills":
		await _verify_skills(first, second)
	elif str(_config.mode) == "training_dummy":
		await _verify_training_dummy(first, second)
	elif (
		str(_config.mode)
		in [
			"skill_reactions",
			"skill_batch",
			"charge",
			"buff",
			"charge_strike",
			"crush",
			"crush_death",
			"crush_overlap",
			"charge_input",
			"charge_moving"
		]
	):
		await _verify_skill_reactions(first, second)
	elif str(_config.mode) == "three_way_cut":
		await _verify_three_way_cut(first, second)
	elif str(_config.mode) == "skill_combat":
		await _verify_skill_combat(first, second)
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


func _verify_skills(first: GameConnection, second: GameConnection) -> void:
	var denied := _request_id()
	second.admin_set_skill(denied, "2 20")
	_check(
		"skill_grant_requires_permission",
		await _feedback_contains(second, denied, "operator permission")
	)
	_check(
		"below_level_five_cannot_learn",
		not await _raw_success(first, "learn_skill", [2, 0], [&"U16", &"U32"])
	)
	var level := _request_id()
	first.admin_raise_progression_level(level, "5")
	if not _check(
		"level_five_unlock",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 5)
	):
		return
	_check("learn_first_rank", await _raw_success(first, "learn_skill", [2, 0], [&"U16", &"U32"]))
	if not _check(
		"learned_rank_subscribed", await _wait_until(func(): return first.skill_revision(2) == 1)
	):
		return
	_check("first_rank_spends_one_point", int(first.selected_skills()[0].points_spent) == 1)
	_check(
		"stale_learning_rejected",
		not await _raw_success(first, "learn_skill", [2, 0], [&"U16", &"U32"])
	)
	_check(
		"overspending_rejected",
		not await _raw_success(first, "learn_skill", [2, 1], [&"U16", &"U32"])
	)
	_check(
		"unknown_skill_rejected",
		not await _raw_success(first, "learn_skill", [255, 0], [&"U16", &"U32"])
	)
	_check("observer_cannot_read_learned_skills", second.skills.is_empty())
	var sword := 0
	for item: Dictionary in first.inventory:
		if int(item.vnum) == 10:
			sword = int(item.id)
	if not _check("starter_sword_available", sword != 0):
		return
	first.equip_item(sword)
	if not _check(
		"sword_equipped",
		await _wait_until(
			func():
				return first.inventory.any(
					func(item): return int(item.id) == sword and bool(item.equipped)
				),
			8.0
		)
	):
		return
	var before_sp := int(first.selected_progression().current_sp)
	_check("skill_cast_accepted", await _raw_success(first, "cast_skill", [2, 1], [&"U16", &"U32"]))
	if not _check(
		"cast_revision_subscribed", await _wait_until(func(): return first.skill_revision(2) == 2)
	):
		return
	var ready := int(first.selected_skills()[0].ready_at_us)
	_check(
		"original_rank_one_sp_cost", int(first.selected_progression().current_sp) == before_sp - 56
	)
	_check(
		"observer_receives_skill_action",
		await _wait_until(
			func():
				return _player_action(second, first.local_identity).ends_with(".general.skill_2"),
			8.0
		)
	)
	_check(
		"cast_replay_rejected",
		not await _raw_success(first, "cast_skill", [2, 1], [&"U16", &"U32"])
	)
	_check(
		"cooldown_recast_rejected",
		not await _raw_success(first, "cast_skill", [2, 2], [&"U16", &"U32"])
	)
	await create_timer(1.05).timeout
	var grant := _request_id()
	first.admin_set_skill(grant, "2 20")
	_check("authorized_rank_update", await _wait_until(func(): return first.skill_revision(2) == 3))
	_check("rank_twenty_subscribed", int(first.selected_skills()[0].rank) == 20)
	_check("rank_update_preserves_cooldown", int(first.selected_skills()[0].ready_at_us) == ready)
	_check("admin_refunds_invested_points", int(first.selected_skills()[0].points_spent) == 0)
	first.admin_set_skill(grant, "2 20")
	await create_timer(0.3).timeout
	_check("admin_replay_does_not_mutate_rank", first.skill_revision(2) == 3)
	var identity := first.local_identity
	first.disconnect_game()
	_check(
		"observer_sees_disconnect",
		await _wait_until(
			func():
				return not second.players.any(
					func(row): return str(row.identity) == identity and bool(row.online)
				),
			8.0
		)
	)
	first.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[0]), "skill-reconnect"
	)
	if not _check(
		"skill_account_reconnects", await _wait_until(func(): return first.state == "lobby", 20.0)
	):
		return
	first.select_character(identity)
	_check(
		"learned_skill_survives_reconnect",
		await _wait_until(func(): return first.skill_revision(2) == 3)
	)
	_check("reconnect_preserves_cooldown", int(first.selected_skills()[0].ready_at_us) == ready)
	_check("reconnect_keeps_skills_private", second.skills.is_empty())


func _verify_skill_combat(first: GameConnection, second: GameConnection) -> void:
	var level := _request_id()
	first.admin_raise_progression_level(level, "6")
	if not _check(
		"combat_fixture_level_six",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 6)
	):
		return
	_check(
		"mutual_presence",
		(
			not _player_row(first, second.local_identity).is_empty()
			and not _player_row(second, first.local_identity).is_empty()
		)
	)
	var observer_start := _xz(_player_row(first, second.local_identity))
	second.move_to(observer_start.x + 1.0, observer_start.y)
	_check(
		"observer_movement_replicates",
		await _wait_until(
			func():
				return (
					_xz(_player_row(first, second.local_identity)).distance_to(observer_start) > 0.5
				),
			8.0
		)
	)
	second.stop_moving()
	if not _check(
		"mobs_subscribed", await _wait_until(func(): return not second.monsters.is_empty())
	):
		return
	var dog_id := int(second.monsters_for_definition(101)[0].id)
	var start := _xz(_player_row(second, first.local_identity))
	for _attempt in 120:
		var dog := _dog(second, dog_id)
		var owner := _xz(_player_row(second, first.local_identity))
		if owner.distance_to(_xz(dog)) <= 1.5:
			break
		var destination := _xz(dog) + (owner - _xz(dog)).normalized()
		first.move_to(destination.x, destination.y)
		await create_timer(0.2).timeout
	first.stop_moving()
	_check(
		"caster_movement_replicates",
		_xz(_player_row(second, first.local_identity)).distance_to(start) > 1.0
	)
	if not _check(
		"caster_reaches_dog",
		_xz(_player_row(second, first.local_identity)).distance_to(_xz(_dog(second, dog_id))) <= 1.5
	):
		return
	var before := _dog(second, dog_id).duplicate(true)
	_check(
		"damaging_cast_accepted",
		await _raw_success(first, "cast_skill", [2, first.skill_revision(2)], [&"U16", &"U32"])
	)
	_check(
		"skill_damage_replicates_to_both",
		await _wait_until(
			func():
				return (
					int(_dog(second, dog_id).health) < int(before.health)
					and _dog(first, dog_id).health == _dog(second, dog_id).health
				),
			8.0
		)
	)
	var after := _dog(second, dog_id).duplicate(true)
	await create_timer(1.1).timeout
	_check(
		"one_hit_per_monster_life",
		(
			_dog(second, dog_id).health == after.health
			and _dog(second, dog_id).life_sequence == after.life_sequence
		)
	)
	first.move_to(start.x, start.y)
	_check(
		"caster_returns_after_skill",
		await _wait_until(
			func(): return _xz(_player_row(second, first.local_identity)).distance_to(start) < 0.25,
			25.0
		)
	)
	first.stop_moving()


func _verify_training_dummy(first: GameConnection, second: GameConnection) -> void:
	var dummy_id := 900001
	if not _check(
		"dummy_subscribed_to_both",
		await _wait_until(
			func():
				return (
					not _dog(first, dummy_id).is_empty() and not _dog(second, dummy_id).is_empty()
				),
			8.0
		)
	):
		return
	var before := _dog(second, dummy_id).duplicate(true)
	_check("bounded_training_fixture", int(before.max_health) == 600)
	if int(first.selected_progression().get("level", 0)) < 5:
		first.admin_raise_progression_level(_request_id(), "5")
	if not _check(
		"dummy_skill_fixture_level_five",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) == 5)
	):
		return
	if first.skill_revision(2) == 0:
		_check(
			"learn_skill_for_dummy",
			await _raw_success(first, "learn_skill", [2, 0], [&"U16", &"U32"])
		)
	_check(
		"dummy_skill_rank_subscribed", await _wait_until(func(): return first.skill_revision(2) > 0)
	)
	var cast_revision := first.skill_revision(2)
	var swords := first.inventory.filter(func(item): return int(item.vnum) == 10)
	if not _check("dummy_starter_sword_available", swords.size() == 1):
		return
	var sword_id := int(swords[0].id)
	first.equip_item(sword_id)
	if not _check(
		"dummy_sword_equipped",
		await _wait_until(
			func():
				return first.inventory.any(
					func(item): return int(item.id) == sword_id and bool(item.equipped)
				),
			8.0
		)
	):
		return
	var observer_start := _xz(_player_row(first, second.local_identity))
	second.move_to(observer_start.x - 1.0, observer_start.y)
	_check(
		"dummy_observer_movement_replicates",
		await _wait_until(
			func():
				return (
					_xz(_player_row(first, second.local_identity)).distance_to(observer_start) > 0.5
				),
			8.0
		)
	)
	second.stop_moving()
	var destination := _xz(before) + Vector2(-1.0, 0.0)
	first.move_to(destination.x, destination.y)
	if not _check(
		"dummy_caster_movement_replicates",
		await _wait_until(
			func():
				return _xz(_player_row(second, first.local_identity)).distance_to(destination) < 0.2,
			8.0
		)
	):
		return
	first.stop_moving()
	_check(
		"dummy_exact_life_target_accepted",
		await _raw_success(
			first, "select_combat_target", [dummy_id, before.life_sequence], [&"U32", &"U32"]
		)
	)
	_check(
		"dummy_forged_life_rejected",
		not await _raw_success(
			first,
			"select_combat_target",
			[dummy_id, int(before.life_sequence) + 1],
			[&"U32", &"U32"]
		)
	)
	var experience := int(first.selected_progression().experience)
	var gold := int(_player_row(first, first.local_identity).gold)
	var potions := _potion_count(first, 27001)
	var loot_count := second.loot.size()
	var item_count := second.item_drops.size()
	_check(
		"dummy_skill_cast_accepted",
		await _raw_success(first, "cast_skill", [2, cast_revision], [&"U16", &"U32"])
	)
	_check(
		"dummy_skill_damage_replicates",
		await _wait_until(
			func():
				return (
					int(_dog(second, dummy_id).health) < int(before.health)
					and _dog(first, dummy_id).health == _dog(second, dummy_id).health
				),
			8.0
		)
	)
	_check(
		"dummy_cast_replay_rejected",
		not await _raw_success(first, "cast_skill", [2, cast_revision], [&"U16", &"U32"])
	)
	await create_timer(2.1).timeout
	var after_skill := int(_dog(second, dummy_id).health)
	first.move_to(destination.x, destination.y)
	await _wait_until(
		func():
			return _xz(_player_row(second, first.local_identity)).distance_to(destination) < 0.2,
		8.0
	)
	first.stop_moving()
	for _attempt in 60:
		if int(_dog(second, dummy_id).health) == 0:
			break
		_check(
			"dummy_melee_action_accepted_%d" % _attempt,
			await _raw_success(first, "perform_attack", [], [])
		)
		await create_timer(1.4).timeout
	var defeated := _dog(second, dummy_id).duplicate(true)
	_check("dummy_melee_damage_replicates", int(defeated.health) < after_skill)
	_check("dummy_can_be_defeated", int(defeated.health) == 0)
	_check("dummy_stays_anchored", _xz(defeated) == _xz(before))
	_check("dummy_does_not_attack", int(defeated.attack_sequence) == 0)
	_check("dummy_has_no_xp_reward", int(first.selected_progression().experience) == experience)
	_check("dummy_has_no_gold_reward", int(_player_row(first, first.local_identity).gold) == gold)
	_check(
		"dummy_has_no_item_reward",
		(
			_potion_count(first, 27001) == potions
			and second.loot.size() == loot_count
			and second.item_drops.size() == item_count
		)
	)
	_check(
		"dummy_respawns_new_life",
		await _wait_until(
			func():
				return (
					int(_dog(second, dummy_id).life_sequence) == int(before.life_sequence) + 1
					and int(_dog(second, dummy_id).health) == 600
				),
			8.0
		)
	)
	_check(
		"dummy_previous_life_rejected",
		not await _raw_success(
			first, "select_combat_target", [dummy_id, before.life_sequence], [&"U32", &"U32"]
		)
	)
	var identity := first.local_identity
	first.disconnect_game()
	_check(
		"dummy_observer_sees_disconnect",
		await _wait_until(
			func(): return not bool(_player_row(second, identity).get("online", false)), 8.0
		)
	)
	first.connect_account(
		str(_config.server), str(_config.database), str(_config.tokens[0]), "dummy-reconnect"
	)
	if not _check(
		"dummy_account_reconnects", await _wait_until(func(): return first.state == "lobby", 20.0)
	):
		return
	first.select_character(identity)
	await _wait_until(func(): return first.local_identity == identity)
	first.enter_selected()
	_check(
		"dummy_reconnect_resubscribes",
		await _wait_until(
			func(): return first.state == "connected" and not _dog(first, dummy_id).is_empty(), 8.0
		)
	)
	await create_timer(2.1).timeout
	_check("dummy_reconnect_does_not_replay_damage", int(_dog(second, dummy_id).health) == 600)


func _xz(row: Dictionary) -> Vector2:
	return Vector2(float(row.get("x", 0)), float(row.get("z", 0)))


func _dog(client: GameConnection, id: int) -> Dictionary:
	for row: Dictionary in client.monsters:
		if int(row.id) == id:
			return row
	return {}


func _player_row(client: GameConnection, identity: String) -> Dictionary:
	for row: Dictionary in client.players:
		if str(row.identity) == identity:
			return row
	return {}


func _player_action(client: GameConnection, identity: String) -> String:
	for row: Dictionary in client.players:
		if str(row.identity) == identity:
			return str(row.attack_action_id)
	return ""


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
			if response.reducer_result.value == ReducerOutcomeEnum.Options.err:
				print("REDUCER_REJECTION ", reducer, " ", response.reducer_result.get_err())
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
	for error in _errors:
		printerr("SMOKE_ERROR ", error)
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


func _prepare_three_way_cut(first: GameConnection) -> bool:
	first.admin_raise_progression_level(_request_id(), "5")
	if not _check(
		"three_way_level_five",
		await _wait_until(func(): return int(first.selected_progression().get("level", 0)) >= 5)
	):
		return false
	_check("three_way_learn", await _raw_success(first, "learn_skill", [1, 0], [&"U16", &"U32"]))
	if not _check(
		"three_way_rank_subscribed", await _wait_until(func(): return first.skill_revision(1) > 0)
	):
		return false
	var swords := first.inventory.filter(func(item): return int(item.vnum) == 10)
	if not _check("three_way_sword_available", swords.size() == 1):
		return false
	var sword_id := int(swords[0].id)
	first.equip_item(sword_id)
	if not _check(
		"three_way_sword_equipped",
		await _wait_until(func(): return _has_equipped_item(first, sword_id))
	):
		return false
	return true


func _verify_three_way_cut(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_three_way_cut(first):
		return
	var revision := first.skill_revision(1)
	var sp := int(first.selected_progression().current_sp)
	_check(
		"three_way_missing_target_rejects",
		not await _raw_success(first, "cast_skill", [1, revision], [&"U16", &"U32"])
	)
	_check(
		"three_way_rejection_preserves_sp_and_revision",
		int(first.selected_progression().current_sp) == sp and first.skill_revision(1) == revision
	)
	if not _check(
		"three_way_dummy_subscribed",
		await _wait_until(func(): return not _dog(second, 900001).is_empty())
	):
		return
	var dummy := _dog(second, 900001).duplicate(true)
	var destination := _xz(dummy) + Vector2(-2.0, 0.0)
	first.move_to(destination.x, destination.y)
	if not _check(
		"three_way_approach_replicates",
		await _wait_until(
			func():
				return (
					_xz(_player_row(second, first.local_identity)).distance_to(destination) < 0.15
				),
			15.0
		)
	):
		return
	first.stop_moving()
	_check(
		"three_way_stale_life_rejects",
		not await _raw_success(
			first, "select_combat_target", [900001, int(dummy.life_sequence) + 1], [&"U32", &"U32"]
		)
	)
	_check(
		"three_way_target_accepted",
		await _raw_success(
			first, "select_combat_target", [900001, dummy.life_sequence], [&"U32", &"U32"]
		)
	)
	if not _check(
		"three_way_cast_accepted",
		await _raw_success(first, "cast_skill", [1, revision], [&"U16", &"U32"])
	):
		return
	var histories: Array = [[int(dummy.health)], [int(dummy.health)]]
	for _tick in 90:
		for index in 2:
			var connection := first if index == 0 else second
			var health := int(_dog(connection, 900001).health)
			if health != int(histories[index][-1]):
				histories[index].append(health)
		await create_timer(0.02).timeout
	_check(
		"three_way_three_hits_each_client", histories[0].size() == 4 and histories[1].size() == 4
	)
	_check("three_way_identical_health_history", histories[0] == histories[1])
	_check(
		"three_way_same_dummy_life",
		(
			_dog(first, 900001).life_sequence == dummy.life_sequence
			and _dog(second, 900001).life_sequence == dummy.life_sequence
		)
	)
	_check(
		"three_way_faces_target",
		absf(float(_player_row(second, first.local_identity).heading) + PI / 2.0) < 0.1
	)
	_check(
		"three_way_replay_rejects",
		not await _raw_success(first, "cast_skill", [1, revision], [&"U16", &"U32"])
	)
	_check(
		"three_way_cooldown_rejects",
		not await _raw_success(first, "cast_skill", [1, first.skill_revision(1)], [&"U16", &"U32"])
	)


func _has_equipped_item(connection: GameConnection, item_id: int) -> bool:
	for item in connection.inventory:
		if int(item.id) == item_id and bool(item.equipped):
			return true
	return false


func _verify_skill_reactions(_first: GameConnection, _second: GameConnection) -> void:
	_check("specialized_reaction_fixture_loaded", false)
