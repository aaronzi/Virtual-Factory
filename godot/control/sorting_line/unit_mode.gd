class_name PlcUnitMode
extends RefCounted
## PackML unit mode (ISA-TR88.00.02) of the line controller. A change is requested by an edge on
## `unit_mode_command` and accepted only in a wait state without motion (STOPPED, IDLE, ABORTED).
##   PRODUCTION   normal operation (auto start, infeed from AC01)
##   MAINTENANCE  the line can run (belt, inspection, robot), but AC01 releases no parts and the
##                controller does not start by itself - e.g. for predictive maintenance runs
##   MANUAL       like MAINTENANCE (no jog functions in the simulation)

enum Mode { PRODUCTION = 1, MAINTENANCE = 2, MANUAL = 3 }
const S := PackMLStateMachine.State
const CHANGE_STATES := [S.STOPPED, S.IDLE, S.ABORTED]

var mode := Mode.PRODUCTION
var _last_command := 0


## Evaluates the command input once per scan. Returns true if the mode changed.
func update(command: int, state: int) -> bool:
	var edge := command != _last_command
	_last_command = command
	if not edge or command == mode or not command in Mode.values() or not state in CHANGE_STATES:
		return false
	mode = command as Mode
	return true


func is_production() -> bool:
	return mode == Mode.PRODUCTION
