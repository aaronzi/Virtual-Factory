extends DeviceView
## Physical actuator of the assembly cell: spawns a workpiece at the outlet whenever the model
## reports a release. Uses the injected "item_factory" service.

var _last_count := 0
var _outlet: Marker3D


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_outlet = Marker3D.new()
	_outlet.name = "Outlet"
	_outlet.position = device.geometry.get("outlet", Vector3(0.95, 0.853, 0.0))
	add_child(_outlet)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var count: int = model.get_value("release_count")
	if count == _last_count:
		return
	_last_count = count
	var factory: ItemFactory = device.services.get("item_factory")
	if factory == null:
		push_warning("AssemblyCell %s: no item_factory service" % device.device_id)
		return
	factory.spawn(_outlet.global_transform, model.get_value("last_serial"), {
		"cap_variant": model.get_value("last_cap_variant"),
		"leak_rate": model.get_value("last_leak_rate"),
		"stroke_time": model.get_value("last_stroke_time"),
	})
