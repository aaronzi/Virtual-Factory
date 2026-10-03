extends DeviceNode
## UR5e device root. The robot base frame (Z-up, metres) sits on top of the pedestal at node "Base";
## Godot is Y-up, so robot coordinates are converted with Ur5eDeviceFrames.


func create_model(parameters: Dictionary) -> Fmi3CoSimulation:
	($Base as Node3D).position.y = geometry.get("pedestal_height", 0.75)
	return super.create_model(parameters)


func world_to_device_frame(world_position: Vector3) -> Vector3:
	return Ur5eDeviceFrames.ROBOT_TO_GODOT.inverse() * ($Base as Node3D).to_local(world_position)
