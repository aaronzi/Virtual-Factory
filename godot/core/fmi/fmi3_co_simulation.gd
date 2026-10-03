class_name Fmi3CoSimulation  # gdlint:ignore=max-public-methods
extends RefCounted
## Base class mirroring the FMI 3.0 Co-Simulation C API (ADR-0002). Exceeds the public-method
## limit by design: one method per FMI function (documented complexity exception).
##
## FMI function            -> method
## fmi3InstantiateCoSimulation -> instantiate()
## fmi3EnterInitializationMode -> enter_initialization_mode()
## fmi3ExitInitializationMode  -> exit_initialization_mode()
## fmi3DoStep              -> do_step()
## fmi3Get/SetFloat64 ...  -> get_float64()/set_float64() ... (status of getters in `last_status`)
## fmi3Get/SetFMUState     -> get_fmu_state()/set_fmu_state()
## fmi3Reset/Terminate/FreeInstance -> reset()/terminate()/free_instance()
##
## Subclasses implement the behaviour in _on_initialize(), _on_step(), _on_reset() and keep any
## internal state in _save_internal_state()/_load_internal_state() so FMU state snapshots are complete.
## They must not access the scene tree (models are pure logic, headless-testable).

enum Phase { NONE, INSTANTIATED, INITIALIZATION, STEP, TERMINATED }

var instance_name := ""
var model_description: Fmi3ModelDescription
var current_time := 0.0
var last_status := Fmi3.Status.OK
var phase := Phase.NONE
var logging_on := false
var _values := {}


# --- life cycle -------------------------------------------------------------------------------

func instantiate(p_instance_name: String, p_description: Fmi3ModelDescription,
		instantiation_token := "", p_logging_on := false) -> int:
	if p_description == null:
		return Fmi3.Status.FATAL
	if instantiation_token != "" and instantiation_token != p_description.instantiation_token:
		_log("instantiation token mismatch")
		return Fmi3.Status.ERROR
	instance_name = p_instance_name
	model_description = p_description
	logging_on = p_logging_on
	_apply_start_values()
	phase = Phase.INSTANTIATED
	return Fmi3.Status.OK


func enter_initialization_mode(start_time := 0.0, _stop_time := -1.0, _tolerance := 0.0) -> int:
	if phase != Phase.INSTANTIATED:
		return _illegal_call("enter_initialization_mode")
	current_time = start_time
	phase = Phase.INITIALIZATION
	return Fmi3.Status.OK


func exit_initialization_mode() -> int:
	if phase != Phase.INITIALIZATION:
		return _illegal_call("exit_initialization_mode")
	_on_initialize()
	phase = Phase.STEP
	return Fmi3.Status.OK


func do_step(current_communication_point: float, communication_step_size: float,
		_no_set_fmu_state_prior := true) -> Fmi3DoStepResult:
	var result := Fmi3DoStepResult.new()
	if phase != Phase.STEP or communication_step_size <= 0.0:
		result.status = _illegal_call("do_step")
		return result
	current_time = current_communication_point
	result.status = _on_step(current_communication_point, communication_step_size)
	if result.status <= Fmi3.Status.WARNING:
		current_time = current_communication_point + communication_step_size
	result.last_successful_time = current_time
	return result


func reset() -> int:
	_apply_start_values()
	current_time = 0.0
	_on_reset()
	phase = Phase.INSTANTIATED
	return Fmi3.Status.OK


func terminate() -> int:
	phase = Phase.TERMINATED
	return Fmi3.Status.OK


func free_instance() -> void:
	_values.clear()
	phase = Phase.NONE


# --- typed access by value reference ------------------------------------------------------------

func get_float64(vrs: PackedInt64Array) -> PackedFloat64Array:
	return PackedFloat64Array(_get_typed(vrs, Fmi3.VarType.FLOAT64))


func get_int32(vrs: PackedInt64Array) -> PackedInt64Array:
	return PackedInt64Array(_get_typed(vrs, Fmi3.VarType.INT32))


func get_uint64(vrs: PackedInt64Array) -> PackedInt64Array:
	return PackedInt64Array(_get_typed(vrs, Fmi3.VarType.UINT64))


func get_boolean(vrs: PackedInt64Array) -> Array:
	return _get_typed(vrs, Fmi3.VarType.BOOLEAN)


func get_string(vrs: PackedInt64Array) -> PackedStringArray:
	return PackedStringArray(_get_typed(vrs, Fmi3.VarType.STRING))


func set_float64(vrs: PackedInt64Array, values: PackedFloat64Array) -> int:
	return _set_typed(vrs, Array(values), Fmi3.VarType.FLOAT64)


func set_int32(vrs: PackedInt64Array, values: PackedInt64Array) -> int:
	return _set_typed(vrs, Array(values), Fmi3.VarType.INT32)


func set_uint64(vrs: PackedInt64Array, values: PackedInt64Array) -> int:
	return _set_typed(vrs, Array(values), Fmi3.VarType.UINT64)


func set_boolean(vrs: PackedInt64Array, values: Array) -> int:
	return _set_typed(vrs, values, Fmi3.VarType.BOOLEAN)


func set_string(vrs: PackedInt64Array, values: PackedStringArray) -> int:
	return _set_typed(vrs, Array(values), Fmi3.VarType.STRING)


# --- untyped convenience used by the co-simulation master and the composition root -------------

## Reads any variable by value reference (FMI rules: all variables are readable).
func get_value_by_vr(vr: int) -> Variant:
	return _values.get(vr)


## Sets an input/parameter by value reference, enforcing FMI causality rules. Returns a status.
func set_value_by_vr(vr: int, value: Variant) -> int:
	var v := model_description.get_variable_by_vr(vr)
	if v == null or not _is_settable(v):
		_log("variable vr=%d not settable in phase %s" % [vr, Phase.keys()[phase]])
		return Fmi3.Status.ERROR
	_values[vr] = Fmi3.coerce(v.type, value)
	return Fmi3.Status.OK


func get_value(var_name: String) -> Variant:
	var v := model_description.get_variable(var_name)
	return _values.get(v.value_reference) if v else null


func set_value(var_name: String, value: Variant) -> int:
	var v := model_description.get_variable(var_name)
	if v == null:
		_log("unknown variable '%s'" % var_name)
		return Fmi3.Status.ERROR
	return set_value_by_vr(v.value_reference, value)


# --- FMU state ----------------------------------------------------------------------------------

func get_fmu_state() -> Dictionary:
	return {"time": current_time, "values": _values.duplicate(true), "internal": _save_internal_state()}


func set_fmu_state(state: Dictionary) -> int:
	current_time = state.get("time", 0.0)
	_values = state.get("values", {}).duplicate(true)
	_load_internal_state(state.get("internal", {}))
	return Fmi3.Status.OK


# --- for subclasses -----------------------------------------------------------------------------

## Behaviour hooks (override).
func _on_initialize() -> void:
	pass


func _on_step(_t: float, _h: float) -> int:
	return Fmi3.Status.OK


func _on_reset() -> void:
	pass


func _save_internal_state() -> Dictionary:
	return {}


func _load_internal_state(_state: Dictionary) -> void:
	pass


## Internal read of any variable by name.
func _get_var(var_name: String) -> Variant:
	return _values[model_description.get_variable(var_name).value_reference]


## Internal write of any variable by name (used to set outputs/locals; no causality check).
func _set_var(var_name: String, value: Variant) -> void:
	var v := model_description.get_variable(var_name)
	_values[v.value_reference] = Fmi3.coerce(v.type, value)


func _log(message: String) -> void:
	if logging_on:
		print("[FMU %s] %s" % [instance_name, message])


# --- private ------------------------------------------------------------------------------------

func _apply_start_values() -> void:
	_values.clear()
	for v in model_description.variables:
		_values[v.value_reference] = v.start


func _is_settable(v: Fmi3Variable) -> bool:
	if phase == Phase.STEP:
		return v.is_settable_in_step_mode()
	return phase in [Phase.INSTANTIATED, Phase.INITIALIZATION] and v.is_settable_before_init()


func _get_typed(vrs: PackedInt64Array, type: int) -> Array:
	var out := []
	last_status = Fmi3.Status.OK
	for vr in vrs:
		var v := model_description.get_variable_by_vr(vr)
		if v == null or v.type != type:
			last_status = Fmi3.Status.ERROR
			out.append(Fmi3.default_value(type))
		else:
			out.append(_values[vr])
	return out


func _set_typed(vrs: PackedInt64Array, values: Array, type: int) -> int:
	if vrs.size() != values.size():
		return Fmi3.Status.ERROR
	var status := Fmi3.Status.OK
	for i in vrs.size():
		var v := model_description.get_variable_by_vr(vrs[i])
		if v == null or v.type != type:
			status = Fmi3.Status.ERROR
			continue
		status = maxi(status, set_value_by_vr(vrs[i], values[i]))
	return status


func _illegal_call(fn: String) -> int:
	_log("%s not allowed in phase %s" % [fn, Phase.keys()[phase]])
	return Fmi3.Status.ERROR
