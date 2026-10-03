class_name RobotJobHandshake
extends RefCounted
## PLC side of the robot job handshake: request (job_start) -> robot job_done -> acknowledge.

enum Phase { IDLE, REQUESTED, ACKNOWLEDGING }

var phase := Phase.IDLE
var target := 1
var slot := 0


func request(p_target: int, p_slot: int) -> bool:
	if phase != Phase.IDLE:
		return false
	target = p_target
	slot = p_slot
	phase = Phase.REQUESTED
	return true


func update(job_done: bool) -> void:
	if phase == Phase.REQUESTED and job_done:
		phase = Phase.ACKNOWLEDGING
	elif phase == Phase.ACKNOWLEDGING and not job_done:
		phase = Phase.IDLE


func job_start() -> bool:
	return phase == Phase.REQUESTED


func is_idle() -> bool:
	return phase == Phase.IDLE
