class_name SafetyCircuit
extends Node
## Hard-wired safety circuit of LINE01 (like a safety relay): the fence door switch and the emergency stop
## on the HMI stand both stop the robot (RB01.protective_stop); the E-stop additionally opens the PLC's
## emergency-stop input (PLC01.estop -> alarm 100, line aborted; Clear only after the button is released).
## The E-stop is latching: click = press (latched), click again = release (twist).

const ROBOT_STOP := "RB01.protective_stop"
const PLC_ESTOP := "PLC01.estop"
## Position of the E-stop knob on the HMI stand (hmi_stand.glb, front = +Z).
const KNOB_POSITION := Vector3(0.18, 1.12, 0.168)

var master: CoSimMaster
var commands: LocalCommands
var door_open := false
var estop_latched := false
var _knob: MeshInstance3D


func setup(p_master: CoSimMaster, p_commands: LocalCommands) -> void:
	master = p_master
	commands = p_commands


func toggle_door() -> void:
	door_open = not door_open
	_apply()


func toggle_estop() -> void:
	estop_latched = not estop_latched
	commands.write(PLC_ESTOP, estop_latched)
	_apply()
	if _knob:
		_knob.position = KNOB_POSITION - Vector3(0, 0, 0.012 if estop_latched else 0.0)


func is_door_open() -> bool:
	return door_open


## The door also follows the robot input when a scenario or an MQTT command sets it (runs after
## LocalCommands.apply, see TrainingUi).
func _physics_process(_delta: float) -> void:
	if not estop_latched:
		door_open = bool(master.read(ROBOT_STOP))
	elif not master.read(ROBOT_STOP):
		commands.write(ROBOT_STOP, true)  # hard-wired: nothing releases the robot while the E-stop is latched


## Adds the clickable E-stop knob to the HMI stand.
func add_estop(stand: Node3D) -> void:
	_knob = MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.027
	mesh.bottom_radius = 0.027
	mesh.height = 0.03
	_knob.mesh = mesh
	_knob.rotation_degrees.x = 90.0
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.85, 0.08, 0.06)
	_knob.material_override = mat
	_knob.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF  # draw-call budget (ADR-0010)
	_knob.position = KNOB_POSITION
	stand.add_child(_knob)
	var body := StaticBody3D.new()
	body.collision_layer = Interactable.UI_LAYER
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.07, 0.07, 0.06)
	shape.shape = box
	body.add_child(shape)
	_knob.add_child(body)
	var click := _Click.new()
	click.on_press = toggle_estop
	_knob.add_child(click)
	click.register(body)


func _apply() -> void:
	commands.write(ROBOT_STOP, door_open or estop_latched)


class _Click:
	extends Interactable
	var on_press: Callable

	func pointer_pressed(_hit: Dictionary) -> void:
		on_press.call()
