extends RefCounted
## Original selected flight kinematics in metres. Hit events are visual only.

const Motion = preload("res://scripts/actors/particle_motion.gd")
var position := Vector3.ZERO
var velocity := Vector3.ZERO
var acceleration := Vector3.ZERO
var orientation := Quaternion.IDENTITY
var remaining_range := 0.0
var elapsed := 0.0
var alive := false
var _definition: Dictionary = {}
var _pierces := 0
var _hit_target := false


func configure(definition: Dictionary, start: Vector3, target: Vector3) -> bool:
	# Definitions are imported content. Spreading and secondary collision policies
	# need separate implementations; none of the four selected flight scripts uses them.
	if not start.is_finite() or not target.is_finite() or start.is_equal_approx(target):
		return false
	for flag: String in ["SpreadingFlag", "HitOnBackground", "HitOnAnotherMonster"]:
		if bool(definition[flag]):
			return false
	for field: String in [
		"InitialVelocity",
		"Range",
		"BombRange",
		"HomingStartTime",
		"HomingMaxAngle",
		"Gravity",
		"ConeAngle",
		"RollAngle"
	]:
		var value := float(definition[field])
		if not is_finite(value) or absf(value) > 1000000:
			return false
	if (
		definition.InitialVelocity <= 0
		or definition.Range <= 0
		or definition.BombRange < 0
		or definition.HomingStartTime < 0
	):
		return false
	var accel := Motion.source_vector(definition.Acceleration)
	var aim := target + (Vector3.UP * 0.5 if definition.MaintainParallelFlag else Vector3.ZERO)
	if not accel.is_finite() or start.is_equal_approx(aim):
		return false
	var base := (
		Quaternion(Vector3.FORWARD, deg_to_rad(float(definition.RollAngle) - 90))
		* Quaternion(Vector3.UP, deg_to_rad(float(definition.ConeAngle)))
	)
	orientation = (_arc(Vector3.BACK, (aim - start).normalized()) * base).normalized()
	position = start
	velocity = orientation * Vector3.BACK * float(definition.InitialVelocity) * 0.01
	acceleration = orientation * accel
	remaining_range = float(definition.Range) * 0.01
	elapsed = 0.0
	_pierces = int(definition.PierceCount)
	_hit_target = false
	_definition = definition.duplicate(true)
	alive = true
	return true


func advance(delta: float, target: Vector3, object_target: bool = true) -> Dictionary:
	if not is_finite(delta) or delta <= 0 or delta > 1 or not target.is_finite():
		return {"error": "Invalid projectile step"}
	if _definition.is_empty():
		return {"error": "Unconfigured projectile"}
	if not alive:
		return {"event": "inactive", "position": position}
	elapsed += delta
	if _definition.HomingFlag and object_target and elapsed > float(_definition.HomingStartTime):
		_home(target)
	var previous := position
	velocity += acceleration * delta
	velocity.y += float(_definition.Gravity) * 0.01 * delta
	var movement := velocity * delta
	remaining_range -= movement.length()
	position += movement
	var event := "flying"
	if remaining_range < 0:
		alive = false
		event = "out_of_range"
	elif not _hit_target or not object_target:
		var distance := _segment_distance_squared(previous, position, target)
		if distance < pow(float(_definition.BombRange) * 0.01, 2):
			event = "target_hit"
			_hit_target = true
			if object_target and _pierces > 0:
				_pierces -= 1
			else:
				alive = false
	return {"event": event, "position": position, "previous_position": previous}


func _home(target: Vector3) -> void:
	var direction := target - position
	if direction.is_zero_approx() or velocity.is_zero_approx():
		return
	direction = direction.normalized()
	var current := velocity.normalized()
	if current.distance_squared_to(direction) < 0.001:
		return
	var turn := _arc(current, direction)
	var angle := float(_definition.HomingMaxAngle)
	if angle <= 180:
		var cosine := cos(deg_to_rad(angle))
		var sine := sin(deg_to_rad(angle))
		if turn.w <= -1.0 + 0.0001:
			turn = Quaternion(0, sine, 0, cosine)
		elif turn.w <= cosine and turn.w <= 1.0 - 0.0001:
			var factor := sine / sqrt(1.0 - turn.w * turn.w)
			turn = Quaternion(turn.x * factor, turn.y * factor, turn.z * factor, cosine)
	velocity = turn * velocity
	acceleration = turn * acceleration
	# D3DX's operand order maps differently in the source's >180-degree branch.
	orientation = ((orientation * turn) if angle > 180 else (turn * orientation)).normalized()


static func _arc(from: Vector3, to: Vector3) -> Quaternion:
	if from == to:
		return Quaternion.IDENTITY
	if from == -to:
		return Quaternion(Vector3.UP, PI)
	return Quaternion(from, to).normalized()


static func _segment_distance_squared(start: Vector3, end: Vector3, point: Vector3) -> float:
	var segment := end - start
	if segment.is_zero_approx():
		return start.distance_squared_to(point)
	var weight := clampf((point - start).dot(segment) / segment.length_squared(), 0, 1)
	return (start + segment * weight).distance_squared_to(point)
