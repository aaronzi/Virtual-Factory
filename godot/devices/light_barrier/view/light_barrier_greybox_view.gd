extends DeviceView
## Greybox view: emitter with status LEDs on one side of the belt, reflector on the other.

const HOUSING := Color(0.15, 0.16, 0.18)
const BRACKET := Color(0.62, 0.64, 0.66)

var _led_signal: MeshInstance3D
var _mat_on := Greybox.material(Color(1.0, 0.75, 0.05), 0.4, 0.0, 3.0)
var _mat_off := Greybox.material(Color(0.25, 0.2, 0.05), 0.6)


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var half: float = device.geometry.get("beam_length", 0.44) * 0.5
	var h: float = device.geometry.get("beam_height", 0.05)
	var housing := Greybox.material(HOUSING, 0.5)
	var bracket := Greybox.material(BRACKET, 0.4, 0.6)
	Greybox.box(self, Vector3(0.03, 0.05, 0.02), Vector3(0, h, half + 0.01), housing)
	Greybox.box(self, Vector3(0.03, h + 0.04, 0.004), Vector3(0, (h - 0.04) * 0.5, half + 0.024), bracket)
	var reflector := Greybox.material(Color(0.8, 0.1, 0.1), 0.2)
	Greybox.box(self, Vector3(0.03, 0.03, 0.006), Vector3(0, h, -half - 0.003), reflector)
	Greybox.box(self, Vector3(0.03, h + 0.03, 0.004), Vector3(0, (h - 0.03) * 0.5, -half - 0.008), bracket)
	var power_led := Greybox.material(Color(0.1, 0.9, 0.2), 0.4, 0.0, 2.0)
	Greybox.sphere(self, 0.004, Vector3(0.008, h + 0.026, half + 0.01), power_led)
	_led_signal = Greybox.sphere(self, 0.004, Vector3(-0.008, h + 0.026, half + 0.01), _mat_off)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	_led_signal.material_override = _mat_on if model.get_value("signal") else _mat_off
