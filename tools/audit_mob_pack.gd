extends SceneTree
## Run against an actual exported pack; verify installed mob/projectile resources.


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("Expected gameplay hash and report path")
		quit(1)
		return
	var Catalog = load("res://scripts/content/actor_catalog.gd")
	var catalog = Catalog.new()
	if not catalog.load_required() or catalog.mob_gameplay_hash != args[0]:
		push_error("Exported mob catalog missing or incompatible")
		quit(1)
		return
	var document: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://assets/imported/mobs/presentation.v1.json")
	)
	var models: Dictionary = {}
	for artifact: Dictionary in document.artifacts:
		var path := str(artifact.path)
		if models.has(path):
			continue
		var packed = load(path)
		if not packed is PackedScene:
			push_error("Missing exported mob scene: " + path)
			quit(1)
			return
		var model: Node = packed.instantiate()
		var players := model.find_children("*", "AnimationPlayer", true, false)
		var skeletons := model.find_children("*", "Skeleton3D", true, false)
		var meshes := model.find_children("*", "MeshInstance3D", true, false)
		if (
			players.is_empty()
			or skeletons.is_empty()
			or meshes.is_empty()
			or players[0].get_animation_list().is_empty()
		):
			push_error("Exported mob missing animation, skeleton or mesh: " + path)
			model.free()
			quit(1)
			return
		models[path] = {
			"clips": players[0].get_animation_list().size(),
			"bones": skeletons[0].get_bone_count(),
			"meshes": meshes.size()
		}
		model.free()
	var Projectiles = load("res://scripts/world/world_projectiles.gd")
	var projectiles = Projectiles.new()
	var valid: bool = projectiles.prepare(
		catalog.manifest,
		"res://assets/imported/projectiles/catalog.v1.json",
		func(_id, _life): return {}
	)
	projectiles.free()
	if not valid:
		push_error("Exported projectile resource validation failed")
		quit(1)
		return
	var result := {
		"passed": true,
		"mob_gameplay_hash": args[0],
		"actors": document.actors.size(),
		"models": models,
		"projectiles_loaded": true
	}
	var report := FileAccess.open(args[1], FileAccess.WRITE)
	report.store_string(JSON.stringify(result, "\t"))
	report.close()
	print(JSON.stringify(result))
	quit(0)
