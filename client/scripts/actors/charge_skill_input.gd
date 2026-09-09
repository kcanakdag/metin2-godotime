class_name ChargeSkillInput
extends Node
## Normal skill-input adapter; all movement and damage remain validated reducers.
signal notice(message: String)
var _connection: GameConnection
var _catalog := SkillCatalog.new()
var _approach := ChargeApproach.new()
var _elapsed := 0.0


static func attach(
	parent: Node,
	connection: GameConnection,
	hud: DevHud,
	npc_approach: NpcApproach,
	attack_input: RefCounted
) -> ChargeSkillInput:
	var driver := ChargeSkillInput.new()
	parent.add_child(driver)
	driver.configure(connection)
	driver.notice.connect(hud.show_notice)
	hud.attack_requested.connect(driver.cancel.bind(true))
	hud.disconnect_requested.connect(driver.cancel.bind(true))
	hud.change_character_requested.connect(driver.cancel.bind(true))
	hud.cast_skill_requested.connect(
		func(vnum: int):
			npc_approach.cancel(true)
			attack_input.release()
			if not driver.request(vnum):
				connection.cast_skill(vnum)
	)
	return driver


func configure(connection: GameConnection) -> void:
	_connection = connection
	_catalog.load_required()
	connection.connection_state_changed.connect(_state_changed)
	connection.reducer_completed.connect(_completed)


func request(vnum: int) -> bool:
	var definition := _catalog.definition(vnum)
	if definition.get("handler") != "physical_charge_v1":
		cancel(true)
		return false
	if _approach.phase != "idle":
		return true
	if _connection.state != "connected":
		return true
	var intent := _approach.start(definition, _owner(), _target(), Time.get_ticks_msec())
	if intent.is_empty():
		notice.emit("Select a living target to use this skill.")
		return true
	# A charge may already exist after a cancelled approach. Reuse its paid state.
	if intent != "begin_charge" or _charge().is_empty():
		_send(intent)
	return true


func cancel(stop := false) -> void:
	var active := _approach.phase != "idle"
	_approach.cancel()
	if stop and active and _connection != null and _connection.state == "connected":
		_connection.stop_moving()


func _state_changed(_state: String, _message: String) -> void:
	cancel()


func _completed(reducer: String, succeeded: bool, _timestamp: int) -> void:
	if reducer in ["begin_charge", "cast_skill"]:
		if not succeeded:
			cancel(true)
		else:
			_approach.completed(reducer, succeeded)
	elif reducer == "move_to" and not succeeded:
		cancel(true)


func _process(delta: float) -> void:
	if _approach.phase != "idle" and Input.is_physical_key_pressed(KEY_SPACE):
		cancel(true)
		return
	_elapsed += delta
	if _elapsed < 0.1 or _approach.phase == "idle":
		return
	_elapsed = 0.0
	if _connection.state != "connected":
		cancel()
		return
	_send(
		_approach.advance(
			_owner(),
			_target(),
			_charge(),
			_connection.selected_combat_target(),
			Time.get_ticks_msec()
		)
	)


func _send(intent: String) -> void:
	match intent:
		"begin_charge":
			_connection.begin_charge(_approach.skill_vnum)
		"cast_skill":
			_connection.stop_moving()
			_connection.cast_skill(_approach.skill_vnum)
		"move_to":
			var target := _target()
			if not target.is_empty():
				_connection.move_to(float(target.x), float(target.z))
		"stop":
			_connection.stop_moving()


func _owner() -> Dictionary:
	for row: Dictionary in _connection.players:
		if str(row.identity) == _connection.local_identity:
			return row
	return {}


func _target() -> Dictionary:
	var selected := _connection.selected_combat_target()
	for row: Dictionary in _connection.monsters:
		if int(row.id) == int(selected.get("target_id", 0)):
			return row
	return {}


func _charge() -> Dictionary:
	for row: Dictionary in _connection.charges:
		if (
			str(row.character_id) == _connection.local_identity
			and int(row.skill_vnum) == _approach.skill_vnum
		):
			return row
	return {}
