extends Control
## Original affect-strip placement; contents and duration come from subscribed status.
const Art = preload("res://scripts/ui/classic_art.gd")
var catalog := SkillCatalog.new()
var _icons: Dictionary = {}
var _names: Dictionary = {}
var _hovered := ""
var _description: Label


func _ready() -> void:
	position = Vector2(10, 10)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_description = Art.label(self, "", Vector2.ZERO, Color.WHITE)
	_description.add_theme_color_override("font_outline_color", Color.BLACK)
	_description.add_theme_constant_override("outline_size", 2)
	_description.z_index = 1
	_description.hide()
	catalog.load_required()


func set_state(rows: Array, character: String) -> void:
	var visible_ids: Dictionary = {}
	for row: Dictionary in rows:
		if str(row.get("character_id", "")) != character or bool(row.get("paused", true)):
			continue
		var skill := catalog.definition(int(row.get("skill_vnum", 0)))
		var path := str(skill.get("buff_icon", ""))
		if path.is_empty() or int(row.get("remaining_ticks", 0)) <= 0:
			continue
		var id := str(row.id)
		if visible_ids.has(id) or visible_ids.size() >= 32:
			continue
		var icon: TextureRect = _icons.get(id)
		if icon == null:
			icon = Art.image(self, path, Vector2.ZERO)
			icon.scale = Vector2(0.7, 0.7)
			icon.mouse_filter = Control.MOUSE_FILTER_PASS
			icon.mouse_entered.connect(_show_description.bind(id))
			icon.mouse_exited.connect(_hide_description.bind(id))
			_icons[id] = icon
		icon.position = Vector2(25 * visible_ids.size(), 0)
		_names[id] = str(skill.name)
		visible_ids[id] = true
	for id: String in _icons.keys():
		if not visible_ids.has(id):
			remove_child(_icons[id])
			_icons[id].queue_free()
			_icons.erase(id)
			_names.erase(id)
			_hide_description(id)
	size = Vector2(25 * visible_ids.size(), 26)
	if not _hovered.is_empty():
		_show_description(_hovered)


func _show_description(id: String) -> void:
	if not _icons.has(id):
		return
	_hovered = id
	_description.text = _names[id]
	var icon: TextureRect = _icons[id]
	var width := _description.get_minimum_size().x
	_description.position = icon.position + Vector2(maxf(0, icon.size.x * 0.7 / 2 - width / 2), 40)
	_description.show()


func _hide_description(id: String) -> void:
	if _hovered == id:
		_hovered = ""
		_description.hide()
