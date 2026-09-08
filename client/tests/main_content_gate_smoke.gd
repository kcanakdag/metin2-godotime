extends SceneTree
## Isolated Main gate checks with normal catalog failures and narrow UI/network spies.

const MainScript := preload("res://scripts/main.gd")


class WaveCatalog:
	extends ActorCatalog

	# Synthetic wave on real registered motions tests routing independently of
	# which original events have been adapted by the content compiler.
	func motion(actor_id: String, mode_id: String, action_id := "", action := "") -> Dictionary:
		var result := super.motion(actor_id, mode_id, action_id, action).duplicate(true)
		if not result.is_empty():
			result.screen_wave = {
				"activation_offset_us": 100000, "duration_us": 200000, "viewer_range_m": 2.0
			}
		return result


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
	_test_screen_wave_setting_round_trip()
	_test_class_wave_dispatch()
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
				"skill_catalog_hash": actor_catalog.skills.content_hash,
			}
		)
	)
	_check(connection.disconnects == 1, "%s target effects disconnect content loading" % label)
	_check(connection.world_entries == 0, "%s target effects cannot enter the world" % label)
	_check(hud.notices == [message], "%s target-effect error remains visible" % label)
	main.free()
	connection.free()
	hud.free()


func _test_screen_wave_setting_round_trip() -> void:
	var path := "user://screen-wave-setting-smoke.json"
	var writer := MainScript.new()
	writer.set("_settings_path", path)
	(
		writer
		. set(
			"_settings",
			{
				"server_url": "http://127.0.0.1:3000",
				"database": "settings-smoke",
				"player_name": "Accessibility",
				"screen_wave_enabled": false,
			}
		)
	)
	writer.call("_save_settings")
	var reader := MainScript.new()
	(
		reader
		. set(
			"_settings",
			{
				"server_url": "default",
				"database": "default",
				"player_name": "default",
				"screen_wave_enabled": true,
			}
		)
	)
	reader.call("_merge_config", path)
	var restored: Dictionary = reader.get("_settings")
	_check(
		(
			restored.server_url == "http://127.0.0.1:3000"
			and restored.database == "settings-smoke"
			and restored.player_name == "Accessibility"
			and not restored.screen_wave_enabled
		),
		"screen-wave accessibility preference survives a settings reload",
	)
	writer.free()
	reader.free()


func _test_class_wave_dispatch() -> void:
	var main := MainScript.new()
	var connection := ConnectionSpy.new()
	var camera := OrbitCamera.new()
	var catalog := WaveCatalog.new()
	_check(catalog.load_required(), "wave dispatch loads all installed class definitions")
	main.connection = connection
	main.camera_rig = camera
	main.set("_actor_catalog", catalog)
	connection.state = "connected"
	connection.local_identity = "viewer"
	for definition: Dictionary in catalog.characters.classes:
		for variant: Dictionary in definition.variants:
			var appearance := {
				"character_id": "attacker",
				"character_class": definition.class_id,
				"sex": variant.sex
			}
			connection.appearances = [appearance]
			var mode := "fan" if int(definition.class_id) == 3 else "onehand"
			var row := {
				"identity": "attacker",
				"online": true,
				"activity": 2,
				"attack_action_id": str(variant.actor_id) + "." + mode + ".combo_4",
				"attack_sequence": 1,
				"attack_speed_percent": 122,
				"action_started_at_us": 1000000,
				"action_ends_at_us": 2000000,
				"x": 0.0,
				"y": 0.0,
				"z": 0.0,
			}
			main.set(
				"_player_rows",
				[{"identity": "viewer", "online": true, "x": 0.0, "y": 0.0, "z": 0.0}, row]
			)
			camera.reset_screen_waves()
			main.call("_observe_screen_waves", 1000000)
			main.call("_observe_screen_waves", 1081967)
			_check(
				camera.screen_wave_snapshot().trigger_count == 0,
				"scaled camera event does not fire early"
			)
			main.call("_observe_screen_waves", 1081968)
			_check(
				(
					camera.screen_wave_snapshot().trigger_count == 1
					and camera.screen_wave_snapshot().activation_us == 1081968
					and camera.screen_wave_snapshot().duration_us == 200000
				),
				"remote wave resolves its own appearance: " + str(variant.actor_id)
			)
			main.call("_observe_screen_waves", 1081968)
			_check(
				(
					camera.screen_wave_snapshot().trigger_count == 1
					and camera.screen_wave_snapshot().activation_us == 1081968
					and camera.screen_wave_snapshot().duration_us == 200000
				),
				"repeated class observation does not replay the wave"
			)
			camera.reset_screen_waves()
			connection.appearances = []
			main.call("_observe_screen_waves", 1081968)
			_check(
				camera.screen_wave_snapshot().trigger_count == 0,
				"missing appearance cannot borrow a Warrior event"
			)
	main.free()
	connection.free()
	camera.free()


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("MAIN_CONTENT_GATE_SMOKE FAIL " + description)
