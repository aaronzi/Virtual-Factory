extends Node3D
## Main scene composition: connects the factory runtime to desktop UI elements.

const PACKML_NAMES := ["UNDEFINED", "CLEARING", "STOPPED", "STARTING", "IDLE", "SUSPENDED", "EXECUTE",
	"STOPPING", "ABORTING", "ABORTED", "HOLDING", "HELD", "UNHOLDING", "SUSPENDING", "UNSUSPENDING",
	"RESETTING", "COMPLETING", "COMPLETE"]
const SEQ_NAMES := ["wait part", "positioning", "settling", "inspecting", "wait robot", "picking"]
const POWER_SOURCES := ["AC01", "CV01", "LB01", "LB02", "QS01", "RB01"]

@onready var _factory := $Factory
@onready var _overlay := $StatusOverlay


func _ready() -> void:
	_overlay.source = _status_text
	_apply_camera_arg(DevTools.get_arg("vf-camera"))


## --vf-camera=x,y,z,tx,ty,tz places the player rig (review screenshots).
func _apply_camera_arg(arg: String) -> void:
	var v := arg.split_floats(",")
	if v.size() == 6:
		($DesktopRig as PlayerRig).teleport_to(Vector3(v[0], v[1], v[2]), Vector3(v[3], v[4], v[5]))


func _status_text() -> String:
	var f = _factory
	if f.builder.devices.is_empty():
		return "Factory not running"
	var power := 0.0
	for id in POWER_SOURCES:
		power += f.read(id + ".power")
	return "\n".join([
		"LINE01  %s   t = %.0f s" % [PACKML_NAMES[f.read("PLC01.packml_state")], f.builder.master.time],
		"Sequence: %s   parts on belt: %d" % [
			SEQ_NAMES[f.read("PLC01.sequence_step")], f.read("PLC01.parts_on_belt")],
		"Parts: %d   OK: %d   NOK: %d" % [
			f.read("PLC01.parts_total"), f.read("PLC01.parts_ok"), f.read("PLC01.parts_nok")],
		"Last: %s  %s" % [f.read("PLC01.serial_at_qs"), ["-", "OK", "NOK"][f.read("PLC01.last_result")]],
		"KLT A: %d/12   KLT B: %d/12" % [f.read("KLTA01.fill_count"), f.read("KLTB01.fill_count")],
		"Robot step: %d   cycles: %d" % [f.read("RB01.program_step"), f.read("RB01.cycle_count")],
		"Line power: %.0f W" % power,
	])
