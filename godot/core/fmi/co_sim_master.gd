class_name CoSimMaster
extends RefCounted
## Fixed-step Gauss-Seidel co-simulation master (ADR-0002).
##
## Instances are stepped in insertion order. Before an instance steps, all of its connected inputs
## are copied from the source outputs, so later instances see this step's outputs of earlier ones
## (Gauss-Seidel); earlier instances see the previous step's values (one-step delay, like PLC I/O).

var time := 0.0
var _instances: Array[Fmi3CoSimulation] = []
var _by_name := {}
var _incoming := {}  # instance name -> Array of [src_fmu, src_vr, dst_vr]


func add_instance(fmu: Fmi3CoSimulation) -> void:
	assert(not _by_name.has(fmu.instance_name), "duplicate instance " + fmu.instance_name)
	_instances.append(fmu)
	_by_name[fmu.instance_name] = fmu
	_incoming[fmu.instance_name] = []


func get_instance(instance_name: String) -> Fmi3CoSimulation:
	return _by_name.get(instance_name)


func get_instances() -> Array[Fmi3CoSimulation]:
	return _instances


## Connects `src.output` to `dst.input` using "INSTANCE.variable" notation. Returns OK or an error.
func connect_variables(src_path: String, dst_path: String) -> Error:
	var src := _resolve(src_path)
	var dst := _resolve(dst_path)
	if src.is_empty() or dst.is_empty():
		push_error("CoSimMaster: unknown endpoint in %s -> %s" % [src_path, dst_path])
		return ERR_DOES_NOT_EXIST
	var sv: Fmi3Variable = src.variable
	var dv: Fmi3Variable = dst.variable
	if not sv.is_output() or dv.causality != Fmi3.Causality.INPUT:
		push_error("CoSimMaster: %s must be an output and %s an input" % [src_path, dst_path])
		return ERR_INVALID_PARAMETER
	if sv.type != dv.type:
		push_error("CoSimMaster: type mismatch %s -> %s" % [src_path, dst_path])
		return ERR_INVALID_DATA
	_incoming[dst.fmu.instance_name].append([src.fmu, sv.value_reference, dv.value_reference])
	return OK


## Enters and exits initialization mode for all instances, then propagates outputs once.
func initialize(start_time := 0.0) -> void:
	time = start_time
	for fmu in _instances:
		fmu.enter_initialization_mode(start_time)
	for fmu in _instances:
		_apply_inputs(fmu)
		fmu.exit_initialization_mode()
	for fmu in _instances:
		_apply_inputs(fmu)


## Advances all instances by `h` seconds. Returns the worst status of all instances.
func step(h: float) -> int:
	var worst := Fmi3.Status.OK
	for fmu in _instances:
		_apply_inputs(fmu)
		var result := fmu.do_step(time, h)
		if result.status > Fmi3.Status.WARNING:
			push_warning("CoSimMaster: %s do_step -> %s" % [
				fmu.instance_name, Fmi3.status_name(result.status)])
		worst = maxi(worst, result.status)
	time += h
	return worst


## Reads a variable by "INSTANCE.variable" path (for views, gateways and tests).
func read(path: String) -> Variant:
	var ep := _resolve(path)
	return ep.fmu.get_value_by_vr(ep.variable.value_reference) if not ep.is_empty() else null


func _apply_inputs(fmu: Fmi3CoSimulation) -> void:
	for conn in _incoming[fmu.instance_name]:
		fmu.set_value_by_vr(conn[2], conn[0].get_value_by_vr(conn[1]))


func _resolve(path: String) -> Dictionary:
	var parts := path.split(".", true, 1)
	if parts.size() != 2 or not _by_name.has(parts[0]):
		return {}
	var fmu: Fmi3CoSimulation = _by_name[parts[0]]
	var v := fmu.model_description.get_variable(parts[1])
	return {"fmu": fmu, "variable": v} if v else {}
