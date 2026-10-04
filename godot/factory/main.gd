extends Node3D
## Main scene composition: connects the factory runtime to desktop UI elements.

const PACKML_NAMES := ["UNDEFINED", "CLEARING", "STOPPED", "STARTING", "IDLE", "SUSPENDED", "EXECUTE",
	"STOPPING", "ABORTING", "ABORTED", "HOLDING", "HELD", "UNHOLDING", "SUSPENDING", "UNSUSPENDING",
	"RESETTING", "COMPLETING", "COMPLETE"]
const SEQ_NAMES := ["SEQ_WAIT_PART", "SEQ_POSITIONING", "SEQ_SETTLING", "SEQ_INSPECTING", "SEQ_WAIT_ROBOT",
	"SEQ_PICKING"]
const POWER_SOURCES := ["AC01", "CV01", "LB01", "LB02", "QS01", "RB01"]
const BAKED_LIGHTING := "res://world/lighting/baked/%s"  ## per layout, made by tools/bake_lighting.sh

var training_ui: TrainingUi

@onready var _factory := $Factory
@onready var _overlay := $StatusOverlay


func _ready() -> void:
	_overlay.source = _status_text
	_overlay.visible = DevTools.get_arg("vf-overlay", "on") != "off"
	var hall := $Hall as Hall
	var interior := hall.get_interior_bounds()
	($DesktopRig as DesktopRig).bounds = AABB(hall.to_global(interior.position) + Vector3(0, 0.3, 0),
		interior.size - Vector3(0, 0.3, 0))
	_apply_camera_arg(DevTools.get_arg("vf-camera"))
	_apply_baked_lighting()
	var mouse := DevTools.get_arg("vf-mouse").split_floats(",")  # --vf-mouse=x,y (screenshots of hover)
	if mouse.size() == 2:
		Input.warp_mouse.call_deferred(Vector2(mouse[0], mouse[1]))
	var rig := _select_rig()
	if not _factory.builder.devices.is_empty() and DevTools.get_arg("vf-ui", "on") != "off":
		training_ui = TrainingUi.new()
		training_ui.name = "TrainingUi"
		add_child(training_ui)
		training_ui.setup(_factory, rig)
	else:
		QualitySettings.apply(self, int(DevTools.get_arg("vf-quality", "1")))


## --vf-xr: use the OpenXR rig if a runtime is available (ADR-0003), otherwise keep the desktop rig.
func _select_rig() -> PlayerRig:
	var desktop := $DesktopRig as PlayerRig
	if DevTools.get_arg("vf-xr") == "":
		return desktop
	var xr := XRRig.new()
	xr.name = "XRRig"
	add_child(xr)
	if not xr.try_start():
		push_warning("XR requested but no OpenXR runtime available - using the desktop rig")
		xr.queue_free()
		return desktop
	xr.teleport_to(desktop.global_position, desktop.global_position - desktop.global_basis.z)
	desktop.get_view_camera().current = false
	desktop.process_mode = Node.PROCESS_MODE_DISABLED
	return xr


## Baked static lighting for the layout (ADR-0031); --vf-baked-lighting=off keeps real-time shadows only.
func _apply_baked_lighting() -> void:
	if _factory.builder.devices.is_empty() or DevTools.get_arg("vf-baked-lighting") == "off":
		return
	var layout_name: String = _factory.layout_path.get_file().get_slice(".", 0)
	if BakedLighting.apply(self, BAKED_LIGHTING % layout_name):
		print("[Lighting] baked lighting: ", BAKED_LIGHTING % layout_name)


## --vf-camera=x,y,z,tx,ty,tz places the player rig (review screenshots).
func _apply_camera_arg(arg: String) -> void:
	var v := arg.split_floats(",")
	if v.size() == 6:
		($DesktopRig as PlayerRig).teleport_to(Vector3(v[0], v[1], v[2]), Vector3(v[3], v[4], v[5]))


func _status_text() -> String:
	var f = _factory
	if f.builder.devices.is_empty():
		return tr("OVERLAY_NOT_RUNNING")
	var power := 0.0
	for id in POWER_SOURCES:
		power += f.read(id + ".power")
	return "\n".join([
		"LINE01  %s   t = %.0f s" % [PACKML_NAMES[f.read("PLC01.packml_state")], f.builder.master.time],
		tr("OVERLAY_SEQUENCE") % [_seq_name(f.read("PLC01.sequence_step")), f.read("PLC01.parts_on_belt")],
		tr("OVERLAY_PARTS") % [
			f.read("PLC01.parts_total"), f.read("PLC01.parts_ok"), f.read("PLC01.parts_nok")],
		tr("OVERLAY_LAST") % [f.read("PLC01.serial_at_qs"), ["-", "OK", "NOK"][f.read("PLC01.last_result")]],
		"KLT A: %d/12   KLT B: %d/12" % [f.read("KLTA01.fill_count"), f.read("KLTB01.fill_count")],
		tr("OVERLAY_ROBOT") % [f.read("RB01.program_step"), f.read("RB01.cycle_count")],
		tr("OVERLAY_POWER") % power,
	])


func _seq_name(step: int) -> String:
	return tr(SEQ_NAMES[step]) if step >= 0 and step < SEQ_NAMES.size() else str(step)
