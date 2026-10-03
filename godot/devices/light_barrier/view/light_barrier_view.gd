extends ModelView
## Light barrier model (emitter with LEDs, reflector); the yellow LED shows the switching output.

var _led: Indicator


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_led = Indicator.new(part("LedSignal"))


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	_led.set_on(model.get_value("signal"))
