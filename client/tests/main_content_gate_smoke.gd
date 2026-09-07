extends SceneTree
## Isolated Main gate checks with normal catalog failures and narrow UI/network spies.

const MainScript := preload("res://scripts/main.gd")


class ConnectionSpy:
	extends GameConnection
	var disconnects := 0
	var world_entries := 0

	func disconnect_game() -> void:
		disconnects += 1

	func enter_loaded_world() -> void:
		world_entries += 1


class HudSpy:
	extends DevHud
	var notices: Array[String] = []

	func _ready() -> void:
		pass

	func show_notice(message: String) -> void:
		notices.append(message)


class FailingEffectCatalog:
	extends TargetEffectCatalog
	var failure := ""

	func load_required(_path := CATALOG_PATH) -> bool:
		loaded = false
		error_message = failure
		return false


var _checks := 0
var _failed := false


func _initialize() -> void:
	_test_failure("Required target-effect catalog is missing.", "missing")
	_test_failure("Required target-effect catalog is not valid JSON.", "invalid")
	if not _failed:
		print("MAIN_CONTENT_GATE_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _test_failure(message: String, label: String) -> void:
	var main := MainScript.new()
	var connection := ConnectionSpy.new()
	var hud := HudSpy.new()
	var catalog := FailingEffectCatalog.new()
	catalog.failure = message
	main.connection = connection
	main.hud = hud
	main.set("_target_effect_catalog", catalog)
	var actor_catalog: ActorCatalog = main.get("_actor_catalog")
	_check(actor_catalog.load_required(), "%s case loads the required actor catalog" % label)
	(
		main
		. call(
			"_prepare_world",
			{
				"map_id": "training",
				"definition_profile": ActorCatalog.PROFILE_ID,
				"definition_hash": actor_catalog.gameplay_definition_hash(),
			}
		)
	)
	_check(connection.disconnects == 1, "%s target effects disconnect content loading" % label)
	_check(connection.world_entries == 0, "%s target effects cannot enter the world" % label)
	_check(hud.notices == [message], "%s target-effect error remains visible" % label)
	main.free()
	connection.free()
	hud.free()


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("MAIN_CONTENT_GATE_SMOKE FAIL " + description)
