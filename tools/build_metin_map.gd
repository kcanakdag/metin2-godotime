extends SceneTree
## Offline scene assembly. No database connection and no editor plugin initialization.

var destination: String
var data: Dictionary
var scene: Node3D
var terrain_textures: TextureLayered
var texture_uv := PackedVector4Array()
var marker_mesh: CylinderMesh
var water_material: StandardMaterial3D


func _initialize() -> void:
	call_deferred("build")


func build() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or not args[0].is_valid_filename():
		fail("Expected one map name")
		return
	destination = "res://assets/imported/maps/" + args[0]
	data = JSON.parse_string(FileAccess.get_file_as_string(destination + "/map.json"))
	if data.is_empty():
		fail("Missing map manifest")
		return
	scene = Node3D.new()
	scene.name = "OriginalMap"
	root.add_child(scene)
	scene.set_meta("source_map", data.map)
	scene.set_meta("import_counts", data.counts)
	scene.set_meta("map_size", data.settings.size)
	if not make_materials():
		return
	var geometry := Node3D.new()
	geometry.name = "Sections"
	attach(scene, geometry)
	var props := Node3D.new()
	props.name = "Scenery"
	attach(scene, props)
	var missing := Node3D.new()
	missing.name = "UnsupportedMarkers"
	missing.visible = false
	attach(scene, missing)
	for chunk in data.chunks:
		add_terrain(geometry, chunk)
		for record in chunk.objects:
			add_placement(props, missing, chunk.id, record)
	var packed := PackedScene.new()
	if packed.pack(scene) != OK:
		fail("Could not pack imported map")
		return
	if ResourceSaver.save(packed, destination + "/map.tscn") != OK:
		fail("Could not save imported map")
		return
	print(
		(
			"MAP_SCENE_BUILT sections=%d scenery=%d markers=%d"
			% [geometry.get_child_count(), props.get_child_count(), missing.get_child_count()]
		)
	)
	build_chunks()
	quit()


func build_chunks() -> void:
	DirAccess.make_dir_recursive_absolute(destination + "/chunks")
	var floors: Array = []
	var collision_path := destination + "/collision.json"
	if FileAccess.file_exists(collision_path):
		floors = JSON.parse_string(FileAccess.get_file_as_string(collision_path)).floors
	for chunk in data.chunks:
		scene = Node3D.new()
		scene.name = "MapChunk_" + chunk.id
		root.add_child(scene)
		add_terrain(scene, chunk)
		var missing := Node3D.new()
		missing.name = "UnsupportedMarkers"
		attach(scene, missing)
		missing.visible = false
		for record in chunk.objects:
			if data.properties[record.crc].status == "converted":
				add_placement(scene, missing, chunk.id, record)
		for mesh: MeshInstance3D in scene.find_children("Terrain", "MeshInstance3D"):
			var body := StaticBody3D.new()
			body.name = "TerrainCollision"
			attach(scene, body)
			body.global_transform = mesh.global_transform
			var shape := CollisionShape3D.new()
			shape.shape = mesh.mesh.create_trimesh_shape()
			attach(body, shape)
		var faces := PackedVector3Array()
		for floor_data: Array in floors:
			var gx := int((floor_data[0] + floor_data[1]) * 0.5 / 256)
			var gz := int((floor_data[2] + floor_data[3]) * 0.5 / 256)
			if gx == int(chunk.grid[0]) and gz == int(chunk.grid[1]):
				for i in range(4, 13, 3):
					faces.append(Vector3(floor_data[i], floor_data[i + 1], floor_data[i + 2]))
		if not faces.is_empty():
			var body := StaticBody3D.new()
			body.name = "AuthoredWalkSurfaces"
			attach(scene, body)
			var shape := CollisionShape3D.new()
			var triangles := ConcavePolygonShape3D.new()
			triangles.backface_collision = true
			triangles.set_faces(faces)
			shape.shape = triangles
			attach(body, shape)
		var packed := PackedScene.new()
		if (
			packed.pack(scene) != OK
			or ResourceSaver.save(packed, destination + "/chunks/" + chunk.id + ".tscn") != OK
		):
			fail("Could not save streaming chunk " + chunk.id)
			return
		scene.queue_free()


func fail(message: String) -> void:
	push_error(message)
	quit(1)


func attach(parent: Node, child: Node) -> void:
	parent.add_child(child)
	child.owner = scene


func make_materials() -> bool:
	for texture in data.textures:
		texture_uv.append(Vector4(texture.uv[0], texture.uv[1], texture.uv[2], texture.uv[3]))
	if data.textures.size() > 32:
		fail("Terrain shader supports at most 32 layers")
		return false
	texture_uv.resize(32)
	terrain_textures = load(destination + "/textures/terrain-array.png")
	if terrain_textures == null or terrain_textures.get_layers() != data.textures.size():
		fail("Terrain texture array is missing layers")
		return false
	marker_mesh = CylinderMesh.new()
	marker_mesh.top_radius = 0.0
	marker_mesh.bottom_radius = 0.65
	marker_mesh.height = 3.0
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.3, 0.7)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	marker_mesh.material = material
	water_material = StandardMaterial3D.new()
	water_material.albedo_color = Color(0.12, 0.36, 0.48, 0.72)
	water_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	water_material.roughness = 0.22
	return true


func add_terrain(parent: Node3D, chunk: Dictionary) -> void:
	var resource: PackedScene = load(destination + "/terrain/" + chunk.id + ".glb")
	var section := resource.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	section.name = "Section_" + chunk.id
	section.position = Vector3(chunk.grid[0] * 256.0, 0, chunk.grid[1] * 256.0)
	attach(parent, section)
	scene.set_editable_instance(section, true)
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/imported_terrain.gdshader")
	material.set_shader_parameter("terrain_textures", terrain_textures)
	material.set_shader_parameter("texture_uv", texture_uv)
	material.set_shader_parameter(
		"tile_ids", load(destination + "/terrain/" + chunk.id + "-tiles.png")
	)
	material.set_shader_parameter(
		"attributes", load(destination + "/terrain/" + chunk.id + "-attributes.png")
	)
	for node in section.find_children("*", "MeshInstance3D"):
		if str(node.name).begins_with("Terrain"):
			node.material_override = material
		else:
			node.material_override = water_material


func add_placement(parent: Node3D, missing: Node3D, chunk_id: String, record: Dictionary) -> void:
	var prop: Dictionary = data.properties[record.crc]
	var node: Node3D
	if prop.status == "converted":
		var resource: PackedScene = load(destination + "/models/" + prop.asset_id + ".glb")
		node = resource.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	else:
		var marker := MeshInstance3D.new()
		marker.mesh = marker_mesh
		node = marker
		parent = missing
	node.name = "Object_%s_%03d_%s" % [chunk_id, record.id, record.crc]
	attach(parent, node)
	var p: Array = record.position
	node.position = Vector3(p[0], p[1], p[2])
	var angles: Array = record.rotation_ypr_deg
	var source_rotation := Basis(Vector3.UP, deg_to_rad(angles[0]))
	source_rotation *= Basis(Vector3.RIGHT, deg_to_rad(angles[1]))
	source_rotation *= Basis(Vector3.BACK, deg_to_rad(angles[2]))
	# Blender/glTF maps source (x,y,z) into Godot (x,z,-y).
	var conversion := Basis(Vector3.RIGHT, Vector3.FORWARD, Vector3.UP)
	node.basis = conversion * source_rotation * conversion.transposed()
	node.set_meta("property_crc", record.crc)
	node.set_meta("property_name", prop.fields.get("propertyname", "Unknown"))
	node.set_meta("import_status", prop.status)
	node.set_meta("source_position_cm", record.source_position)
	if prop.status != "converted":
		node.set_meta("import_reason", prop.reason)
