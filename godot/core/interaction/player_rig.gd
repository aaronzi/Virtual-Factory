class_name PlayerRig
extends Node3D
## Abstract player rig. All gameplay/UI code talks to the player only through this interface,
## so a DesktopRig (mouse/keyboard) and a later XRRig (XROrigin3D + controllers) are
## interchangeable (XR-readiness, see docs/adr/0003-xr-ready-architecture.md).

## Emitted when the rig's pointer (mouse ray or XR controller ray) presses on something.
signal pointer_pressed(hit: Dictionary)
## Emitted when the pointer button / trigger is released (hit may be empty).
signal pointer_released(hit: Dictionary)
## Emitted when the user scrolls at the pointer (mouse wheel, trackpad, XR thumbstick), in wheel steps:
## y > 0 scrolls the content down, x > 0 to the right.
signal pointer_scrolled(amount: Vector2)


## True while the pointer can be used for UI (e.g. not while the desktop camera is being rotated).
func is_pointer_active() -> bool:
	return true


## World-space origin and direction of the rig's primary pointer ray.
func get_pointer_ray() -> Dictionary:
	push_error("PlayerRig.get_pointer_ray() not implemented by %s" % get_script().resource_path)
	return {"origin": global_position, "direction": -global_basis.z}


## The camera that currently renders the player's view (head camera in XR).
func get_view_camera() -> Camera3D:
	push_error("PlayerRig.get_view_camera() not implemented by %s" % get_script().resource_path)
	return null


## Moves the rig so that the view looks from `from` towards `target` (used by tours/scenarios).
func teleport_to(from: Vector3, target: Vector3) -> void:
	global_position = from
	look_at(target, Vector3.UP)
