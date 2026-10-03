class_name PackMLStateMachine
extends RefCounted
## PackML unit state model (ISA-TR88.00.02). State and command numbers follow the standard.
##
## Acting states (STARTING, STOPPING, ...) end when the program calls state_complete(); if
## `auto_complete` is true they complete automatically on the next update().

signal state_changed(old_state: int, new_state: int)

enum State {
	UNDEFINED, CLEARING, STOPPED, STARTING, IDLE, SUSPENDED, EXECUTE, STOPPING, ABORTING, ABORTED,
	HOLDING, HELD, UNHOLDING, SUSPENDING, UNSUSPENDING, RESETTING, COMPLETING, COMPLETE,
}
enum Command { NONE, RESET, START, STOP, HOLD, UNHOLD, SUSPEND, UNSUSPEND, ABORT, CLEAR }

## Acting state -> state reached on completion (SC).
const ACTING_TARGETS := {
	State.CLEARING: State.STOPPED, State.STARTING: State.EXECUTE, State.STOPPING: State.STOPPED,
	State.ABORTING: State.ABORTED, State.HOLDING: State.HELD, State.UNHOLDING: State.EXECUTE,
	State.SUSPENDING: State.SUSPENDED, State.UNSUSPENDING: State.EXECUTE,
	State.RESETTING: State.IDLE, State.COMPLETING: State.COMPLETE,
}
## [from state, command] -> acting state entered.
const COMMAND_TRANSITIONS := {
	[State.STOPPED, Command.RESET]: State.RESETTING,
	[State.COMPLETE, Command.RESET]: State.RESETTING,
	[State.IDLE, Command.START]: State.STARTING,
	[State.EXECUTE, Command.HOLD]: State.HOLDING,
	[State.HELD, Command.UNHOLD]: State.UNHOLDING,
	[State.EXECUTE, Command.SUSPEND]: State.SUSPENDING,
	[State.SUSPENDED, Command.UNSUSPEND]: State.UNSUSPENDING,
	[State.ABORTED, Command.CLEAR]: State.CLEARING,
}
const STOPPABLE := [
	State.IDLE, State.STARTING, State.EXECUTE, State.HOLDING, State.HELD, State.UNHOLDING,
	State.SUSPENDING, State.SUSPENDED, State.UNSUSPENDING, State.RESETTING, State.COMPLETING,
	State.COMPLETE,
]

var state := State.STOPPED
var auto_complete := true
var time_in_state := 0.0
var _complete_requested := false


## Applies a command. Returns true if it caused a transition.
func command(cmd: int) -> bool:
	if cmd == Command.ABORT and state not in [State.ABORTING, State.ABORTED]:
		_enter(State.ABORTING)
		return true
	if cmd == Command.STOP and state in STOPPABLE:
		_enter(State.STOPPING)
		return true
	var key := [state, cmd]
	if COMMAND_TRANSITIONS.has(key):
		_enter(COMMAND_TRANSITIONS[key])
		return true
	return false


## Signals that the current acting state has finished (or, in EXECUTE, that production is complete).
func state_complete() -> void:
	_complete_requested = true


func update(dt: float) -> void:
	time_in_state += dt
	if state == State.EXECUTE and _complete_requested:
		_enter(State.COMPLETING)
	elif ACTING_TARGETS.has(state) and (_complete_requested or auto_complete):
		_enter(ACTING_TARGETS[state])


func is_acting() -> bool:
	return ACTING_TARGETS.has(state)


func state_name() -> String:
	return State.keys()[state]


func _enter(new_state: int) -> void:
	var old := state
	state = new_state
	time_in_state = 0.0
	_complete_requested = false
	state_changed.emit(old, new_state)
