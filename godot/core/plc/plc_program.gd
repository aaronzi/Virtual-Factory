class_name PlcProgram
extends Fmi3CoSimulation
## Base class for virtual PLC programs. A PLC program is itself an FMI co-simulation slave whose
## variables are the PLC's process image (inputs %I, outputs %Q, parameters), so it is wired with
## the same connection mechanism as the devices.
##
## do_step() is subdivided into cyclic scans of `scan_time` seconds; subclasses implement _scan(dt).
## A PackML state machine is provided; commands arrive via the `packml_command` input (edge-triggered).

var packml := PackMLStateMachine.new()
var _scan_accumulator := 0.0
var _last_command := 0


func _on_step(_t: float, h: float) -> int:
	var scan_time: float = maxf(_get_var("scan_time"), 0.001)
	_scan_accumulator += h
	while _scan_accumulator >= scan_time - 1e-9:
		_scan_accumulator -= scan_time
		_handle_packml_command()
		_scan(scan_time)
		packml.update(scan_time)
		_set_var("packml_state", packml.state)
	return Fmi3.Status.OK


## One PLC scan cycle (override).
func _scan(_dt: float) -> void:
	pass


func _handle_packml_command() -> void:
	var cmd: int = _get_var("packml_command")
	if cmd != _last_command and cmd != PackMLStateMachine.Command.NONE:
		packml.command(cmd)
	_last_command = cmd
