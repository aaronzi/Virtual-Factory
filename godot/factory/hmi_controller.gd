class_name HmiController
extends Node
## Drives the HMI view on the HMI stand from the PLC process image (local fieldbus, not MQTT) and executes
## the operator's commands. OEE (ISO 22400) is computed from the PackML state durations of this session.
## Alarm acknowledgement goes to the alarms service (ISA-18.2, REST), polled every ALARMS_POLL_S.

const REFRESH_S := 0.25
const ALARMS_POLL_S := 2.0
const PLC := "PLC01"
const OPERATOR := "HMI01 (operator panel LINE01)"

var master: CoSimMaster
var commands: LocalCommands
var view: HmiView
var panel: WorldPanel
var alarms: AlarmsClient  ## optional; null = no acknowledge button
var _timer := 0.0
var _alarms_timer := 0.0
var _unacked := -1
var _polling := false
var _seconds := {"execute": 0.0, "planned": 0.0}
var _last_time := 0.0


func setup(p_master: CoSimMaster, p_commands: LocalCommands, stand: Node3D) -> void:
	master = p_master
	commands = p_commands
	view = HmiView.new()
	view.command_pressed.connect(func(c: int) -> void: commands.write(PLC + ".packml_command", c, true))
	view.auto_exchange_toggled.connect(func(on: bool) -> void: commands.write(PLC + ".auto_exchange", on))
	view.exchange_pressed.connect(func(k: int) -> void: commands.write(PLC + ".klt_exchange_command", k, true))
	view.ack_pressed.connect(_acknowledge)
	panel = WorldPanel.new()
	panel.size_m = Vector2(0.48, 0.34)
	panel.pixels_per_meter = 1100.0
	panel.refresh_hz = 1.0 / REFRESH_S
	panel.set_content(view)
	stand.add_child(panel)
	panel.position = Vector3(0.0, 1.3, 0.043)  # over the screen of the stand (front = +Z)


func _process(delta: float) -> void:
	_alarms_timer -= delta
	if alarms and _alarms_timer <= 0.0 and not _polling:
		_alarms_timer = ALARMS_POLL_S
		_poll_alarms()
	_timer -= delta
	if _timer > 0.0:
		return
	_timer = REFRESH_S
	view.update_status(status())


func status() -> Dictionary:
	var state: int = _read(PLC + ".packml_state", 0)
	_account(state)
	var total: int = _read(PLC + ".parts_total", 0)
	var ok: int = _read(PLC + ".parts_ok", 0)
	var takt: float = _read("AC01.takt_time", 12.0)
	var execute: float = _seconds.execute
	return {"state": state, "state_name": PackMLStateMachine.State.keys()[state],
		"total": total, "ok": ok, "nok": _read(PLC + ".parts_nok", 0),
		"klt_a": _read("KLTA01.fill_count", 0), "klt_b": _read("KLTB01.fill_count", 0),
		"capacity": _read(PLC + ".klt_capacity", 12), "auto_exchange": _read(PLC + ".auto_exchange", true),
		"alarm": str(_read(PLC + ".alarm_text", "")), "unacked": _unacked,
		"availability": execute / _seconds.planned if _seconds.planned > 1.0 else 0.0,
		"performance": minf(total * takt / execute, 1.0) if execute > 1.0 else 0.0,
		"quality": float(ok) / total if total > 0 else 0.0}


func _poll_alarms() -> void:
	_polling = true
	_unacked = await alarms.unacknowledged()
	_polling = false


func _acknowledge() -> void:
	if alarms and await alarms.ack_all(OPERATOR):
		_unacked = 0
	_alarms_timer = 0.0


## Planned time = time not spent STOPPED/IDLE (line meant to produce); production time = EXECUTE.
func _account(state: int) -> void:
	var dt := master.time - _last_time
	_last_time = master.time
	var s := PackMLStateMachine.State
	if state not in [s.STOPPED, s.IDLE, s.UNDEFINED]:
		_seconds.planned += dt
	if state == s.EXECUTE:
		_seconds.execute += dt


func _read(path: String, fallback: Variant) -> Variant:
	var v: Variant = master.read(path)
	return fallback if v == null else v
