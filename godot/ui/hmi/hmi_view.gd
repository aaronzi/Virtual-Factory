class_name HmiView
extends PanelContainer
## Line operator panel (HMI) on the HMI stand: PackML state and commands, counters, OEE, alarm, KLT exchange.
## View only - the controller pushes a status dictionary and executes the emitted commands.

signal command_pressed(command: int)
signal auto_exchange_toggled(enabled: bool)
signal exchange_pressed(container: int)
signal ack_pressed

const C := PackMLStateMachine.Command
const COMMANDS := [[C.RESET, "HMI_RESET"], [C.START, "HMI_START"], [C.STOP, "HMI_STOP"], [C.HOLD, "HMI_HOLD"],
	[C.UNHOLD, "HMI_UNHOLD"], [C.SUSPEND, "HMI_SUSPEND"], [C.UNSUSPEND, "HMI_UNSUSPEND"],
	[C.ABORT, "HMI_ABORT"], [C.CLEAR, "HMI_CLEAR"]]

var _state: Label
var _stats: Label
var _oee: Label
var _alarm: Label
var _ack: Button
var _auto: CheckButton
var _buttons := {}  # command -> Button


func _init() -> void:
	theme = UiTheme.get_theme()
	var root := VBoxContainer.new()
	add_child(root)
	var head := HBoxContainer.new()
	head.add_child(UiTheme.label("LINE01", 24))
	_state = UiTheme.label("-", 24, UiTheme.MUTED)
	_state.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_state.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	head.add_child(_state)
	root.add_child(head)
	_stats = UiTheme.label("", 17)
	_oee = UiTheme.label("", 17, UiTheme.ACCENT.lightened(0.3))
	_alarm = UiTheme.label("", 17, UiTheme.ALARM)
	_alarm.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS  # one line: the layout has no spare row
	root.add_child(_stats)
	root.add_child(_oee)
	root.add_child(_alarm_row())
	root.add_child(_command_grid())
	root.add_child(_klt_row())


## status: {state:int, state_name, total, ok, nok, klt_a, klt_b, capacity, auto_exchange, alarm,
##          availability, performance, quality, unacked (alarms service: unacknowledged alarms, -1 = n/a)}
func update_status(s: Dictionary) -> void:
	_state.text = s.get("state_name", "-")
	_state.add_theme_color_override("font_color", _state_color(s.get("state", 0)))
	var total: int = s.get("total", 0)
	var reject: float = 100.0 * s.get("nok", 0) / total if total > 0 else 0.0
	_stats.text = tr("HMI_STATS") % [total, s.get("ok", 0), s.get("nok", 0), reject,
		s.get("klt_a", 0), s.get("capacity", 12), s.get("klt_b", 0), s.get("capacity", 12)]
	var a: float = s.get("availability", 0.0)
	var p: float = s.get("performance", 0.0)
	var q: float = s.get("quality", 0.0)
	_oee.text = tr("HMI_OEE") % [a * p * q * 100.0, a * 100.0, p * 100.0, q * 100.0]
	_alarm.text = s.get("alarm", "")
	var unacked: int = s.get("unacked", -1)
	_ack.visible = unacked >= 0
	_ack.disabled = unacked <= 0
	_ack.text = tr("HMI_ACK") % maxi(unacked, 0)
	var allowed := PackMLStateMachine.allowed_commands(s.get("state", 0))
	for cmd: int in _buttons:
		_buttons[cmd].disabled = cmd not in allowed
	_auto.set_pressed_no_signal(s.get("auto_exchange", true))


## Alarm text (one line, the layout has no spare row) and the acknowledge button of the alarm management.
func _alarm_row() -> HBoxContainer:
	var row := HBoxContainer.new()
	_alarm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(_alarm)
	_ack = Button.new()
	_ack.add_theme_font_size_override("font_size", 15)
	_ack.visible = false
	_ack.pressed.connect(func() -> void: ack_pressed.emit())
	row.add_child(_ack)
	return row


func _command_grid() -> GridContainer:
	var grid := GridContainer.new()
	grid.columns = 3
	for entry: Array in COMMANDS:
		var b := Button.new()
		b.text = entry[1]
		b.custom_minimum_size = Vector2(110, 36)
		b.add_theme_font_size_override("font_size", 17)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var cmd: int = entry[0]
		b.pressed.connect(func() -> void: command_pressed.emit(cmd))
		grid.add_child(b)
		_buttons[cmd] = b
	return grid


func _klt_row() -> HBoxContainer:
	var row := HBoxContainer.new()
	_auto = CheckButton.new()
	_auto.text = "HMI_AUTO_EXCHANGE"
	_auto.add_theme_font_size_override("font_size", 16)
	_auto.toggled.connect(func(on: bool) -> void: auto_exchange_toggled.emit(on))
	row.add_child(_auto)
	for container in [1, 2]:
		var b := Button.new()
		b.text = "HMI_EXCHANGE_A" if container == 1 else "HMI_EXCHANGE_B"
		b.add_theme_font_size_override("font_size", 16)
		b.pressed.connect(func() -> void: exchange_pressed.emit(container))
		row.add_child(b)
	return row


static func _state_color(state: int) -> Color:
	var s := PackMLStateMachine.State
	if state == s.EXECUTE:
		return UiTheme.OK
	if state in [s.STOPPED, s.ABORTED, s.ABORTING, s.STOPPING]:
		return UiTheme.ALARM
	return UiTheme.WARN
