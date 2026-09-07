extends "res://tests/physical_finisher_smoke.gd"
## Disconnect cancels a captured physical area before activation, without replay.

var _pending_health: Dictionary = {}


func _run() -> void:
	var actor := _make_client()
	var observer := _make_client()
	var ready := await _create_rosters(actor, observer)
	var actor_id := str(actor.characters[0].character_id) if ready else ""
	var observer_id := str(observer.characters[0].character_id) if ready else ""
	if ready:
		ready = await _enter_finisher_fixture(actor, observer, actor_id, observer_id)
	if ready:
		ready = await _park_observer(observer, actor, observer_id)
	if ready:
		ready = await _park_finisher_actor(actor, observer, actor_id)
	if ready:
		ready = await _wait_three_dogs_at_baseline(observer)
	if ready:
		ready = await _equip_combo_sword(actor, observer, actor_id)
	if ready:
		ready = await _start_pending_disconnect(actor, observer, actor_id)
	if not ready:
		_check("physical_pending_lifecycle_completed", false)
	_tokens.clear()
	_finish()


func _start_pending_disconnect(
	actor: GameConnection, observer: GameConnection, actor_id: String
) -> bool:
	if not await _stage_first_whiff(actor, observer, actor_id):
		return false
	var first_half := await _start_finisher_chain(actor, observer, actor_id)
	if first_half.is_empty():
		return false
	var fourth := await _finish_finisher_chain(actor, observer, actor_id, first_half.second)
	if fourth.is_empty():
		return false
	for id in [1, 2, 3]:
		_pending_health[id] = _monster_by_id(observer, id).duplicate(true)
	return await _disconnect_pending_area(actor, observer, actor_id, fourth)


func _disconnect_pending_area(
	actor: GameConnection, observer: GameConnection, actor_id: String, fourth: Dictionary
) -> bool:
	var started := int(fourth.action_started_at_us)
	if not _check(
		"physical_pending_disconnect_window",
		await _wait_for_estimated_action_time(
			observer, started, 220_000, 290_000, 300_000, "physical_pending_disconnect"
		)
	):
		return false
	var before_position := _position(_player(observer, actor_id))
	var before_sequence := int(fourth.attack_sequence)
	actor.disconnect_game()
	if not _check(
		"physical_pending_disconnect_removes_presence",
		await _wait_until(func(): return _player(observer, actor_id).is_empty(), 5.0)
	):
		return false
	var removed_at := observer.server_time_us
	(
		_timing_evidence
		. append(
			{
				"phase": "physical_pending_disconnect",
				"action_started_at_us": started,
				"activation_at_us": started + 666_667,
				"presence_removed_clock_us": removed_at,
				"before_health": _pending_health.duplicate(true),
			}
		)
	)
	if not _check("physical_presence_removed_before_area", removed_at < started + 666_667):
		return false
	if not _check(
		"physical_observer_reaches_expired_area",
		await _wait_server_time(observer, started + 1_466_667)
	):
		return false
	if not _check(
		"physical_pending_area_has_no_damage_or_force", _unchanged_pending_victims(observer)
	):
		return false
	return await _reenter_without_pending_replay(
		actor, observer, actor_id, before_position, before_sequence
	)


func _unchanged_pending_victims(client: GameConnection) -> bool:
	for id in [1, 2, 3]:
		var before: Dictionary = _pending_health[id]
		var current := _monster_by_id(client, id)
		if (
			current.is_empty()
			or int(current.health) != int(before.health)
			or int(current.life_sequence) != int(before.life_sequence)
			or (
				str(current.attack_action_id)
				in [FINISHER_FRONT_KNOCKDOWN, FINISHER_FRONT_STANDUP, FINISHER_BACK_KNOCKDOWN]
			)
		):
			return false
	return true


func _reenter_without_pending_replay(
	actor: GameConnection,
	observer: GameConnection,
	actor_id: String,
	before_position: Vector2,
	before_sequence: int
) -> bool:
	actor.connect_account(_server, _database, str(_tokens[0]), "physical-pending-reconnect")
	if not _check(
		"physical_pending_reconnect_returns_lobby",
		await _wait_until(func(): return actor.state == "lobby", 20.0)
	):
		return false
	actor.enter_selected()
	if not _check(
		"physical_pending_reconnect_restores_presence",
		await _wait_until(
			func():
				return actor.state == "connected" and not _player(observer, actor_id).is_empty(),
			20.0
		)
	):
		return false
	if not _check(
		"physical_pending_reconnect_has_no_root_catchup",
		(
			_position(_player(observer, actor_id)).distance_to(before_position)
			<= ROOT_DISCONNECT_SAMPLE_TOLERANCE_M
		)
	):
		return false
	if not await _park_finisher_actor(actor, observer, actor_id):
		return false
	var parked := _position(_player(observer, actor_id))
	await create_timer(1.3).timeout
	return _check(
		"physical_pending_reconnect_has_no_action_damage_or_force_replay",
		(
			int(_player(observer, actor_id).attack_sequence) == before_sequence
			and (
				_position(_player(observer, actor_id)).distance_to(parked)
				<= ROOT_POSITION_TOLERANCE_M
			)
			and _unchanged_pending_victims(actor)
			and _unchanged_pending_victims(observer)
		)
	)
