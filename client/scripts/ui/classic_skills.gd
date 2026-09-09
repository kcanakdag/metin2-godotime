extends Control
## Original art with server-owned learned ranks and point spending.
signal learn_requested(vnum: int)
signal cast_requested(vnum: int)
const Art = preload("res://scripts/ui/classic_art.gd")
const Slot = preload("res://scripts/ui/classic_slot.gd")
var catalog := SkillCatalog.new()
var _progression: Dictionary = {}
var _rows: Array = []
var _list: Control
var _points: Label
var _moving := false
var _drag_offset := Vector2.ZERO
var _skill_controls: Dictionary = {}


func _ready() -> void:
	name = "Skills"
	size = Vector2(253, 361)
	position = Vector2(20, 120)
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 13
	Art.board(self, size)
	var title := Art.title(self, "Skills", 253, hide)
	title.gui_input.connect(_title_input)
	_points = Art.label(self, "", Vector2(16, 38), Art.TITLE)
	var scroll := ScrollContainer.new()
	scroll.position = Vector2(16, 67)
	scroll.size = Vector2(225, 188)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	_list = Control.new()
	_list.custom_minimum_size = Vector2(212, 188)
	scroll.add_child(_list)
	var hint := Art.label(
		self,
		"Drag a learned skill to a quickslot.\nRight-click a skill to use it.",
		Vector2(16, 265),
		Art.TEXT
	)
	hint.add_theme_font_size_override("font_size", 11)
	catalog.load_required()
	hide()


func _process(_delta: float) -> void:
	if _moving:
		position = (get_global_mouse_position() - _drag_offset).clamp(
			Vector2.ZERO, get_viewport_rect().size - Vector2(40, 40)
		)
		if not Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
			_moving = false


func _title_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_moving = event.pressed
		_drag_offset = get_global_mouse_position() - position


func set_state(progression: Dictionary, rows: Array) -> void:
	if _progression == progression and _rows == rows:
		return
	_progression = progression.duplicate(true)
	_rows = rows.duplicate(true)
	_skill_controls.clear()
	for child in _list.get_children():
		_list.remove_child(child)
		child.queue_free()
	var spent := 0
	for row: Dictionary in rows:
		spent += int(row.get("points_spent", 0))
	var points := maxi(0, int(progression.get("level", 0)) - 4 - spent)
	_points.text = "Skill points: %d" % points
	var definitions := catalog.available(int(progression.get("character_class", -1)))
	_list.custom_minimum_size.y = maxf(188.0, definitions.size() * 60.0)
	if definitions.is_empty():
		Art.label(_list, "No skills available for this class yet.", Vector2.ZERO, Art.TEXT)
	for index in definitions.size():
		var definition: Dictionary = definitions[index]
		var rank := 0
		for row: Dictionary in rows:
			if int(row.skill_vnum) == int(definition.vnum):
				rank = int(row.rank)
		var y := float(index * 60)
		Art.image(_list, "public/slot_base", Vector2(0, y))
		var slot := Slot.new()
		slot.position = Vector2(0, y)
		slot.size = Vector2(32, 32)
		slot.kind = "skill"
		slot.row = {"skill_vnum": int(definition.vnum), "rank": rank, "icon": definition.icon}
		slot.secondary.connect(func(_slot): cast_requested.emit(int(definition.vnum)))
		slot.tooltip_text = (
			"%s\nRank %d/%d · Requires level %d\n%d SP · %d sec cooldown"
			% [
				definition.name,
				rank,
				definition.maximum_rank,
				definition.minimum_level,
				catalog.cost(int(definition.vnum), maxi(1, rank)),
				catalog.cooldown_us(int(definition.vnum), maxi(1, rank)) / 1000000
			]
		)
		_list.add_child(slot)
		Art.label(_list, str(definition.name), Vector2(42, y), Art.TITLE)
		Art.label(
			_list, "Rank %d / %d" % [rank, definition.maximum_rank], Vector2(42, y + 18), Art.TEXT
		)
		var plus := TextureButton.new()
		plus.position = Vector2(195, y + 9)
		plus.texture_normal = Art.texture("game/windows/btn_plus_up")
		plus.texture_hover = Art.texture("game/windows/btn_plus_over")
		plus.texture_pressed = Art.texture("game/windows/btn_plus_down")
		plus.texture_disabled = plus.texture_normal
		plus.focus_mode = Control.FOCUS_NONE
		plus.pressed.connect(func(): learn_requested.emit(int(definition.vnum)))
		_list.add_child(plus)
		plus.disabled = (
			points == 0
			or rank >= int(definition.maximum_rank)
			or int(progression.get("level", 0)) < int(definition.minimum_level)
		)
		plus.tooltip_text = "Learn / upgrade: 1 skill point"
		_skill_controls[int(definition.vnum)] = {"slot": slot, "learn": plus}


func toggle() -> void:
	visible = not visible


func snapshot() -> Dictionary:
	var scroll: ScrollContainer = _list.get_parent()
	var viewport := scroll.get_global_rect()
	var controls: Array = []
	for vnum: int in _skill_controls:
		var entry: Dictionary = _skill_controls[vnum]
		var slot: Control = entry.slot
		var learn: TextureButton = entry.learn
		var center := slot.get_global_rect().get_center()
		var learn_center := learn.get_global_rect().get_center()
		(
			controls
			. append(
				{
					"vnum": vnum,
					"slot_center": [center.x, center.y],
					"learn_center": [learn_center.x, learn_center.y],
					"fully_visible":
					is_visible_in_tree() and viewport.encloses(slot.get_global_rect()),
					"learn_enabled": not learn.disabled,
				}
			)
		)
	var scroll_center := viewport.get_center()
	return {
		"visible": visible,
		"points": _points.text,
		"rows": _rows.duplicate(true),
		"controls": controls,
		"scroll_center": [scroll_center.x, scroll_center.y],
		"scroll_vertical": scroll.scroll_vertical,
	}
