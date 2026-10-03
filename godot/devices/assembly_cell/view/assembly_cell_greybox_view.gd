extends DeviceView
## Greybox enclosure of the black-box assembly cell: housing, window, outlet tunnel, HMI,
## stack light (green = assembling, amber = blocked) and a progress bar.

var _green: MeshInstance3D
var _amber: MeshInstance3D
var _progress: MeshInstance3D
var _on_green := Greybox.material(Color(0.1, 0.9, 0.2), 0.3, 0.0, 3.0)
var _on_amber := Greybox.material(Color(1.0, 0.65, 0.0), 0.3, 0.0, 3.0)
var _off := Greybox.material(Color(0.25, 0.25, 0.25), 0.5)


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var size: Vector3 = device.geometry.get("size", Vector3(1.6, 2.0, 1.2))
	var body := Greybox.material(Color(0.86, 0.87, 0.86), 0.6)
	var dark := Greybox.material(Color(0.25, 0.28, 0.31), 0.6)
	Greybox.box(self, Vector3(size.x, 0.12, size.z), Vector3(0, 0.06, 0), dark)
	Greybox.box(self, Vector3(size.x, size.y - 0.12, size.z), Vector3(0, 0.06 + size.y * 0.5, 0), body)
	Greybox.box(self, Vector3(size.x * 0.6, size.y * 0.35, 0.01),
		Vector3(-0.1, size.y * 0.62, size.z * 0.5 + 0.005),
		Greybox.material(Color(0.12, 0.2, 0.26), 0.1, 0.3))
	Greybox.box(self, Vector3(0.3, 0.22, 0.32), Vector3(size.x * 0.5 + 0.15, 0.96, 0), dark)
	Greybox.box(self, Vector3(0.25, 0.18, 0.05), Vector3(size.x * 0.32, 1.35, size.z * 0.5 + 0.03),
		Greybox.material(Color(0.05, 0.08, 0.12), 0.2, 0.0, 0.6))
	Greybox.box(self, Vector3(0.5, 0.03, 0.01), Vector3(-0.1, size.y * 0.4, size.z * 0.5 + 0.006), dark)
	_progress = Greybox.box(self, Vector3(0.5, 0.03, 0.01),
		Vector3(-0.1, size.y * 0.4, size.z * 0.5 + 0.008), _on_green)
	var top := Vector3(size.x * 0.4, size.y + 0.06, size.z * 0.3)
	Greybox.cylinder(self, 0.01, 0.12, top, dark)
	_green = Greybox.cylinder(self, 0.03, 0.06, top + Vector3(0, 0.09, 0), _off)
	_amber = Greybox.cylinder(self, 0.03, 0.06, top + Vector3(0, 0.15, 0), _off)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var state: int = model.get_value("state")
	_green.material_override = _on_green if state == 1 else _off
	_amber.material_override = _on_amber if state == 2 else _off
	var p: float = model.get_value("cycle_progress")
	_progress.scale.x = maxf(p, 0.001)
	_progress.position.x = -0.1 - 0.25 * (1.0 - p)
