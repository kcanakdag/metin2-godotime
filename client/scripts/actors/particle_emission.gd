extends RefCounted
## Presentation-only emission lifecycle, using the imported original timing rules.
## A renderer owns geometry; this component returns births/deaths with stable IDs.

var _emitter: Dictionary = {}
var _remaining: Dictionary = {}
var _delay := 0.0
var _started := false
var _time := 0.0
var _loops := 0
var _residue := 0.0
var _next_id := 0
var _finished := false


func configure(system: Dictionary) -> bool:
	var emitter: Variant = system.get("emitter")
	var delay: Variant = system.get("start_seconds")
	if not emitter is Dictionary or not _number(delay, 0.0, 3600.0):
		return false
	for field: String in ["MaxEmissionCount", "LoopCount", "CycleLoopEnable"]:
		var value: Variant = emitter.get(field)
		var maximum := 4096 if field == "MaxEmissionCount" else 10000
		if field == "CycleLoopEnable":
			maximum = 1
		if not _number(value, 0, maximum) or float(value) != floor(float(value)):
			return false
	if emitter.MaxEmissionCount < 1 or not _number(emitter.get("CycleLength"), 0.000001, 60):
		return false
	var curves: Variant = emitter.get("curves")
	if not curves is Dictionary:
		return false
	for name: String in ["EmissionCountPerSecond", "LifeTime"]:
		if not _curve_valid(curves.get(name)):
			return false
	_emitter = emitter.duplicate(true)
	_delay = float(delay)
	_started = _delay <= 0.0
	_time = 0.0
	_loops = int(emitter.LoopCount)
	_residue = 0.0
	_next_id = 0
	_finished = false
	_remaining.clear()
	return true


func advance(delta: float, emitting: bool = true) -> Dictionary:
	if _emitter.is_empty() or not is_finite(delta) or delta <= 0.0 or delta > 1.0:
		return {"error": "Invalid particle emission step"}
	var births: Array = []
	var deaths: Array = []
	if _finished:
		return _result(births, deaths)
	if not _started:
		_delay -= delta
		_started = _delay <= 0.0
		# Original delayed activation does not simulate the remainder of this frame.
		return _result(births, deaths)
	_time += delta
	var make_particles := true
	if _time >= float(_emitter.CycleLength):
		if int(_emitter.CycleLoopEnable) != 0:
			_loops -= 1
			make_particles = _loops != 0
		else:
			make_particles = false
		if make_particles:
			_loops = maxi(_loops, 0)
			_time -= float(_emitter.CycleLength)
		else:
			_loops = 1
			if _remaining.is_empty():
				_finished = true
				return _result(births, deaths)
	for id: int in _remaining.keys():
		_remaining[id] = float(_remaining[id]) - delta
		if float(_remaining[id]) < 0.0:
			deaths.append(id)
			_remaining.erase(id)
	if emitting and make_particles:
		var curves: Dictionary = _emitter.curves
		var amount := sample(curves.EmissionCountPerSecond, _time) * delta + _residue
		var count := int(amount)
		_residue = amount - count
		# Discard capacity-clipped integer births; retain only the fractional residue.
		count = mini(count, int(_emitter.MaxEmissionCount) - _remaining.size())
		var lifetime := sample(curves.LifeTime, _time)
		if lifetime > 0.0:
			for unused: int in range(count):
				_next_id += 1
				_remaining[_next_id] = lifetime
				births.append({"id": _next_id, "lifetime": lifetime, "emitter_time": _time})
	return _result(births, deaths)


func _result(births: Array, deaths: Array) -> Dictionary:
	return {
		"births": births,
		"deaths": deaths,
		"alive": _remaining.size(),
		"finished": _finished,
		"emitter_time": _time,
	}


static func sample(keys: Array, time: float) -> float:
	if keys.is_empty():
		return 0.0
	if time <= float(keys[0][0]):
		return float(keys[0][1])
	for i: int in range(1, keys.size()):
		var start: Array = keys[i - 1]
		var end: Array = keys[i]
		if time <= float(end[0]):
			return lerpf(float(start[1]), float(end[1]), (time - start[0]) / (end[0] - start[0]))
	return float(keys.back()[1])


static func _number(value: Variant, low: float, high: float) -> bool:
	return (
		(value is float or value is int)
		and is_finite(float(value))
		and float(value) >= low
		and float(value) <= high
	)


static func _curve_valid(keys: Variant) -> bool:
	if not keys is Array or keys.size() > 256:
		return false
	var previous := -3600.0
	for key: Variant in keys:
		if not key is Array or key.size() != 2:
			return false
		if not _number(key[0], -3600, 3600) or not _number(key[1], 0, 100000):
			return false
		if float(key[0]) < previous:
			return false
		previous = float(key[0])
	return true
