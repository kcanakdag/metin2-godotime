extends RefCounted
## Original effect mesh frame progression, independent of rendering and gameplay.

var _count := 0
var _frame := 0
var _interval := 0.02
var _remaining := 0.02
var _delay := 0.0
var _time := 0.0
var _loops := 0
var _looping := false
var _started := false
var _finished := false


func configure(count: int, interval: float, looping: bool, loops: int, delay: float = 0) -> bool:
	if (
		count < 1
		or count > 256
		or not is_finite(interval)
		or interval < 0.000001
		or interval > 60
		or loops < 0
		or loops > 1000000
		or not is_finite(delay)
		or delay < 0
		or delay > 3600
	):
		return false
	_count = count
	_interval = interval
	_remaining = interval
	_delay = delay
	_looping = looping
	_loops = loops
	_frame = 0
	_time = 0
	_started = delay <= 0
	_finished = false
	return true


func advance(delta: float) -> Dictionary:
	if _count == 0 or not is_finite(delta) or delta <= 0 or delta > 1:
		return {"error": "Invalid mesh frame clock step"}
	if _finished:
		return snapshot()
	if not _started:
		_delay -= delta
		_started = _delay <= 0
		# Original activation frame shows frame zero without advancing local time.
		return snapshot()
	_time += delta
	_remaining -= delta
	for unused: int in range(20):
		if _remaining >= 0:
			break
		_remaining += _interval
		_frame += 1
		if _frame >= _count:
			_loops -= 1
			_frame = 0
			if _looping and _loops != 0:
				_loops = maxi(0, _loops)
			else:
				_loops = 1
				_finished = true
				break
	return snapshot()


func snapshot() -> Dictionary:
	return {
		"frame": _frame,
		"visible": _started and not _finished,
		"finished": _finished,
		"local_time": _time
	}
