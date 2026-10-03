class_name ScenarioValidator
extends RefCounted
## Checks training scenario definitions (structure on load, FMI variables against a master on start).
## Returns "" when valid, otherwise a description of the first problem.

const TRIGGERS := ["at", "after", "when"]
const ACTIONS := ["set", "pulse", "reset"]
const TEXTS := ["title_en", "title_de", "description_en", "description_de"]
const OPS := [">=", ">", "<=", "<", "==", "!="]


static func check_structure(s: Dictionary) -> String:
	if String(s.get("id", "")) == "":
		return "scenario without id"
	for key in TEXTS:
		if not s.get(key) is String:
			return "%s: missing %s" % [s.id, key]
	var steps: Variant = s.get("steps")
	if not steps is Array or steps.is_empty():
		return "%s: steps must be a non-empty array" % s.id
	for i in steps.size():
		var problem := _check_step(steps[i])
		if problem != "":
			return "%s step %d: %s" % [s.id, i, problem]
	return ""


static func _check_step(step: Variant) -> String:
	if not step is Dictionary:
		return "not an object"
	var triggers := TRIGGERS.filter(func(t: String) -> bool: return step.has(t))
	if triggers.size() != 1:
		return "needs exactly one trigger of %s" % [TRIGGERS]
	if step.has("when"):
		var cond: Variant = step.when
		if not cond is Dictionary or not cond.has("var") or not cond.has("value") \
				or String(cond.get("op", ">=")) not in OPS:
			return "'when' needs var, op (%s) and value" % [OPS]
	elif not (step[triggers[0]] is float or step[triggers[0]] is int):
		return "'%s' must be a number of seconds" % triggers[0]
	if not ACTIONS.any(func(a: String) -> bool: return step.has(a)) and not step.has("message_en"):
		return "needs an action (%s) or a message" % [ACTIONS]
	for a in ["set", "pulse"]:
		if step.has(a) and not step[a] is Dictionary:
			return "'%s' must map \"DEVICE.variable\" to a value" % a
	var reset: Variant = step.get("reset", [])
	if not (reset is Array or (reset is String and reset == "all")):
		return "'reset' must be a list of variables or \"all\""
	return ""


## All written variables must be inputs/tunable parameters, condition variables must exist.
static func check_variables(s: Dictionary, master: CoSimMaster) -> String:
	for step: Dictionary in s.steps:
		var written: Array = []
		for a in ["set", "pulse"]:
			written += (step.get(a, {}) as Dictionary).keys()
		var reset: Variant = step.get("reset", [])
		if reset is Array:
			written += reset
		for path: String in written:
			var v := _variable(master, path)
			if v == null or not v.is_settable_in_step_mode():
				return "%s is not a writable input/tunable parameter" % path
		if step.has("when") and _variable(master, step.when["var"]) == null:
			return "unknown variable %s" % step.when["var"]
	return ""


static func _variable(master: CoSimMaster, path: String) -> Fmi3Variable:
	var parts := path.split(".", true, 1)
	var fmu := master.get_instance(parts[0]) if parts.size() == 2 else null
	return fmu.model_description.get_variable(parts[1]) if fmu != null else null
