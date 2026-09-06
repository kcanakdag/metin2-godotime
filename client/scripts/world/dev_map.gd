@tool
class_name DevMap
extends Node3D
## Small handmade test ground. Collision obstacles come from the server table.

var obstacle_rows: Array = []
var half_size := 32.0
var collision_visible := false
var _obstacles: Node3D
var _collision: Node3D


func _ready() -> void:
	_build_ground()
	_obstacles = Node3D.new()
	_obstacles.name = "ServerObstacles"
	add_child(_obstacles)
	_collision = Node3D.new()
	_collision.name = "CollisionOverlay"
	add_child(_collision)
	_collision.visible = collision_visible


func set_obstacles(rows: Array) -> void:
	obstacle_rows = rows.duplicate(true)
	for child in _obstacles.get_children():
		child.queue_free()
	for child in _collision.get_children():
		child.queue_free()
	for row: Dictionary in rows:
		var size := Vector3(float(row.half_x) * 2.0, float(row.height), float(row.half_z) * 2.0)
		var position_3d := Vector3(float(row.x), size.y * 0.5, float(row.z))
		var material := _material(Color("777b6a"))
		var mesh: Mesh
		if str(row.kind) == "metin":
			var crystal := CylinderMesh.new()
			crystal.top_radius = 0.18
			crystal.bottom_radius = minf(size.x, size.z) * 0.6
			crystal.height = size.y
			crystal.radial_segments = 5
			mesh = crystal
			material = _material(Color("745c73"))
		else:
			var block := BoxMesh.new()
			block.size = size
			mesh = block
		_add_mesh(_obstacles, mesh, position_3d, material, "Obstacle_" + str(row.id))
		var overlay := BoxMesh.new()
		overlay.size = size + Vector3(0.9, 0.04, 0.9)
		var tint := _material(Color(0.95, 0.68, 0.2, 0.2))
		tint.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		tint.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		_add_mesh(_collision, overlay, position_3d, tint, "Collider_" + str(row.id))


func show_collision(enabled: bool) -> void:
	collision_visible = enabled
	if is_instance_valid(_collision):
		_collision.visible = enabled


func _build_ground() -> void:
	var grass := PlaneMesh.new()
	grass.size = Vector2.ONE * 80.0
	_add_mesh(self, grass, Vector3.ZERO, _material(Color("667153")), "Ground")
	var path := PlaneMesh.new()
	path.size = Vector2(7.0, 64.0)
	_add_mesh(self, path, Vector3(0, 0.015, 0), _material(Color("a89b78")), "NorthRoad")
	var crossing := PlaneMesh.new()
	crossing.size = Vector2(64.0, 5.5)
	_add_mesh(self, crossing, Vector3(0, 0.018, 0), _material(Color("a89b78")), "EastRoad")
	var circle := CylinderMesh.new()
	circle.top_radius = 4.8
	circle.bottom_radius = 4.8
	circle.height = 0.045
	circle.radial_segments = 48
	_add_mesh(self, circle, Vector3(0, 0.024, 3.0), _material(Color("b0ac91")), "MeetingSquare")
	for index in 18:
		var angle := float(index) / 18.0 * TAU
		var point := Vector3(cos(angle), 0.0, sin(angle)) * (26.0 + float(index % 3))
		_tree(point, index)
	_pavilion(Vector3(-17, 0, -14))
	_pavilion(Vector3(17, 0, -14))
	for x in [-25.0, 25.0]:
		var marker := CylinderMesh.new()
		marker.top_radius = 0.18
		marker.bottom_radius = 0.25
		marker.height = 4.0
		_add_mesh(self, marker, Vector3(x, 2, 0), _material(Color("635240")), "BoundaryPost")
		var banner := BoxMesh.new()
		banner.size = Vector3(1.2, 2, 0.07)
		var color := Color("9e453f") if x < 0 else Color("385d79")
		_add_mesh(self, banner, Vector3(x + 0.5, 2.9, 0), _material(color), "KingdomBanner")


func _tree(point: Vector3, index: int) -> void:
	var trunk := CylinderMesh.new()
	trunk.top_radius = 0.18
	trunk.bottom_radius = 0.38
	trunk.height = 3.5
	trunk.radial_segments = 6
	_add_mesh(self, trunk, point + Vector3.UP * 1.75, _material(Color("615446")), "TreeTrunk")
	var crown := SphereMesh.new()
	crown.radius = 2.3 + float(index % 3) * 0.2
	crown.height = 4.2
	crown.radial_segments = 10
	crown.rings = 5
	var greens := [Color("3e5844"), Color("4f6142"), Color("687448")]
	_add_mesh(self, crown, point + Vector3.UP * 4.0, _material(greens[index % 3]), "TreeCrown")


func _pavilion(point: Vector3) -> void:
	var base := BoxMesh.new()
	base.size = Vector3(6.0, 0.3, 5.0)
	_add_mesh(self, base, point + Vector3.UP * 0.15, _material(Color("898976")), "PavilionBase")
	for x in [-2.3, 2.3]:
		for z in [-1.8, 1.8]:
			var post := BoxMesh.new()
			post.size = Vector3(0.3, 3.2, 0.3)
			_add_mesh(
				self, post, point + Vector3(x, 1.9, z), _material(Color("82574a")), "PavilionPost"
			)
	var roof := PrismMesh.new()
	roof.size = Vector3(7.2, 2.0, 6.2)
	_add_mesh(self, roof, point + Vector3.UP * 4.1, _material(Color("404f51")), "PavilionRoof")


func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.95
	return material


func _add_mesh(parent: Node, mesh: Mesh, point: Vector3, material: Material, label: String) -> void:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.mesh = mesh
	instance.material_override = material
	instance.position = point
	parent.add_child(instance)
