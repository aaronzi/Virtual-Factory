class_name RobotJobHandshake
extends RefCounted
## PLC side of the robot job handshake: request (job_start) -> robot job_done -> acknowledge.
## The job remembers the serial of the part to pick so the PLC can report where it was sorted.

enum Phase { IDLE, REQUESTED, ACKNOWLEDGING }

var phase := Phase.IDLE
var target := 1
var slot := 0
var serial := ""


func request(p_target: int, p_slot: int, p_serial := "") -> bool:
	if phase != Phase.IDLE:
		return false
	target = p_target
	slot = p_slot
	serial = p_serial
	phase = Phase.REQUESTED
	return true


## Returns true in the scan in which the robot reports the requested job as done.
func update(job_done: bool) -> bool:
	if phase == Phase.REQUESTED and job_done:
		phase = Phase.ACKNOWLEDGING
		return true
	if phase == Phase.ACKNOWLEDGING and not job_done:
		phase = Phase.IDLE
	return false


func job_start() -> bool:
	return phase == Phase.REQUESTED


func is_idle() -> bool:
	return phase == Phase.IDLE
