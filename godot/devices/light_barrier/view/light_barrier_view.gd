extends ModelView
## Light barrier model (emitter with LEDs, reflector); the yellow LED shows the switching output.

var _led: Indicator


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_led = Indicator.new(part("LedSignal"))
	for mesh in model_root.find_children("*", "GeometryInstance3D", true, false):
		(mesh as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF  # tiny


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	_led.set_on(model.get_value("signal"))
