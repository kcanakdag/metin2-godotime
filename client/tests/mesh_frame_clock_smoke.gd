extends SceneTree

const Clock = preload("res://scripts/actors/mesh_frame_clock.gd")
var _checks := 0
var _failures: Array[String] = []


func _init() -> void:
	var clock := Clock.new()
	_check("unconfigured", clock.advance(0.01).has("error"))
	_check("configure finite", clock.configure(3, 0.125, false, 0))
	_check("exact deadline stays", clock.advance(0.125).frame == 0)
	_check("past deadline advances", clock.advance(0.0625).frame == 1)
	_check("last frame visible", clock.advance(0.125).frame == 2)
	var done: Dictionary = clock.advance(0.125)
	_check("finite wraps and stops", done.finished and done.frame == 0 and not done.visible)
	_check("finished stays stopped", clock.advance(1) == done)
	_check("configure delayed", clock.configure(3, 0.125, false, 0, 0.25))
	_check("before activation hidden", not clock.advance(0.125).visible)
	var activated: Dictionary = clock.advance(0.25)
	_check(
		"activation discards overshoot",
		activated.visible and activated.frame == 0 and activated.local_time == 0
	)
	_check("delayed first deadline stays", clock.advance(0.125).frame == 0)
	_check("configure two loops", clock.configure(2, 0.125, true, 2))
	_check("first wrap alive", not clock.advance(0.3125).finished)
	_check("second wrap completes", clock.advance(0.25).finished)
	_check("configure infinite", clock.configure(2, 0.125, true, 0))
	for unused: int in range(10):
		_check("infinite stays alive", not clock.advance(1).finished)
	_check("configure catchup", clock.configure(100, 0.001, false, 0))
	_check("catchup bounded twenty", clock.advance(1).frame == 20)
	_check("backlog retained", clock.advance(0.001).frame == 40)
	_check("reject nonfinite", clock.advance(NAN).has("error"))
	_check("reject negative interval", not clock.configure(3, -1, false, 0))
	_check("reject bad count", not clock.configure(257, 0.02, false, 0))
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)
