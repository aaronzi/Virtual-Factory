class_name DeviceProbe
extends Node3D
## Environment probe: samples the physical world (raycasts, overlaps, surface colours) and writes
## the result into the device model's physical inputs before each co-simulation step.

var device: DeviceNode


func bind(p_device: DeviceNode) -> void:
	device = p_device


func sample(_model: Fmi3CoSimulation, _delta: float) -> void:
	pass
