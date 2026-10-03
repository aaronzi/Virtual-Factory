class_name DeviceView
extends Node3D
## Device view: maps model outputs to the 3D representation (animations, lights, physics
## actuation such as belt velocity) after each co-simulation step.

var device: DeviceNode


func bind(p_device: DeviceNode) -> void:
	device = p_device


func apply(_model: Fmi3CoSimulation, _delta: float) -> void:
	pass
