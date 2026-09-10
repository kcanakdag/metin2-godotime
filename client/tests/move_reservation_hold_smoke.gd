extends SceneTree
## A ground-click reservation must clear a stale WASD hold before it issues.
##
## `_physics_process` answers a released WASD hold with `stop_moving`, so a
## `move_to` issued while that flag is still true is cancelled one tick later.
## Browser QA caught the resulting 6 ms `move_to`/`stop_moving` pair freezing an
## outbound walk the native client completed to the same waypoint.

const MainScript := preload("res://scripts/main.gd")
const DESTINATION := Vector3(621.25, 0.0, 666.16)
const ALTERNATE := Vector3(606.0, 0.0, 671.0)


class ConnectionSpy:
	extends GameConnection
	var moves: Array[Vector2] = []
	var stops := 0

	func _process(_delta: float) -> void:
		pass

	func move_to(x: float, z: float) -> void:
		moves.append(Vector2(x, z))

	func stop_moving() -> void:
		stops += 1


class ChargeSpy:
	extends ChargeSkillInput
	var cancels := 0

	func cancel(_stop := false) -> void:
		cancels += 1


class ApproachSpy:
	extends NpcApproach
	var cancels := 0

	func cancel(_stop := false) -> void:
		cancels += 1


class HudSpy:
	extends DevHud

	func _ready() -> void:
		pass

	func wants_keyboard() -> bool:
		return false


class MapSpy:
	extends DevMap

	func _ready() -> void:
		pass


class CameraSpy:
	extends OrbitCamera

	func _init() -> void:
		var camera := Camera3D.new()
		camera.name = "Camera3D"
		add_child(camera)

	func _ready() -> void:
		pass


class HoldMain:
	extends MainScript
	## `_ready` builds the real scene graph, which this isolated harness replaces
	## with spies; everything under test lives in explicit method calls instead.

	func _ready() -> void:
		pass


var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	create_timer(60).timeout.connect(func(): quit(1))
	_run.call_deferred()


func _run() -> void:
	var connection := ConnectionSpy.new()
	connection.name = "GameConnection"
	connection.state = "connected"
	var hud := HudSpy.new()
	hud.name = "DevHud"
	var camera := CameraSpy.new()
	camera.name = "OrbitCamera"
	var world := MapSpy.new()
	world.name = "DevMap"
	var projectiles := Node3D.new()
	projectiles.name = "WorldProjectiles"
	var effects := Node3D.new()
	effects.name = "WorldSkillEffects"
	var main: MainScript = HoldMain.new()
	for child: Node in [connection, hud, camera, world, projectiles, effects]:
		main.add_child(child)
	# The real `_physics_process` needs a Window ancestor for its focus check;
	# every other collaborator is a spy so nothing loads content or opens a socket.
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	main.call("_create_marker")
	var charge := ChargeSpy.new()
	var approach := ApproachSpy.new()
	main.set("_charge_input", charge)
	main.set("_npc_approach", approach)
	var driver: MoveDestination = MoveDestination.attach(main, connection)
	driver.set_process(false)
	main.set("_move_destination", driver)

	# Negative control: an uncleared hold really does cancel the walk, so the
	# assertions below cannot pass for an unrelated reason.
	main.set("_held_movement", true)
	main.call("_physics_process", 0.2)
	_check(
		connection.stops == 1,
		"an uncleared WASD hold cancels the walk on the next physics tick"
	)

	main.set("_held_movement", true)
	main.call("request_move_destination", DESTINATION)
	_check(
		not bool(main.get("_held_movement")),
		"request_move_destination clears the stale WASD hold"
	)
	_check(
		connection.moves == [Vector2(DESTINATION.x, DESTINATION.z)],
		"the clicked destination is issued exactly once"
	)
	main.call("_physics_process", 0.2)
	_check(connection.stops == 1, "the tick after a click sends no stop_moving")
	_check(driver.is_active(), "the reservation stays live through that tick")

	main.call("request_move_destination", ALTERNATE)
	_check(
		(
			connection.moves.size() == 2
			and connection.moves[1] == Vector2(ALTERNATE.x, ALTERNATE.z)
			and connection.stops == 1
		),
		"a second click replaces the destination without a stale stop"
	)
	_check(
		charge.cancels == 2 and approach.cancels == 2,
		"each request releases the charge and approach reservations"
	)

	main.call("request_stop_moving")
	_check(
		(
			connection.stops == 2
			and not bool(main.get("_held_movement"))
			and not driver.is_active()
		),
		"request_stop_moving clears every reservation and the hold flag"
	)
	_check(
		charge.cancels == 3 and approach.cancels == 3,
		"an explicit stop also releases charge and approach"
	)

	var passed := _failures.is_empty()
	if passed:
		print("MOVE_RESERVATION_HOLD_SMOKE PASS ", _checks, " checks")
	else:
		for failure: String in _failures:
			print("MOVE_RESERVATION_HOLD_SMOKE FAIL: ", failure)
	# The spies and marker are plain objects rather than main's children, so
	# release them explicitly before the engine reports shutdown leaks.
	charge.free()
	approach.free()
	main.free()
	quit(0 if passed else 1)


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
