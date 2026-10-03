class_name LocalCommands
extends RefCounted
## Writes PLC/device inputs from in-world operator devices (HMI, KLT interaction) - the fieldbus path of a
## real HMI, not MQTT. Values are applied between master steps; pulse inputs (edge-triggered commands such as
## `packml_command`) are held for one step and then reset to 0, like the UNS gateway does.

var _master: CoSimMaster
var _queue: Array = []   # [path, value, pulse]
var _reset: Array = []   # paths to reset to 0 before the next step


func _init(master: CoSimMaster) -> void:
	_master = master


func write(path: String, value: Variant, pulse := false) -> void:
	_queue.append([path, value, pulse])


## Call once per physics frame before the co-simulation step.
func apply() -> void:
	var pulsing := {}  # paths that must not pulse this step (just reset, or already pulsed)
	for path: String in _reset:
		_write_var(path, 0)
		pulsing[path] = true
	_reset.clear()
	var pending := _queue
	_queue = []
	for entry: Array in pending:
		if entry[2] and pulsing.has(entry[0]):
			_queue.append(entry)  # one pulse per step and variable, with a 0 step in between
			continue
		_write_var(entry[0], entry[1])
		if entry[2]:
			pulsing[entry[0]] = true
			_reset.append(entry[0])


func _write_var(path: String, value: Variant) -> void:
	var parts := path.split(".", true, 1)
	var fmu := _master.get_instance(parts[0])
	if fmu == null:
		push_warning("LocalCommands: unknown instance in %s" % path)
		return
	fmu.set_value(parts[1], value)
