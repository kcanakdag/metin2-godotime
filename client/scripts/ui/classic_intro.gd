extends Control
## Account and character presentation using selected original English client artwork.
## Credentials leave only through explicit submit signals; snapshots never include them.

signal login_requested(username: String, password: String)
signal register_requested(username: String, email: String, password: String)
signal select_requested(character_id: String)
signal create_requested(slot: int, character_name: String)
signal enter_requested
signal logout_requested

const Art = preload("res://scripts/ui/classic_art.gd")
const Preview = preload("res://scripts/ui/classic_intro_preview.gd")
const STAGES := ["server", "login", "register", "empire", "select", "create"]
const BUSY_STATES := [
	"busy",
	"registering",
	"logging_in",
	"authenticating",
	"connecting",
	"reconnecting",
	"subscribing",
	"opening",
	"joining",
	"leaving",
	"selecting",
	"creating",
	"entering",
	"loading"
]

var _stage := "server"
var _busy := false
var _available := false
var _server_label := "Yongan"
var _authenticated := false
var _rows: Array = []
var _selected_id := ""
var _slot := 0
var _background: TextureRect
var _preview: Control
var _panels: Dictionary = {}
var _controls: Dictionary = {}
var _buttons: Array[BaseButton] = []
var _unavailable: Array[BaseButton] = []
var _message: Label
var _username: LineEdit
var _password: LineEdit
var _register_name: LineEdit
var _email: LineEdit
var _register_password: LineEdit
var _character_name: LineEdit
var _character_values: Dictionary = {}
var _character_title: TextureRect
var _empire_title: TextureRect
var _empire_atlas: Control
var _create_title: TextureRect
var _left: BaseButton
var _right: BaseButton


func _ready() -> void:
	name = "ClassicIntro"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	_background = TextureRect.new()
	_background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_background.stretch_mode = TextureRect.STRETCH_SCALE
	_background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_background)
	_preview = Preview.new()
	add_child(_preview)
	_build_server()
	_build_login()
	_build_register()
	_build_empire()
	_build_select()
	_build_create()
	_build_arrows()
	_message = Art.label(self, "", Vector2.ZERO, Color("f2e7c1"))
	_message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_message.size = Vector2(600, 60)
	get_viewport().size_changed.connect(_layout)
	_layout()
	set_stage("server")


func set_stage(stage: String) -> void:
	if stage not in STAGES:
		return
	_stage = stage
	for key in _panels:
		_panels[key].visible = key == stage
	_preview.visible = stage in ["select", "create"]
	_left.visible = _preview.visible
	_right.visible = _preview.visible
	_background.texture = Art.texture(
		(
			"locale/en/ui/select"
			if _preview.visible
			else "locale/en/ui/" + ("serverlist" if stage == "server" else "login")
		)
	)
	if stage == "empire":
		_background.texture = null
	_message.text = ""
	_refresh_character()
	_update_enabled()
	if not _busy:
		_focus_default.call_deferred()


func set_status(state: String, message: String) -> void:
	_busy = state in BUSY_STATES
	_message.text = message
	_message.add_theme_color_override(
		"font_color", Color("ff9090") if state == "error" else Art.TITLE
	)
	_update_enabled()
	if not _busy:
		_focus_default.call_deferred()


func set_server(label: String, available: bool) -> void:
	_server_label = label
	_available = available
	_controls.server_row.text = label
	_controls.channel_row.text = "CH 1   " + ("Online" if available else "Offline")
	_controls.connection_name.text = label + " / CH 1"
	_update_enabled()


func set_roster(rows: Array, selected_id: String) -> void:
	var old_id := _selected_id
	_rows = rows
	_selected_id = selected_id
	_authenticated = true
	if (
		not selected_id.is_empty()
		and (old_id != selected_id or _stage in ["server", "login", "register"])
	):
		for row: Dictionary in rows:
			if str(row.get("id", "")) == selected_id:
				_slot = clampi(int(row.get("slot", 0)), 0, 3)
	if _stage in ["server", "login", "register"]:
		if selected_id.is_empty() and not rows.is_empty():
			_slot = clampi(int(rows[0].get("slot", 0)), 0, 3)
		set_stage("empire" if rows.is_empty() else "select")
	_refresh_character()
	_update_enabled()


func clear_session() -> void:
	_authenticated = false
	_rows.clear()
	_selected_id = ""
	_slot = 0
	_password.clear()
	_register_password.clear()
	_email.clear()
	_character_name.clear()
	_busy = false
	set_stage("login")


func handle_key(event: InputEventKey) -> bool:
	if not visible or not event.pressed or event.echo or _busy:
		return false
	if event.keycode == KEY_ESCAPE:
		_back()
		return true
	if get_viewport().gui_get_focus_owner() is LineEdit:
		return false
	if _stage == "select":
		if event.keycode in [KEY_LEFT, KEY_RIGHT]:
			_cycle(-1 if event.keycode == KEY_LEFT else 1)
			return true
		if event.keycode >= KEY_1 and event.keycode <= KEY_4:
			_choose_slot(event.keycode - KEY_1)
			return true
	var primary := event.keycode in [KEY_ENTER, KEY_KP_ENTER]
	if primary:
		_primary()
	return primary


func snapshot() -> Dictionary:
	var rectangles: Dictionary = {}
	var character_values: Dictionary = {}
	var focused_control := ""
	var focused := get_viewport().gui_get_focus_owner()
	for key in _controls:
		var control: Control = _controls[key]
		var rect := control.get_global_rect()
		rectangles[key] = [rect.position.x, rect.position.y, rect.size.x, rect.size.y]
		if control == focused:
			focused_control = str(key)
	for key: String in _character_values:
		character_values[key] = _character_values[key].text
	return {
		"visible": is_visible_in_tree(),
		"stage": _stage,
		"busy": _busy,
		"available": _available,
		"slot": _slot,
		"selected_id": _selected_id,
		"roster_count": _rows.size(),
		"controls": rectangles,
		"focused_control": focused_control,
		"character_name_input": _character_name.text,
		"character_values": character_values,
		"preview": _preview.snapshot(),
		"password_masked": _password.secret and _register_password.secret,
		"message": _message.text
	}


func _panel(key: String, dimensions: Vector2, thin: bool = true) -> Control:
	var result := Control.new()
	result.name = key.capitalize() + "Panel"
	result.size = dimensions
	result.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(result)
	if dimensions != Vector2.ZERO:
		Art.board(result, dimensions, thin)
	_panels[key] = result
	return result


func _button(
	parent: Node, key: String, text: String, at: Vector2, action: Callable, kind: String = "large"
) -> BaseButton:
	var result := Art.button(parent, "public/" + kind + "_button_", at, action)
	var caption := Art.label(result, text, Vector2.ZERO, Color.WHITE)
	caption.size = result.get_combined_minimum_size()
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_controls[key] = result
	_buttons.append(result)
	return result


func _field(
	parent: Node, key: String, at: Vector2, dimensions: Vector2, secret: bool = false
) -> LineEdit:
	var result := LineEdit.new()
	result.position = at
	result.secret = secret
	result.secret_character = "*"
	result.max_length = 128 if secret else 32
	result.add_theme_font_size_override("font_size", 12)
	result.add_theme_color_override("font_color", Color.WHITE)
	for state in ["normal", "focus", "read_only"]:
		result.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	parent.add_child(result)
	result.size = dimensions
	_controls[key] = result
	return result


func _build_server() -> void:
	var panel := _panel("server", Vector2(375, 400))
	var title := Art.label(panel, "Select Server", Vector2(0, 12), Color.WHITE)
	title.size.x = 375
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_line(panel, Rect2(10, 34, 354, 1), Color("777777"))
	_line(panel, Rect2(10, 35, 355, 1), Color("111111"))
	_line(panel, Rect2(246, 38, 1, 355), Color("777777"))
	_line(panel, Rect2(247, 38, 1, 355), Color("111111"))
	for entry in [
		["server_row", Vector2(10, 40), Vector2(232, 22)],
		["channel_row", Vector2(255, 40), Vector2(109, 22)]
	]:
		var row := Button.new()
		row.position = entry[1]
		row.size = entry[2]
		row.alignment = HORIZONTAL_ALIGNMENT_LEFT
		row.focus_mode = Control.FOCUS_NONE
		row.add_theme_font_size_override("font_size", 12)
		var selected := StyleBoxFlat.new()
		selected.bg_color = Color(0.45, 0.37, 0.2, 0.6)
		for state in ["normal", "hover", "pressed", "disabled"]:
			row.add_theme_stylebox_override(state, selected)
		panel.add_child(row)
		_controls[entry[0]] = row
		_buttons.append(row)
	_button(panel, "server_confirm", "OK", Vector2(267, 351), set_stage.bind("login"))
	_button(panel, "server_exit", "Exit", Vector2(267, 373), _logout)


func _build_login() -> void:
	var panel := _panel("login", Vector2.ZERO)
	panel.size = Vector2(208, 132)
	Art.image(panel, "locale/en/ui/login/loginwindow", Vector2(0, 35))
	Art.board(panel, Vector2(208, 32), true)
	var name := Art.label(panel, "Yongan / CH 1", Vector2(15, 8))
	name.clip_text = true
	name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	name.size.x = 130
	_controls.connection_name = name
	_button(panel, "server_change", "Select", Vector2(150, 5), set_stage.bind("server"), "small")
	_username = _field(panel, "username", Vector2(77, 51), Vector2(120, 18))
	_password = _field(panel, "password", Vector2(77, 78), Vector2(120, 18), true)
	_username.text_submitted.connect(func(_text: String) -> void: _password.grab_focus())
	_password.text_submitted.connect(func(_text: String) -> void: _submit_login())
	_button(panel, "login_submit", "Login", Vector2(15, 100), _submit_login)
	_button(panel, "login_exit", "Exit", Vector2(105, 100), _logout)
	_button(
		panel, "register_open", "Register", Vector2(14, 143), set_stage.bind("register"), "xlarge"
	)


func _build_register() -> void:
	var panel := _panel("register", Vector2(280, 190))
	Art.title(panel, "Register", 265, set_stage.bind("login"))
	for entry in [["Username", 42], ["Email", 76], ["Password", 110]]:
		Art.label(panel, entry[0], Vector2(14, entry[1] + 2))
		Art.image(panel, "public/parameter_slot_05", Vector2(128, entry[1]))
	_register_name = _field(panel, "register_username", Vector2(131, 42), Vector2(125, 18))
	_email = _field(panel, "register_email", Vector2(131, 76), Vector2(125, 18))
	_email.max_length = 254
	_register_password = _field(
		panel, "register_password", Vector2(131, 110), Vector2(125, 18), true
	)
	_register_name.text_submitted.connect(func(_text: String) -> void: _email.grab_focus())
	_email.text_submitted.connect(func(_text: String) -> void: _register_password.grab_focus())
	_register_password.text_submitted.connect(func(_text: String) -> void: _submit_register())
	_button(panel, "register_submit", "Register", Vector2(42, 150), _submit_register)
	_button(panel, "register_cancel", "Cancel", Vector2(146, 150), set_stage.bind("login"))


func _build_empire() -> void:
	var panel := _panel("empire", Vector2.ZERO)
	Art.tile(panel, "intro/pattern/background_pattern", Rect2(0, 42, 1280, 716)).name = "Pattern"
	var shade := Art.image(panel, "intro/select/background_alpha", Vector2.ZERO)
	shade.name = "Shade"
	shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	Art.tile(panel, "intro/pattern/line_pattern", Rect2(0, 0, 1280, 64)).name = "Top"
	Art.tile(panel, "intro/pattern/line_pattern", Rect2(0, 758, 1280, 64)).name = "Bottom"
	_empire_title = Art.image(panel, "locale/en/ui/empire/title", Vector2.ZERO)
	_empire_atlas = Art.image(panel, "intro/empire/atlas", Vector2.ZERO)
	for entry in [
		["a", Vector2(43, 201), Vector2(167, 235)],
		["b", Vector2(17, 16), Vector2(70, 42)],
		["c", Vector2(314, 33), Vector2(357, 78)]
	]:
		var area := Art.image(_empire_atlas, "intro/empire/empirearea_" + entry[0], entry[1])
		area.modulate.a = 1.0 if entry[0] == "a" else 0.25
		var flag := Art.image(_empire_atlas, "intro/empire/empireareaflag_" + entry[0], entry[2])
		flag.modulate.a = 1.0 if entry[0] == "a" else 0.4
	var board := Control.new()
	board.name = "EmpireBoard"
	board.size = Vector2(208, 314)
	panel.add_child(board)
	Art.board(board, board.size, true)
	Art.image(board, "intro/empire/empireflag_a", Vector2(40, 36))
	var text := Art.label(
		board, "Shinsoo\n\nThe southern empire.\n\nBegin your journey in Yongan.", Vector2(15, 149)
	)
	text.size = Vector2(180, 118)
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_button(board, "empire_confirm", "Select", Vector2(14, 277), set_stage.bind("create"))
	_button(board, "empire_cancel", "Cancel", Vector2(105, 277), _back)
	for entry in [["left", Vector2(160, 340)], ["right", Vector2(290, 340)]]:
		var arrow := Art.button(
			_empire_atlas, "intro/select/" + entry[0] + "_button_", entry[1], Callable()
		)
		arrow.disabled = true
		arrow.modulate = Color(0.5, 0.5, 0.5)
		arrow.tooltip_text = "Shinsoo"


func _build_select() -> void:
	var panel := _panel("select", Vector2(208, 323))
	_character_title = Art.image(panel, "locale/en/ui/select/name_warrior", Vector2(-27, -149))
	var flag := Art.image(panel, "intro/empire/empireflag_a", Vector2(21, 12))
	flag.scale = Vector2(0.5, 0.5)
	Art.image(panel, "public/parameter_slot_03", Vector2(100, 12))
	Art.image(panel, "public/parameter_slot_03", Vector2(100, 33))
	Art.label(panel, "Shinsoo", Vector2(109, 13))
	Art.label(panel, "No Guild", Vector2(109, 34))
	for entry in [
		["name", "Name", 63, 43, "05"],
		["level", "Level", 89, 43, "05"],
		["playtime", "Play Time", 115, 83, "03"]
	]:
		Art.label(panel, entry[1], Vector2(17, entry[2]))
		var background := Art.image(
			panel, "public/parameter_slot_" + entry[4], Vector2(17 + entry[3], entry[2] - 2)
		)
		var value := Art.label(panel, "", Vector2(17 + entry[3], entry[2]))
		value.size.x = background.size.x
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_character_values[entry[0]] = value
	for index in 4:
		var key: String = ["hth", "int", "str", "dex"][index]
		Art.label(panel, ["VIT", "INT", "STR", "DEX"][index], Vector2(17, 141 + 26 * index))
		_gauge(panel, Vector2(47, 145 + 26 * index), 100)
		Art.image(panel, "public/parameter_slot_00", Vector2(151, 139 + 26 * index))
		var value := Art.label(panel, "", Vector2(151, 141 + 26 * index))
		value.size.x = 39
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_character_values[key] = value
	_button(panel, "enter", "Start", Vector2(14, 249), _enter, "xlarge")
	_button(panel, "create_open", "Create", Vector2(14, 249), _begin_create, "xlarge")
	var delete := _button(panel, "delete", "Delete", Vector2(14, 284), Callable())
	_unavailable.append(delete)
	_button(panel, "select_logout", "Exit", Vector2(105, 284), _logout)


func _build_create() -> void:
	var panel := _panel("create", Vector2(208, 329))
	_create_title = Art.image(panel, "locale/en/ui/select/name_warrior", Vector2(-27, -149))
	var text := Art.label(
		panel,
		"Warrior\n\nWarriors fight at close range\nwith strength and courage.",
		Vector2(13, 14)
	)
	text.size = Vector2(180, 112)
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_line(panel, Rect2(8, 131, 189, 1), Color("aaa6a1"))
	for index in 4:
		Art.label(panel, ["VIT", "INT", "STR", "DEX"][index], Vector2(15, 138 + 19 * index))
		_gauge(panel, Vector2(45, 142 + 19 * index), 120)
		Art.image(panel, "public/parameter_slot_00", Vector2(165, 137 + 19 * index))
	Art.label(panel, "Name", Vector2(43, 218))
	Art.image(panel, "public/parameter_slot_04", Vector2(82, 216))
	_character_name = _field(panel, "character_name", Vector2(85, 218), Vector2(90, 20))
	_character_name.max_length = 16
	_character_name.text_submitted.connect(func(_text: String) -> void: _submit_create())
	Art.label(panel, "Sex", Vector2(43, 247))
	var male := _button(panel, "male", "Male", Vector2(79, 247), Callable(), "middle")
	male.toggle_mode = true
	male.button_group = ButtonGroup.new()
	male.button_pressed = true
	var female := _button(panel, "female", "Female", Vector2(139, 247), Callable(), "middle")
	_unavailable.append(female)
	Art.label(panel, "Shape", Vector2(43, 270))
	var shape := _button(panel, "shape_1", "1", Vector2(79, 268), Callable(), "middle")
	shape.toggle_mode = true
	shape.button_group = ButtonGroup.new()
	shape.button_pressed = true
	_unavailable.append(_button(panel, "shape_2", "2", Vector2(139, 268), Callable(), "middle"))
	_button(panel, "create_submit", "Create", Vector2(11, 294), _submit_create)
	_button(panel, "create_cancel", "Cancel", Vector2(109, 294), _back)


func _build_arrows() -> void:
	_left = Art.button(self, "intro/select/dragon_left_button_", Vector2.ZERO, _cycle.bind(-1))
	_right = Art.button(self, "intro/select/dragon_right_button_", Vector2.ZERO, _cycle.bind(1))
	_controls.slot_previous = _left
	_controls.slot_next = _right


func _gauge(parent: Node, at: Vector2, width: float) -> void:
	Art.image(parent, "pattern/gauge_slot_left", at)
	Art.tile(
		parent, "pattern/gauge_slot_center", Rect2(at + Vector2(16, 0), Vector2(width - 32, 7))
	)
	Art.image(parent, "pattern/gauge_slot_right", at + Vector2(width - 16, 0))


func _line(parent: Node, rect: Rect2, color: Color) -> void:
	var line := ColorRect.new()
	line.position = rect.position
	line.size = rect.size
	line.color = color
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(line)


func _layout() -> void:
	var viewport := get_viewport_rect().size
	_panels.server.position = Vector2((viewport.x - 375) / 2, viewport.y - 472)
	_panels.login.position = Vector2((viewport.x - 208) / 2, viewport.y - 445)
	_panels.register.position = (viewport - _panels.register.size) / 2
	_panels.select.position = Vector2(viewport.x * 65 / 800, viewport.y * 220 / 600)
	_panels.create.position = Vector2(viewport.x * 65 / 800, viewport.y * 215 / 600)
	var empire: Control = _panels.empire
	empire.size = viewport
	empire.get_node("Pattern").size = Vector2(viewport.x, viewport.y - 84)
	empire.get_node("Shade").size = viewport
	empire.get_node("Top").size.x = viewport.x
	empire.get_node("Bottom").position.y = viewport.y - 42
	empire.get_node("Bottom").size.x = viewport.x
	empire.get_node("EmpireBoard").position = viewport * Vector2(40.0 / 800, 211.0 / 600)
	_empire_atlas.position = viewport * Vector2(282.0 / 800, 170.0 / 600)
	_empire_title.position = viewport * Vector2(237.0 / 800, 46.0 / 600)
	_empire_title.scale = viewport / Vector2(800, 600)
	_preview.position = Vector2(270, 0)
	_preview.size = Vector2(maxf(1, viewport.x - 270), viewport.y)
	_left.position = viewport * Vector2(384.0 / 800, 505.0 / 600)
	_right.position = viewport * Vector2(558.0 / 800, 505.0 / 600)
	_message.position = Vector2((viewport.x - 600) / 2, viewport.y - 70)


func _refresh_character() -> void:
	if not is_instance_valid(_preview):
		return
	var row := _row_for_slot(_slot)
	for key in _character_values:
		_character_values[key].text = str(row.get(key, ""))
	_character_title.visible = not row.is_empty()
	_controls.enter.visible = not row.is_empty()
	_controls.create_open.visible = row.is_empty()
	_preview.set_characters(_rows, _slot, _stage == "create")


func _update_enabled() -> void:
	for button in _buttons:
		button.disabled = _busy
	for button in _unavailable:
		button.disabled = true
		button.modulate = Color(0.5, 0.5, 0.5)
	for field in [
		_username, _password, _register_name, _email, _register_password, _character_name
	]:
		field.editable = not _busy
	if _controls.has("server_confirm"):
		_controls.server_confirm.disabled = _busy or not _available
		_controls.server_row.disabled = _busy or not _available
		_controls.channel_row.disabled = _busy or not _available
		_controls.login_submit.disabled = _busy or not _available
	var row := _row_for_slot(_slot)
	_controls.enter.disabled = _busy or row.is_empty() or str(row.get("id", "")) != _selected_id
	_left.disabled = _busy or _stage == "create"
	_right.disabled = _busy or _stage == "create"
	_left.modulate = Color(0.5, 0.5, 0.5) if _left.disabled else Color.WHITE
	_right.modulate = _left.modulate


func _focus_default() -> void:
	if not is_visible_in_tree() or _busy:
		return
	var field: LineEdit
	match _stage:
		"login":
			field = _username
		"register":
			field = _register_name
		"create":
			field = _character_name
	if field:
		field.grab_focus()
	else:
		var focused := get_viewport().gui_get_focus_owner()
		if focused:
			focused.release_focus()


func _row_for_slot(slot: int) -> Dictionary:
	for row: Dictionary in _rows:
		if int(row.get("slot", -1)) == slot:
			return row
	return {}


func _choose_slot(slot: int) -> void:
	if _busy:
		return
	_slot = clampi(slot, 0, 3)
	_refresh_character()
	_update_enabled()
	var row := _row_for_slot(_slot)
	if not row.is_empty() and str(row.get("id", "")) != _selected_id:
		select_requested.emit(str(row.id))


func _cycle(direction: int) -> void:
	if _stage == "select":
		_choose_slot(posmod(_slot + direction, 4))


func _begin_create() -> void:
	if not _busy and _row_for_slot(_slot).is_empty():
		set_stage("empire" if _rows.is_empty() else "create")


func _submit_login() -> void:
	if _busy or not _available:
		return
	if _username.text.strip_edges().is_empty() or _password.text.is_empty():
		set_status("error", "Enter your username and password.")
		return
	var username := _username.text.strip_edges()
	var password := _password.text
	_password.clear()
	login_requested.emit(username, password)


func _submit_register() -> void:
	if _busy:
		return
	if (
		_register_name.text.strip_edges().is_empty()
		or _email.text.strip_edges().is_empty()
		or _register_password.text.is_empty()
	):
		set_status("error", "Enter your username, email and password.")
		return
	var username := _register_name.text.strip_edges()
	var email := _email.text.strip_edges()
	var password := _register_password.text
	_register_password.clear()
	register_requested.emit(username, email, password)


func _submit_create() -> void:
	if _busy:
		return
	if _character_name.text.strip_edges().is_empty():
		set_status("error", "Choose a character name.")
		return
	create_requested.emit(_slot, _character_name.text.strip_edges())


func _enter() -> void:
	if not _controls.enter.disabled:
		enter_requested.emit()


func _primary() -> void:
	match _stage:
		"server":
			if _available:
				set_stage("login")
		"login":
			_submit_login()
		"register":
			_submit_register()
		"empire":
			set_stage("create")
		"create":
			_submit_create()
		"select":
			if _row_for_slot(_slot).is_empty():
				_begin_create()
			else:
				_enter()


func _back() -> void:
	match _stage:
		"server", "login", "select":
			_logout()
		"register":
			set_stage("login")
		"empire":
			set_stage("select")
		"create":
			set_stage("select")


func _logout() -> void:
	_password.clear()
	_register_password.clear()
	logout_requested.emit()
