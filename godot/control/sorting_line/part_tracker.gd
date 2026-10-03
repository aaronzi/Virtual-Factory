class_name PartTracker
extends RefCounted
## Infeed interlock and FIFO part tracking (serial numbers) from release to inspection.

var serials: Array[String] = []
var infeed_occupied := false
var infeed_faults := 0
var _last_release_count := 0
var _lb01_fall := IecFTrig.new()
var _timeout := IecTon.new()


func _init(infeed_timeout: float) -> void:
	_timeout.pt = infeed_timeout


func update(release_count: int, last_serial: String, lb01: bool, dt: float) -> void:
	if release_count != _last_release_count:
		_last_release_count = release_count
		serials.append(last_serial)
		infeed_occupied = true
	if _lb01_fall.update(lb01):
		infeed_occupied = false
	if _timeout.update(infeed_occupied and not lb01, dt):
		infeed_occupied = false
		infeed_faults += 1


## Serial of the part that just arrived at the inspection position ("" if tracking lost).
func pop_at_station() -> String:
	return serials.pop_front() if not serials.is_empty() else ""
