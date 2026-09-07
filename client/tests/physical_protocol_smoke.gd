extends SceneTree
## Isolated protocol-14 gate check; no generated schema or server is required.

var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_check(GameConnection.EXPECTED_PROTOCOL_VERSION == 14, "client expects protocol 14")
	var legacy := GameConnection.new()
	legacy._session = 1
	legacy.world_info = {"protocol_version": 13}
	legacy._on_subscription_applied(1)
	_check(legacy.state == "error", "protocol 13 is rejected before joining")
	_check(
		legacy.state_message.contains("protocol mismatch"),
		"protocol-13 rejection explains the incompatible client/server contract"
	)
	legacy.queue_free()

	var current := GameConnection.new()
	current._session = 1
	current.world_info = {"protocol_version": 14}
	current._on_subscription_applied(1)
	_check(current.state != "error", "protocol 14 clears the protocol gate")
	current.queue_free()
	if not _failed:
		print("PHYSICAL_PROTOCOL_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _check(passed: bool, description: String) -> void:
	if not passed:
		push_error("PHYSICAL_PROTOCOL_SMOKE FAIL " + description)
		_failed = true
		return
	_checks += 1
