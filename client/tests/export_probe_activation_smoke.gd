extends SceneTree


class Connection:
	extends Node
	signal reducer_failed(message: String)
	signal reducer_completed(name: String, succeeded: bool, timestamp: int)
	signal players_changed(rows: Array)
	signal monsters_changed(rows: Array)
	signal connection_state_changed(state: String, message: String)


class Fixture:
	extends Node
	var connection := Connection.new()


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var fixture := Fixture.new()
	root.add_child(fixture)
	fixture.add_child(fixture.connection)
	var probe := preload("res://tests/export_probe.gd").new()
	fixture.add_child(probe)
	probe.set_process(false)
	var args := OS.get_cmdline_user_args()
	var enabled := "--probe-report" in args or "--probe-commands" in args
	var failures: Array[String] = []
	var signals := [
		"reducer_failed",
		"reducer_completed",
		"players_changed",
		"monsters_changed",
		"connection_state_changed"
	]
	for signal_name in signals:
		var count := fixture.connection.get_signal_connection_list(signal_name).size()
		if count != (1 if enabled else 0):
			failures.append("Unexpected hook count: " + signal_name)
	await process_frame
	if is_instance_valid(probe) != enabled:
		failures.append("Probe lifetime does not match activation")
	if enabled and probe.get("_report").is_empty() and probe.get("_commands").is_empty():
		failures.append("Native activation argument was not retained")
	print(JSON.stringify({"enabled": enabled, "checks": 7 if enabled else 6, "failures": failures}))
	fixture.free()
	quit(0 if failures.is_empty() else 1)
