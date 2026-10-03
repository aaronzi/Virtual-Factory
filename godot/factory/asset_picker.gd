class_name AssetPicker
extends RefCounted
## Maps a pointer ray to the asset whose AAS should be shown: workpieces (by serial) first, then devices and
## tagged props via selection volumes (boxes around their meshes on Interactable.SELECTION_LAYER).
## Returns {"tag": AAS tag, "kind": "workpiece" | "device", "node": Node3D} or {}.

const MIN_SIZE := 0.15


## Adds a selection volume to every device and every prop with an `asset_tag` meta.
static func add_volumes(builder: FactoryBuilder) -> void:
	for device: DeviceNode in builder.devices.values():
		_add_volume(device, device.device_id)
	for prop in builder.props:
		if prop.has_meta("asset_tag"):
			_add_volume(prop, prop.get_meta("asset_tag"))


static func pick(world: World3D, ray: Dictionary, length := 30.0) -> Dictionary:
	var space := world.direct_space_state
	var query := PhysicsRayQueryParameters3D.create(ray.origin, ray.origin + ray.direction * length)
	query.collision_mask = ~(Interactable.SELECTION_LAYER | Interactable.UI_LAYER)
	var hit := space.intersect_ray(query)
	var item: TrackedItem = _ancestor_item(hit.collider) if hit else null
	if item:
		return {"tag": AasClient.workpiece_tag(item.item_id), "kind": "workpiece", "node": item,
			"point": hit.position}
	var surface: Vector3 = hit.position if hit else Vector3.INF
	var area := _most_specific_volume(space, query, surface)
	if area:
		var point := surface if surface.is_finite() and _contains(area, surface) else area.global_position
		return {"tag": area.get_meta("asset_tag"), "kind": "device", "node": area.get_parent(),
			"point": _box_center(area) if not surface.is_finite() else point, "volume": area}
	return {}


## Selection volumes overlap (the robot's box covers the QA station): of all volumes along the ray, pick the
## one the ray passes through most centrally (distance of the ray to the box centre relative to its size).
## Prefers the smallest volume that contains the clicked surface point (what the user actually hit).
static func _most_specific_volume(space: PhysicsDirectSpaceState3D,
		query: PhysicsRayQueryParameters3D, surface := Vector3.INF) -> Area3D:
	query.collision_mask = Interactable.SELECTION_LAYER
	query.collide_with_areas = true
	query.collide_with_bodies = false
	var origin := query.from
	var direction := (query.to - query.from).normalized()
	var best: Area3D
	var best_score := INF
	var exclude: Array[RID] = []
	for i in 8:
		query.exclude = exclude
		var hit := space.intersect_ray(query)
		if hit.is_empty():
			break
		exclude.append(hit.rid)
		var area := hit.collider as Area3D
		if area == null or not area.has_meta("asset_tag") or area.get_child_count() == 0:
			continue
		var shape := area.get_child(0) as CollisionShape3D
		var center := shape.global_position
		var to_center := center - origin
		var miss := (to_center - direction * to_center.dot(direction)).length()
		var size: Vector3 = (shape.shape as BoxShape3D).size
		var score := miss / maxf(size.length() * 0.5, 0.01)
		if surface.is_finite() and _contains(area, surface):
			score = -1.0 / maxf(size.x * size.y * size.z, 1e-6)  # containing boxes win, smallest first
		if score < best_score:
			best_score = score
			best = area
	return best


static func _contains(area: Area3D, point: Vector3) -> bool:
	var shape := area.get_child(0) as CollisionShape3D
	var local := shape.global_transform.affine_inverse() * point
	var half: Vector3 = (shape.shape as BoxShape3D).size * 0.5 + Vector3.ONE * 0.02
	return absf(local.x) <= half.x and absf(local.y) <= half.y and absf(local.z) <= half.z


static func _box_center(area: Area3D) -> Vector3:
	return (area.get_child(0) as Node3D).global_position


static func _ancestor_item(collider: Object) -> TrackedItem:
	var node := collider as Node
	while node:
		if node is TrackedItem:
			return node
		node = node.get_parent()
	return null


static func _add_volume(owner: Node3D, tag: String) -> void:
	var box := _mesh_bounds(owner)
	if box.size == Vector3.ZERO:
		return
	var area := Area3D.new()
	area.name = "SelectionVolume"
	area.collision_layer = Interactable.SELECTION_LAYER
	area.collision_mask = 0
	area.monitoring = false
	area.set_meta("asset_tag", tag)
	var shape := CollisionShape3D.new()
	var box_shape := BoxShape3D.new()
	box_shape.size = box.size.max(Vector3.ONE * MIN_SIZE)  # slim sensors stay clickable
	shape.shape = box_shape
	shape.position = box.get_center()
	area.add_child(shape)
	owner.add_child(area)


## Merged AABB of all meshes below `owner`, in the owner's local frame.
static func _mesh_bounds(owner: Node3D) -> AABB:
	var result := AABB()
	var first := true
	var inverse := owner.global_transform.affine_inverse()
	for mesh: MeshInstance3D in owner.find_children("*", "MeshInstance3D", true, false):
		var local := inverse * mesh.global_transform * mesh.get_aabb()
		result = local if first else result.merge(local)
		first = false
	return result
