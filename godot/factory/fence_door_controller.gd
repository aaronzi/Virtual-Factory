class_name FenceDoorController
extends Node
## Interlocked door of the robot safety fence: clicking it opens/closes the door and sets RB01.protective_stop
## (the door switch); the robot pauses, the PLC holds the line with alarm 201 and resumes when it is closed.
## The door also follows the input when a scenario or an MQTT command sets it.

const INPUT := "RB01.protective_stop"
const OPEN_DEG := 95.0
const SWING_DEG_PER_S := 180.0

var master: CoSimMaster
var commands: LocalCommands
var safety: SafetyCircuit
var door: Node3D
var _closed_rotation := 0.0
var _angle := 0.0


## Returns false if the fence prop has no door object.
func setup(p_master: CoSimMaster, p_commands: LocalCommands, fence: Node3D) -> bool:
	master = p_master
	commands = p_commands
	door = fence.find_child("Door", true, false) as Node3D
	if door == null:
		return false
	_closed_rotation = door.rotation.y
	var body := StaticBody3D.new()
	body.collision_layer = Interactable.UI_LAYER
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	var bounds := _bounds(door)
	box.size = bounds.size.max(Vector3.ONE * 0.04)
	shape.shape = box
	shape.position = bounds.get_center()
	body.add_child(shape)
	door.add_child(body)
	var click := _DoorClick.new()
	click.controller = self
	door.add_child(click)
	click.register(body)
	return true


func toggle() -> void:
	if safety:
		safety.toggle_door()
	else:
		commands.write(INPUT, not is_open())


func is_open() -> bool:
	return safety.is_door_open() if safety else bool(master.read(INPUT))


func _process(delta: float) -> void:
	if door == null:
		return
	var target := OPEN_DEG if is_open() else 0.0
	_angle = move_toward(_angle, target, SWING_DEG_PER_S * delta)
	door.rotation.y = _closed_rotation - deg_to_rad(_angle)


static func _bounds(node: Node3D) -> AABB:
	var result := AABB()
	var first := true
	var inverse := node.global_transform.affine_inverse()
	for mesh: MeshInstance3D in node.find_children("*", "MeshInstance3D", true, true) + [node]:
		if not mesh is MeshInstance3D:
			continue
		var local := inverse * mesh.global_transform * mesh.get_aabb()
		result = local if first else result.merge(local)
		first = false
	return result


class _DoorClick:
	extends Interactable
	var controller: FenceDoorController

	func pointer_pressed(_hit: Dictionary) -> void:
		controller.toggle()
