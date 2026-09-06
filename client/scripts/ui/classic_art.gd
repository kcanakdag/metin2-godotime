extends RefCounted
## Original bitmap composition; coordinates are measured in native source pixels.

const ROOT := "res://assets/imported/ui/"
const TEXT := Color("c2c2c2")
const TITLE := Color("f2e7c1")


static func texture(path: String) -> Texture2D:
	var resource := ROOT + path.to_lower() + ".png"
	if ResourceLoader.exists(resource):
		return load(resource) as Texture2D
	return null


static func image(parent: Node, path: String, at: Vector2) -> TextureRect:
	var result := TextureRect.new()
	result.texture = texture(path)
	result.position = at
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	result.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	if result.texture:
		result.size = result.texture.get_size()
	parent.add_child(result)
	return result


static func tile(parent: Node, path: String, rect: Rect2) -> TextureRect:
	var result := image(parent, path, rect.position)
	result.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	result.stretch_mode = TextureRect.STRETCH_TILE
	result.size = rect.size
	return result


static func button(parent: Node, path: String, at: Vector2, action: Callable) -> TextureButton:
	var result := TextureButton.new()
	result.position = at
	result.texture_normal = texture(path + "01")
	result.texture_hover = texture(path + "02")
	result.texture_pressed = texture(path + "03")
	result.texture_disabled = result.texture_normal
	result.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	result.focus_mode = Control.FOCUS_NONE
	result.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	if action.is_valid():
		result.pressed.connect(action)
	parent.add_child(result)
	return result


static func label(parent: Node, text: String, at: Vector2, color: Color = TEXT) -> Label:
	var result := Label.new()
	result.text = text
	result.position = at
	result.add_theme_font_size_override("font_size", 12)
	result.add_theme_color_override("font_color", color)
	result.add_theme_color_override("font_shadow_color", Color.BLACK)
	result.add_theme_constant_override("shadow_offset_x", 1)
	result.add_theme_constant_override("shadow_offset_y", 1)
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(result)
	return result


static func board(parent: Node, dimensions: Vector2, thin: bool = false) -> Control:
	var result := Control.new()
	result.size = dimensions
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(result)
	var corner := 16.0 if thin else 32.0
	var prefix := "pattern/thinboard_" if thin else "pattern/board_"
	var inner := dimensions - Vector2.ONE * corner * 2
	if thin:
		var fill := ColorRect.new()
		fill.color = Color(0, 0, 0, 0.51)
		fill.position = Vector2.ONE * corner
		fill.size = inner
		fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
		result.add_child(fill)
	else:
		tile(result, prefix + "base", Rect2(Vector2.ONE * corner, inner))
	for entry in [
		["lefttop", Vector2.ZERO],
		["righttop", Vector2(dimensions.x - corner, 0)],
		["leftbottom", Vector2(0, dimensions.y - corner)],
		["rightbottom", dimensions - Vector2.ONE * corner]
	]:
		image(result, prefix + "corner_" + entry[0], entry[1])
	for entry in [
		["left", Rect2(0, corner, corner, inner.y)],
		["right", Rect2(dimensions.x - corner, corner, corner, inner.y)],
		["top", Rect2(corner, 0, inner.x, corner)],
		["bottom", Rect2(corner, dimensions.y - corner, inner.x, corner)]
	]:
		tile(result, prefix + "line_" + entry[0], entry[1])
	return result


static func title(parent: Node, text: String, width: float, close: Callable) -> Control:
	var result := Control.new()
	result.position = Vector2(8, 7)
	result.size = Vector2(width, 23)
	result.mouse_filter = Control.MOUSE_FILTER_PASS
	parent.add_child(result)
	image(result, "pattern/titlebar_left", Vector2.ZERO)
	tile(result, "pattern/titlebar_center", Rect2(32, 0, width - 64, 32))
	image(result, "pattern/titlebar_right", Vector2(width - 32, 0))
	var caption := label(result, text, Vector2(0, 3), TITLE)
	caption.size.x = width - 7
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var exit_button := button(result, "public/close_button_", Vector2(width - 18, 3), close)
	exit_button.tooltip_text = "Close"
	return result


static func item_icon(vnum: int) -> Texture2D:
	return texture("icon/item/%05d" % vnum)


static func item_height(vnum: int) -> int:
	return 2 if vnum == 10 else 1


static func item_name(vnum: int) -> String:
	return "Sword+0" if vnum == 10 else "Red Potion (S)"
