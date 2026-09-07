class_name WorldPicker
extends RefCounted
## One nearest-hit ray keeps target proxies behind real client colliders occluded.

const WORLD_COLLISION_LAYER := 1
const TARGET_COLLISION_LAYER := 2
const PICK_MASK := WORLD_COLLISION_LAYER | TARGET_COLLISION_LAYER
const RAY_LENGTH := 500.0


func pick(
	camera: Camera3D, space_state: PhysicsDirectSpaceState3D, screen_position: Vector2
) -> Dictionary:
	if not is_instance_valid(camera) or space_state == null:
		return {}
	var origin := camera.project_ray_origin(screen_position)
	var query := PhysicsRayQueryParameters3D.create(
		origin, origin + camera.project_ray_normal(screen_position) * RAY_LENGTH
	)
	query.collision_mask = PICK_MASK
	query.collide_with_areas = false
	query.collide_with_bodies = true
	return classify_hit(space_state.intersect_ray(query))


func classify_hit(hit: Dictionary) -> Dictionary:
	if hit.is_empty():
		return {}
	var collider: Variant = hit.get("collider")
	if collider is CollisionObject3D and (collider.collision_layer & TARGET_COLLISION_LAYER) != 0:
		if collider.has_meta("npc_actor"):
			return _npc_hit(collider)
		return _combat_hit(collider)
	var position: Variant = hit.get("position")
	if position is Vector3:
		return {"kind": "ground", "position": position}
	return {"kind": "blocked"}


func movement_point(pick_result: Dictionary, plane_fallback: Variant) -> Variant:
	if pick_result.get("kind") == "ground" and pick_result.get("position") is Vector3:
		return pick_result.position
	if pick_result.is_empty() and plane_fallback is Vector3:
		return plane_fallback
	return null


func _npc_hit(collider: CollisionObject3D) -> Dictionary:
	var npc: Variant = collider.get_meta("npc_actor", null)
	if (
		is_instance_valid(npc)
		and npc is NpcActor
		and npc.is_visible_in_tree()
		and str(collider.get_meta("spawn_id", "")) == npc.spawn_id
	):
		return {"kind": "npc", "actor": npc}
	return {"kind": "blocked"}


func _combat_hit(collider: CollisionObject3D) -> Dictionary:
	var actor: Variant = collider.get_meta("combat_target_actor", null)
	var intent: Variant = (
		actor.combat_target_intent()
		if is_instance_valid(actor) and actor.has_method("combat_target_intent")
		else {}
	)
	if not intent is Dictionary or intent.is_empty():
		return {"kind": "blocked"}
	if (
		int(collider.get_meta("target_id", 0)) != int(intent.get("target_id", 0))
		or (
			int(collider.get_meta("target_life_sequence", -1))
			!= int(intent.get("target_life_sequence", -1))
		)
	):
		return {"kind": "blocked"}
	return {"kind": "target", "actor": actor, "intent": intent}
