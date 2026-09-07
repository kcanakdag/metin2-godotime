extends Control
## The original thin-board frame and 17-pixel line rhythm, with current server values.

const Art = preload("res://scripts/ui/classic_art.gd")


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	z_index = 20
	hide()


func _process(_delta: float) -> void:
	if visible:
		var pointer := get_global_mouse_position()
		position = Vector2(pointer.x - size.x / 2, pointer.y - size.y - 12)
		position = position.clamp(Vector2.ZERO, get_viewport_rect().size - size)


func show_item(row: Dictionary) -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	var vnum := int(row.get("vnum", 0))
	var lines: Array[String] = [Art.item_name(vnum), ""]
	if vnum == 10:
		lines.append("Attack Value +10")
		lines.append("[ Warrior ]")
	elif vnum == 27002:
		lines.append("Cannot be used yet.")
	else:
		lines.append("Restores 40 HP")
		lines.append("Right-click to use")
	size = Vector2(190, 12 + lines.size() * 17)
	Art.board(self, size, true)
	for index in lines.size():
		var line := Art.label(
			self, lines[index], Vector2(0, 7 + index * 17), Art.TITLE if index == 0 else Art.TEXT
		)
		line.size.x = size.x
		line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	show()
