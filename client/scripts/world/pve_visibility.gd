extends RefCounted
## Presentation selection only; full subscribed state remains server-owned.

# Pinned original config.cpp VIEW_RANGE + VIEW_BONUS_RANGE (centimetres).
const RANGE_CM := 5500


static func includes(row: Dictionary, viewer: Variant, ready_at: Callable) -> bool:
	if not viewer is Vector3 or not viewer.is_finite():
		return false
	var point: Variant = position_for(row)
	if not point is Vector3 or not ready_at.call(point):
		return false
	var dx := absi(int(point.x * 100.0) - int(viewer.x * 100.0))
	var dz := absi(int(point.z * 100.0) - int(viewer.z * 100.0))
	var distance_cm := (246 * maxi(dx, dz) + 102 * mini(dx, dz)) >> 8
	return distance_cm <= RANGE_CM


static func position_for(row: Dictionary) -> Variant:
	var point := Vector3(
		float(row.get("x", NAN)), float(row.get("y", NAN)), float(row.get("z", NAN))
	)
	return point if point.is_finite() else null
