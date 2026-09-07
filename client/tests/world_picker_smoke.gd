extends SceneTree
## Actual physics rays exercise target priority, client-collider occlusion, and stale blocking.

const Picker = preload("res://scripts/world/world_picker.gd")

var _picker := Picker.new()
var _stage: Node3D
var _camera: Camera3D
var _target_body: StaticBody3D
var _target_shape: CollisionShape3D
var _intent := {"target_id": 7, "target_life_sequence": 3}
var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_stage = Node3D.new()
	root.add_child(_stage)
	_camera = Camera3D.new()
	_camera.position = Vector3(0, 2, 5)
	_camera.look_at_from_position(_camera.position, Vector3(0, 0.5, 0))
	_camera.current = true
	_stage.add_child(_camera)
	_add_body("Ground", 1, Vector3(0, -0.15, 0), Vector3(20, 0.2, 20))
	_target_body = _add_body("Target", 2, Vector3(0, 0.5, 0), Vector3.ONE)
	_target_shape = _target_body.get_node("Shape") as CollisionShape3D
	_target_body.set_meta("combat_target_actor", self)
	_target_body.set_meta("target_id", 7)
	_target_body.set_meta("target_life_sequence", 3)
	await physics_frame
	await physics_frame
	var point := root.get_visible_rect().size * 0.5
	var pick := _pick(point)
	_check(
		pick.get("kind") == "target" and pick.get("intent") == _intent,
		"nearest live proxy yields its exact target generation"
	)

	_target_body.position.x = 5.0
	await physics_frame
	pick = _pick(point)
	_check(
		pick.get("kind") == "ground",
		"same stationary pointer is re-evaluated after the actor moves away"
	)

	_target_body.position.x = 0.0
	_intent = {}
	await physics_frame
	pick = _pick(point)
	_check(
		pick.get("kind") == "blocked" and not pick.has("position"),
		"invalid nearest target proxy is never reinterpreted as ground"
	)
	_check(
		_picker.movement_point(pick, Vector3(9, 0, 9)) == null,
		"blocked proxy cannot use the training-plane movement fallback"
	)
	_check(
		_picker.movement_point({}, Vector3(9, 0, 9)) == Vector3(9, 0, 9),
		"a genuinely empty training ray can use the plane fallback"
	)

	_intent = {"target_id": 7, "target_life_sequence": 4}
	await physics_frame
	pick = _pick(point)
	_check(pick.get("kind") == "blocked", "stale collider generation fails closed")
	_target_body.set_meta("target_life_sequence", 4)
	await physics_frame
	_check(_pick(point).get("kind") == "target", "matching new life becomes pickable")

	var blocker := _add_body("ClientOccluder", 1, Vector3(0, 1.25, 2.5), Vector3(2, 2, 0.5))
	await physics_frame
	_check(
		_pick(point).get("kind") == "ground",
		"a nearer real client collider occludes the target proxy"
	)
	blocker.queue_free()
	await physics_frame
	await physics_frame
	_target_shape.disabled = true
	await physics_frame
	_check(_pick(point).get("kind") == "ground", "disabled dead proxy exposes ground behind it")

	if not _failed:
		print("WORLD_PICKER_SMOKE PASS ", _checks, " checks")
	_stage.queue_free()
	await process_frame
	quit(1 if _failed else 0)


func combat_target_intent() -> Dictionary:
	return _intent.duplicate()


func _pick(point: Vector2) -> Dictionary:
	return _picker.pick(_camera, _stage.get_world_3d().direct_space_state, point)


func _add_body(label: String, layer: int, point: Vector3, dimensions: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	body.collision_layer = layer
	body.collision_mask = 0
	body.position = point
	_stage.add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Shape"
	var shape := BoxShape3D.new()
	shape.size = dimensions
	collision.shape = shape
	body.add_child(collision)
	return body


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("WORLD_PICKER_SMOKE FAIL " + description)
