class_name LineAlarms
extends RefCounted
## Alarm handling of LINE01. Each scan the program passes the alarm conditions (code -> active); the
## first active alarm in ALARMS order (= priority) is reported as `code`/`text`. Reactions (PackML):
##   ABORT      level: while active the unit is driven to ABORTED (Clear only works once it is gone)
##   HOLD       on the rising edge: HOLD; the operator unholds
##   HOLD_AUTO  level: HOLD while active in EXECUTE, automatic UNHOLD once all HOLD_AUTO alarms are gone
##   NONE       warning only
## Codes are documented in docs/interfaces/scenarios.md.

enum Reaction { NONE, HOLD, HOLD_AUTO, ABORT }

const ALARMS := {
	101: ["CV01 conveyor drive fault", Reaction.ABORT],
	202: ["RB01 robot fault", Reaction.HOLD],
	201: ["RB01 protective stop (safety fence door open)", Reaction.HOLD_AUTO],
	302: ["LB02 inspection light barrier blocked (signal stuck)", Reaction.HOLD_AUTO],
	301: ["LB01 infeed light barrier blocked (signal stuck)", Reaction.HOLD_AUTO],
	401: ["Infeed tracking timeout: released part not detected at LB01", Reaction.NONE],
}
const S := PackMLStateMachine.State
const C := PackMLStateMachine.Command

var code := 0
var text := ""
var count := 0  ## alarms raised since start (rising edges)
var _active := {}
var _auto_held := false


## Updates the alarm list from `conditions` (code -> bool) and applies the PackML reactions.
func update(conditions: Dictionary, packml: PackMLStateMachine) -> void:
	code = 0
	text = ""
	for c: int in ALARMS:
		var on: bool = conditions.get(c, false)
		if on and not _active.get(c, false):
			count += 1
			if ALARMS[c][1] == Reaction.HOLD:
				packml.command(C.HOLD)
		_active[c] = on
		if on and code == 0:
			code = c
			text = ALARMS[c][0]
	_react(packml)


func _react(packml: PackMLStateMachine) -> void:
	if is_active(Reaction.ABORT) and packml.state not in [S.ABORTING, S.ABORTED]:
		packml.command(C.ABORT)
	var hold := is_active(Reaction.HOLD_AUTO)
	if hold and packml.state == S.EXECUTE:
		_auto_held = packml.command(C.HOLD)
	elif not hold and _auto_held and packml.state == S.HELD:
		packml.command(C.UNHOLD)
		_auto_held = false
	elif packml.state not in [S.HOLDING, S.HELD]:
		_auto_held = false


## True if any alarm with the given reaction is active.
func is_active(reaction: int) -> bool:
	for c: int in _active:
		if _active[c] and ALARMS[c][1] == reaction:
			return true
	return false


## Red stack light / horn: an active alarm that stops the line (not a warning).
func stops_line() -> bool:
	return is_active(Reaction.ABORT) or is_active(Reaction.HOLD) or is_active(Reaction.HOLD_AUTO)
