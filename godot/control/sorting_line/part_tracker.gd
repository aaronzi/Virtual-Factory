class_name PartTracker
extends RefCounted
## Infeed interlock and FIFO part tracking (serial numbers) from release to inspection.
## Infeed timeout: a released part must reach LB01 within `infeed_timeout` s of belt running time
## (time with the belt stopped - held, inspecting, KLT exchange - does not count).

var serials: Array[String] = []
var infeed_occupied := false
var infeed_faults := 0
## Set by an infeed timeout (released part not seen at LB01), cleared by the next LB01 detection.
var timeout_alarm := false
var _last_release_count := 0
var _lb01_fall := IecFTrig.new()
var _timeout := 0.0
var _waited := 0.0


func _init(infeed_timeout: float) -> void:
	_timeout = infeed_timeout


func update(release_count: int, last_serial: String, lb01: bool, dt: float, belt_running := true) -> void:
	if release_count != _last_release_count:
		_last_release_count = release_count
		serials.append(last_serial)
		infeed_occupied = true
	if _lb01_fall.update(lb01):
		infeed_occupied = false
		timeout_alarm = false
	if not infeed_occupied or lb01:
		_waited = 0.0
	elif belt_running:
		_waited += dt
	if _waited >= _timeout - 1e-9:
		_waited = 0.0
		infeed_occupied = false
		infeed_faults += 1
		timeout_alarm = true


## Serial of the part that just arrived at the inspection position ("" if tracking lost).
func pop_at_station() -> String:
	return serials.pop_front() if not serials.is_empty() else ""
