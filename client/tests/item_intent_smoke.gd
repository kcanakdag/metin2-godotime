extends SceneTree
## Real facade payloads carry subscribed revisions without optimistic inventory mutation.

var _checks := 0
var _failed := false


class CapturingConnection:
	extends GameConnection
	var calls: Array = []

	func _call_reducer(
		name: String, args: Array = [], types: Array = [], _joining := false, _lobby := false
	) -> void:
		calls.append({"name": name, "args": args, "types": types})


func _initialize() -> void:
	var client := CapturingConnection.new()
	client.local_identity = "owner"
	client.inventory = [
		{"id": 31, "revision": 8, "owner": "owner", "count": 5},
		{"id": 32, "revision": 2, "owner": "inactive", "count": 1}
	]
	var before := client.inventory.duplicate(true)
	client.move_item(31, 4)
	client.equip_item(31)
	client.unequip_item(31, 7)
	client.use_item(31)
	client.use_item(31)
	_check(client.calls.size() == 5, "five ordinary item intents sent")
	_check(client.calls[0].args == [31, 4, 8], "move includes observed revision")
	_check(client.calls[1].args == [31, 8], "equip includes observed revision")
	_check(client.calls[2].args == [31, 7, 8], "unequip includes observed revision")
	_check(client.calls[3].args == [31, 8], "consume includes observed revision")
	_check(client.calls[3] == client.calls[4], "unacknowledged repeat keeps the same revision")
	_check(client.calls[0].types == [&"U64", &"U8", &"U32"], "move wire types match reducer")
	_check(client.calls[3].types == [&"U64", &"U32"], "consume wire types match reducer")
	client.use_item(0)
	client.use_item(32)
	_check(client.calls.size() == 5, "unavailable and inactive items are not sent by the facade")
	_check(client.inventory == before, "no optimistic count or revision changes")
	client.free()
	if not _failed:
		print("ITEM_INTENT_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _check(passed: bool, description: String) -> void:
	if not passed:
		push_error("ITEM_INTENT_SMOKE FAIL " + description)
		_failed = true
	else:
		_checks += 1
