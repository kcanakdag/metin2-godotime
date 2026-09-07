extends Node


func _ready() -> void:
	await get_tree().create_timer(0.25).timeout
	var file := FileAccess.open("user://scene-command-qa-args.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(OS.get_cmdline_user_args()))
	file.close()
	await get_tree().create_timer(0.5).timeout
	get_tree().quit()
