extends DeviceProbe
## Casts the light beam from emitter to reflector and reports whether an item interrupts it.

var _from := Vector3.ZERO
var _to := Vector3.ZERO


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var half: float = device.geometry.get("beam_length", 0.44) * 0.5
	var height: float = device.geometry.get("beam_height", 0.05)
	_from = Vector3(0, height, half)
	_to = Vector3(0, height, -half)


func sample(model: Fmi3CoSimulation, _delta: float) -> void:
	var query := PhysicsRayQueryParameters3D.create(
		device.to_global(_from), device.to_global(_to), PhysicsLayers.ITEMS)
	var hit := device.get_world_3d().direct_space_state.intersect_ray(query)
	model.set_value("beam_blocked", not hit.is_empty())
