extends ModelView
## Assembly cell model: stack light (green = assembling, amber = blocked/waiting, red = idle while
## the line is not enabled).

var _green: Indicator
var _amber: Indicator
var _red: Indicator


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_green = Indicator.new(part("LightGreen"))
	_amber = Indicator.new(part("LightAmber"))
	_red = Indicator.new(part("LightRed"))


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var state: int = model.get_value("state")
	_green.set_on(state == 1)
	_amber.set_on(state == 2)
	_red.set_on(state == 0)
