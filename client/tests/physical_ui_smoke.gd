extends SceneTree
## Isolated preparation check for the proposed public physical display fields.

const ActorCatalog = preload("res://scripts/content/actor_catalog.gd")
const ClassicStatus = preload("res://scripts/ui/classic_status.gd")
const ClassicTooltip = preload("res://scripts/ui/classic_tooltip.gd")

var _checks := 0
var _failed := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 720)
	var status := ClassicStatus.new()
	root.add_child(status)
	await process_frame
	status.set_player({"name": "Warrior", "health": 380, "max_health": 760})
	status.set_progression(_display_row(6, 28, 31, 5))
	status.show()
	var snapshot: Dictionary = status.snapshot()
	_check(snapshot.values.attack == "28-31", "renders initial equipped owner attack range")
	_check(snapshot.values.defense == "5", "renders initial owner display defense")
	status.set_progression(_display_row(6, 10, 10, 5))
	_check(status.snapshot().values.attack == "10", "renders unarmed one-value owner attack")
	_check(
		status.snapshot().values.defense == "5", "unarmed display defense remains owner-projected"
	)
	status.set_progression(_display_row(7, 30, 32, 5))
	_check(
		status.snapshot().values.attack == "30-32", "renders STR-seven equipped owner attack range"
	)
	status.set_progression(_display_row(6, 28, 31, 5))
	_check(
		(
			status._labels.attack.tooltip_text
			== "Equipped-weapon Attack. Actual damage depends on the target."
		),
		"attack tooltip explains target-dependent damage"
	)

	var tooltip := ClassicTooltip.new()
	root.add_child(tooltip)
	await process_frame
	tooltip.show_item({"vnum": 10})
	_check(
		_tooltip_text(tooltip).contains("Attack Value 13-15"),
		"Sword+0 tooltip uses public item physical range"
	)
	tooltip.show_item({"vnum": 27001})
	_check(
		_tooltip_text(tooltip).contains("Restores 300 HP gradually"), "small recovery from catalog"
	)
	tooltip.show_item({"vnum": 27002})
	_check(
		_tooltip_text(tooltip).contains("Restores 800 HP gradually"), "medium recovery from catalog"
	)
	_check(not _tooltip_text(tooltip).contains("Cannot be used"), "medium potion is usable")

	var catalog := ActorCatalog.new()
	_check(catalog.load_required(), "staged catalog accepts exact selected public physical field")
	var sword: Dictionary = catalog.item_for_vnum(10)
	var physical: Dictionary = sword.get("physical", {})
	_check(
		(
			physical.size() == 3
			and int(physical.get("power_min", -1)) == 13
			and int(physical.get("power_max", -1)) == 15
			and int(physical.get("refine_attack", -1)) == 0
		),
		"catalog retains exact selected Sword+0 public field"
	)
	var missing_physical: Dictionary = catalog.manifest.duplicate(true)
	for item: Dictionary in missing_physical.get("items", []):
		if str(item.get("id", "")) == ActorCatalog.SWORD_ID:
			item.erase("physical")
	var missing_catalog := ActorCatalog.new()
	missing_catalog.report_errors = false
	_check(
		not missing_catalog.load_document(missing_physical),
		"catalog rejects a missing selected Sword+0 public physical field"
	)
	var malformed_physical: Dictionary = catalog.manifest.duplicate(true)
	for item: Dictionary in malformed_physical.get("items", []):
		if str(item.get("id", "")) == ActorCatalog.SWORD_ID:
			item.get("physical", {})["unexpected"] = 1
	var malformed_catalog := ActorCatalog.new()
	malformed_catalog.report_errors = false
	_check(
		not malformed_catalog.load_document(malformed_physical),
		"catalog rejects an expanded selected Sword+0 public physical field"
	)

	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://physical-ui-component.png")
	if not _failed:
		print("PHYSICAL_UI_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _tooltip_text(node: Node) -> String:
	var lines: PackedStringArray = []
	for child in node.get_children():
		if child is Label:
			lines.append(child.text)
	return "\n".join(lines)


func _display_row(strength: int, attack_min: int, attack_max: int, defense: int) -> Dictionary:
	return {
		"character_id": "a".repeat(64),
		"level": 1,
		"experience": 0,
		"next_exp": 300,
		"unspent_stat_points": 0,
		"strength": strength,
		"vitality": 4,
		"dexterity": 3,
		"intelligence": 3,
		"current_sp": 130,
		"max_sp": 260,
		"display_attack_min": attack_min,
		"display_attack_max": attack_max,
		"display_defense": defense,
	}


func _check(passed: bool, description: String) -> void:
	if not passed:
		push_error("PHYSICAL_UI_SMOKE FAIL " + description)
		_failed = true
		return
	_checks += 1
