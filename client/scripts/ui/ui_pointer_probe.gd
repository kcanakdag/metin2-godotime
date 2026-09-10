class_name UiPointerProbe
extends RefCounted

## Pointer diagnostics shared by the in-game debug HUD and exported QA probes.
##
## World clicks are delivered through `_unhandled_input`, so any GUI control with
## a mouse filter of STOP consumes them first and world actions silently stop
## working. Reporting which control owns the pointer turns that class of failure
## into a named overlay instead of a mystery timeout.


static func hovered_control_path(node: Node) -> String:
	var control := hovered_control(node)
	if control == null:
		return ""
	return "%s/%s" % [control.get_parent().get_path(), control.name]


static func hovered_control(node: Node) -> Control:
	if node == null or not node.is_inside_tree():
		return null
	var control := node.get_viewport().gui_get_hovered_control()
	return control if is_instance_valid(control) else null


static func mouse_position(node: Node) -> Array:
	if node == null or not node.is_inside_tree():
		return []
	var position := node.get_viewport().get_mouse_position()
	return [position.x, position.y]
