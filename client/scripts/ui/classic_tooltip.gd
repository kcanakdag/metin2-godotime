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
	var definition := ItemCatalog.item(vnum)
	if row.has("skill_vnum"):
		var skills := SkillCatalog.new()
		if skills.load_required():
			var skill := skills.definition(int(row.skill_vnum))
			if not skill.is_empty():
				lines[0] = str(skill.name)
				lines.append("Rank %d / %d" % [int(row.get("rank", 0)), skill.maximum_rank])
				lines.append(
					(
						"SP cost %d"
						% skills.cost(int(row.skill_vnum), maxi(1, int(row.get("rank", 0))))
					)
				)
				lines.append("Cooldown %d sec" % (int(skill.cooldown_us) / 1000000))
				lines.append("Requires level %d and an equipped sword" % skill.minimum_level)
	elif definition.get("kind") == "weapon":
		var physical: Dictionary = definition.get("weapon", {})
		var minimum := int(physical.get("power_min", 0)) + int(physical.get("refine_attack", 0))
		var maximum := int(physical.get("power_max", 0)) + int(physical.get("refine_attack", 0))
		lines.append("Attack Value %s" % _attack_value_text(minimum, maximum))
		lines.append("Attack Speed +%d%%" % int(definition.get("attack_speed_bonus", 0)))
		var classes: Array[String] = []
		var names := ["Warrior", "Assassin", "Sura", "Shaman"]
		for index in names.size():
			if int(definition.get("allowed_classes", 0)) & (1 << index):
				classes.append(names[index])
		lines.append("[ %s ]" % " / ".join(classes))
	elif definition.get("kind") == "recovery":
		var effect: Dictionary = definition.get("recovery", {})
		if int(effect.get("hp", 0)) > 0:
			lines.append("Restores %d HP gradually" % int(effect.hp))
		if int(effect.get("sp", 0)) > 0:
			lines.append("Restores %d SP gradually" % int(effect.sp))
		lines.append("Right-click to use")
	else:
		lines.append("Cannot be used.")
	var width := 190.0
	for text: String in lines:
		width = maxf(
			width,
			(
				ceilf(
					ThemeDB.fallback_font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
				)
				+ 20.0
			)
		)
	size = Vector2(width, 12 + lines.size() * 17)
	Art.board(self, size, true)
	for index in lines.size():
		var line := Art.label(
			self, lines[index], Vector2(0, 7 + index * 17), Art.TITLE if index == 0 else Art.TEXT
		)
		line.size.x = size.x
		line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	show()


func _attack_value_text(minimum: int, maximum: int) -> String:
	return str(minimum) if minimum == maximum else "%d-%d" % [minimum, maximum]
