extends ModelView
## QA station model: ring light during measurement, OK/NOK lamps with the latched result, and the
## robot pick point marker (teach point).

var _ring: Indicator
var _ok: Indicator
var _nok: Indicator


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_ring = Indicator.new(part("RingLight"), 4.0)
	_ok = Indicator.new(part("LampOk"))
	_nok = Indicator.new(part("LampNok"))
	var marker := Marker3D.new()
	marker.name = "PickPoint"
	marker.position = Vector3(0, device.geometry.get("pick_height", 0.15), 0)
	add_child(marker)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var valid: bool = model.get_value("result_valid")
	var ok: bool = model.get_value("result_ok")
	_ring.set_on(model.get_value("light_on"))
	_ok.set_on(valid and ok)
	_nok.set_on(valid and not ok)
