extends DeviceView
## Greybox QA station: bracket on the conveyor frame, angled colour sensor with ring light,
## result lamp (green = OK, red = NOK) and the robot pick point marker.

var _ring: MeshInstance3D
var _lamp: MeshInstance3D
var _ring_on := Greybox.material(Color(0.95, 0.95, 1.0), 0.3, 0.0, 4.0)
var _ring_off := Greybox.material(Color(0.6, 0.6, 0.62), 0.3)
var _lamp_ok := Greybox.material(Color(0.1, 0.9, 0.2), 0.3, 0.0, 3.0)
var _lamp_nok := Greybox.material(Color(0.95, 0.1, 0.1), 0.3, 0.0, 3.0)
var _lamp_idle := Greybox.material(Color(0.2, 0.22, 0.22), 0.5)


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var g := device.geometry
	var head := QaStationGeometry.sensor_head(g)
	var target := QaStationGeometry.inspection_point(g)
	var alu := Greybox.material(Color(0.72, 0.74, 0.76), 0.35, 0.7)
	var post_z: float = head.z + 0.06
	Greybox.box(self, Vector3(0.04, head.y + 0.12, 0.04), Vector3(0, (head.y + 0.12) * 0.5 - 0.1, post_z), alu)
	Greybox.box(self, Vector3(0.03, 0.03, 0.08), Vector3(0, head.y + 0.03, post_z - 0.04), alu)
	var sensor := Node3D.new()
	add_child(sensor)
	sensor.transform = Transform3D(Basis.looking_at(target - head, Vector3.UP), head)
	var housing := Greybox.material(Color(0.16, 0.17, 0.2), 0.4)
	Greybox.box(sensor, Vector3(0.035, 0.035, 0.06), Vector3(0, 0, 0.01), housing)
	_ring = Greybox.cylinder(sensor, 0.028, 0.008, Vector3(0, 0, -0.024), _ring_off, Vector3.FORWARD)
	_lamp = Greybox.sphere(self, 0.018, Vector3(0, head.y + 0.08, post_z), _lamp_idle)
	var marker := Marker3D.new()
	marker.name = "PickPoint"
	marker.position = Vector3(0, g.get("pick_height", 0.15), 0)
	add_child(marker)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	_ring.material_override = _ring_on if model.get_value("light_on") else _ring_off
	if not model.get_value("result_valid"):
		_lamp.material_override = _lamp_idle
	else:
		_lamp.material_override = _lamp_ok if model.get_value("result_ok") else _lamp_nok
