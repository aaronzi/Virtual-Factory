class_name RetentiveCounters
extends Node
## Retentive serial number counter of the assembly cell (like the retain memory of a PLC): live sessions
## continue the serial numbers of the previous run, so a serial - and the GS1 Digital Link of the part - is
## never reused; passports of shipped parts outlive the session (ADR-0025). Stored in user://retain.json and
## applied as the AC01 parameter serial_start before the co-simulation is initialised.
## --vf-serial-start=<n> sets the next serial, --vf-retain=off disables it; runs with --vf-uns=off (headless
## tests) start at the layout value, so they stay deterministic.

const PATH := "user://retain.json"
const CELL := "AC01"
const KEY := "AC01.serial_next"
const SAVE_S := 5.0

var master: CoSimMaster
var _start := -1  ## first serial of this run (-1: layout value)
var _timer := 0.0
var _enabled := false


## Parameter overrides for FactoryBuilder.parameter_overrides (before build).
func overrides(enabled: bool) -> Dictionary:
	_enabled = enabled
	var override := DevTools.get_arg("vf-serial-start")
	if override != "":
		_start = int(override)
	elif enabled:
		_start = int(_load().get(KEY, -1))
	return {CELL: {"serial_start": _start}} if _start > 0 else {}


## Starts saving the counter of the built co-simulation.
func attach(p_master: CoSimMaster) -> void:
	master = p_master
	if _start <= 0 and master.get_instance(CELL):
		_start = int(master.get_instance(CELL).get_value("serial_start"))
	set_process(_enabled)


func _process(delta: float) -> void:
	_timer -= delta
	if _timer <= 0.0:
		_timer = SAVE_S
		save()


func _exit_tree() -> void:
	save()


## Next serial number = first serial of this run + parts released so far.
func next_serial() -> int:
	return _start + int(master.read(CELL + ".release_count"))


func save() -> void:
	if not _enabled or master == null or master.get_instance(CELL) == null:
		return
	var file := FileAccess.open(PATH, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify({KEY: next_serial()}))


static func _load() -> Dictionary:
	if not FileAccess.file_exists(PATH):
		return {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	return data if data is Dictionary else {}
