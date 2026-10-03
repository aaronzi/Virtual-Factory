class_name ScenarioRunner
extends RefCounted
## Runs data-driven training scenarios (fault injection) against the co-simulation. A scenario is a
## Dictionary (JSON, see docs/interfaces/scenarios.md) with id, title_en/de, description_en/de and
## sequential steps. A step fires when its trigger is met, then the next step is armed:
##   trigger: "at": s since start | "after": s since the previous step | "when": {"var", "op", "value"}
##   actions: "set": {"DEV.var": value}, "pulse": {"DEV.var": value} (one master step, then 0),
##            "reset": ["DEV.var", ...] or "all" (back to the value before the scenario changed it)
##   optional "message_en"/"message_de" for the trainer UI.
## Only FMI inputs and tunable parameters can be written (validated on start). stop() restores every
## changed variable; a scenario that runs to its end keeps its last values (scenarios end with a reset).
## Call before_step(h) from the physics loop before the master steps (after UNS commands).

signal started(scenario_id: String)
signal step_changed(index: int, step: Dictionary)
signal finished(scenario_id: String, completed: bool)

var active := false
var active_id := ""
var elapsed := 0.0  ## s since start of the active scenario
var step_index := -1  ## index of the last fired step (-1: none yet)
## Fraction of fired steps of the active (or last) scenario, 0..1.
var progress: float:
	get:
		var n := _steps().size()
		return 0.0 if n == 0 else float(step_index + 1) / n

var _master: CoSimMaster
var _scenarios := {}  # id -> Dictionary (insertion order = list order)
var _originals := {}  # "DEV.var" -> value before the scenario
var _pulses: Array[String] = []
var _last_fire_time := 0.0


func _init(master: CoSimMaster) -> void:
	_master = master


## Loads every *.json scenario of a directory (sorted by file name). Returns the number loaded.
func load_directory(dir_path: String) -> int:
	var count := 0
	var files := Array(DirAccess.get_files_at(dir_path))
	files.sort()
	for file: String in files:
		if not file.ends_with(".json"):
			continue
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir_path.path_join(file)))
		if data is Dictionary and add(data) == OK:
			count += 1
		else:
			push_error("ScenarioRunner: invalid scenario file %s" % file)
	return count


## Registers a scenario after a structural check (variables are resolved on start()).
func add(scenario: Dictionary) -> Error:
	var problem := ScenarioValidator.check_structure(scenario)
	if problem != "":
		push_error("ScenarioRunner: %s" % problem)
		return ERR_INVALID_DATA
	_scenarios[scenario.id] = scenario
	return OK


## Available scenarios as [{id, title, description, steps}] in the given language ("en", "de").
func list(lang := "en") -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for id: String in _scenarios:
		var s: Dictionary = _scenarios[id]
		out.append({"id": id, "title": localized(s, "title", lang),
			"description": localized(s, "description", lang), "steps": s.steps.size()})
	return out


func get_scenario(id: String) -> Dictionary:
	return _scenarios.get(id, {})


## Starts a scenario (stops a running one first). Returns ERR_DOES_NOT_EXIST or ERR_INVALID_DATA
## if the id is unknown or a variable is unknown / not writable in step mode.
func start(id: String) -> Error:
	if not _scenarios.has(id):
		push_error("ScenarioRunner: unknown scenario '%s'" % id)
		return ERR_DOES_NOT_EXIST
	var problem := ScenarioValidator.check_variables(_scenarios[id], _master)
	if problem != "":
		push_error("ScenarioRunner: %s: %s" % [id, problem])
		return ERR_INVALID_DATA
	stop()
	active_id = id
	active = true
	elapsed = 0.0
	step_index = -1
	_last_fire_time = 0.0
	_originals.clear()
	started.emit(id)
	return OK


## Aborts the active scenario and restores every variable it changed.
func stop() -> void:
	if not active:
		return
	_restore(_originals.keys())
	active = false
	finished.emit(active_id, false)


## Advances the scenario clock, fires due steps and releases pulses of the previous step.
func before_step(h: float) -> void:
	for path in _pulses:
		_write(path, 0, false)
	_pulses.clear()
	if not active:
		return
	elapsed += h
	var steps := _steps()
	while active and step_index + 1 < steps.size() and _is_due(steps[step_index + 1]):
		_fire(step_index + 1)
	if active and step_index + 1 >= steps.size():
		active = false
		finished.emit(active_id, true)


## Localized text of a scenario or step field (falls back to English).
static func localized(data: Dictionary, key: String, lang: String) -> String:
	return String(data.get("%s_%s" % [key, lang], data.get(key + "_en", "")))


func _steps() -> Array:
	return _scenarios.get(active_id, {}).get("steps", [])


func _is_due(step: Dictionary) -> bool:
	if step.has("at"):
		return elapsed >= float(step.at) - 1e-9
	if step.has("after"):
		return elapsed - _last_fire_time >= float(step.after) - 1e-9
	var cond: Dictionary = step.when
	return compare(_master.read(cond["var"]), String(cond.get("op", ">=")), cond.value)


func _fire(index: int) -> void:
	var step: Dictionary = _steps()[index]
	step_index = index
	_last_fire_time = elapsed
	var to_set: Dictionary = step.get("set", {})
	for path: String in to_set:
		_write(path, to_set[path])
	var pulses: Dictionary = step.get("pulse", {})
	for path: String in pulses:
		_write(path, pulses[path], false)
		_pulses.append(path)
	var reset: Variant = step.get("reset", [])
	_restore(_originals.keys() if reset is String and reset == "all" else Array(reset))
	step_changed.emit(index, step)


## Writes an FMI variable; `record` remembers the value before the first change for reset/stop.
func _write(path: String, value: Variant, record := true) -> void:
	if record and not _originals.has(path):
		_originals[path] = _master.read(path)
	var ep := path.split(".", true, 1)
	var fmu := _master.get_instance(ep[0])
	if fmu == null or fmu.set_value(ep[1], value) != Fmi3.Status.OK:
		push_warning("ScenarioRunner: cannot set %s" % path)


func _restore(paths: Array) -> void:
	for path: String in paths:
		if _originals.has(path):
			var value: Variant = _originals[path]
			_originals.erase(path)
			_write(path, value, false)


static func compare(a: Variant, op: String, b: Variant) -> bool:
	if a == null:
		return false
	match op:
		">=":
			return a >= b
		">":
			return a > b
		"<=":
			return a <= b
		"<":
			return a < b
		"!=":
			return a != b
	return a == b
