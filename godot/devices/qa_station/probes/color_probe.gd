extends DeviceProbe
## Light spot of the colour sensor: a ray from the sensor head to the inspection point.
## Reports the perceived surface colour and whether a TrackedItem is in the spot.

const BACKGROUND := Color(0.12, 0.13, 0.13)

var _head := Vector3.ZERO
var _target := Vector3.ZERO


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_head = QaStationGeometry.sensor_head(device.geometry)
	_target = QaStationGeometry.inspection_point(device.geometry)


func sample(model: Fmi3CoSimulation, _delta: float) -> void:
	var from := device.to_global(_head)
	var to := from + (device.to_global(_target) - from) * 1.6
	var query := PhysicsRayQueryParameters3D.create(from, to, PhysicsLayers.WORLD | PhysicsLayers.ITEMS)
	var hit := device.get_world_3d().direct_space_state.intersect_ray(query)
	var color := Color.BLACK
	var present := false
	if not hit.is_empty():
		present = hit.collider is TrackedItem
		color = hit.collider.get_surface_color_at(hit.position) if present else BACKGROUND
	model.set_value("measured_r", color.r)
	model.set_value("measured_g", color.g)
	model.set_value("measured_b", color.b)
	model.set_value("object_present", present)
