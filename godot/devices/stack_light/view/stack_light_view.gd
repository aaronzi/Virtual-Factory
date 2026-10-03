extends ModelView
## Signal tower model (base, pole, three LED segments, buzzer cap): lit segments glow in their colour.

const LAMPS := {"LampGreen": "green_on", "LampAmber": "amber_on", "LampRed": "red_on"}

var _lamps := {}  # output name -> Indicator


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	for part_name: String in LAMPS:
		_lamps[LAMPS[part_name]] = Indicator.new(part(part_name), 1.2)
	for mesh in model_root.find_children("*", "GeometryInstance3D", true, false):
		(mesh as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF  # draw calls


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	for output: String in _lamps:
		(_lamps[output] as Indicator).set_on(model.get_value(output))
