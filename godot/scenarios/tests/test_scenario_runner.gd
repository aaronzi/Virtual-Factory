extends GutTest
## ScenarioRunner against a master with the accumulator test FMU (enable input, rate tunable,
## limit fixed, value output).

const MD_PATH := "res://core/fmi/tests/fixtures/modelDescription.xml"
const AccumulatorFmu := preload("res://core/fmi/tests/accumulator_fmu.gd")
const H := 0.1

var master: CoSimMaster
var runner: ScenarioRunner
var acc: Fmi3CoSimulation
var fired: Array = []


func before_each() -> void:
	master = CoSimMaster.new()
	acc = AccumulatorFmu.new()
	acc.instantiate("ACC", Fmi3ModelDescription.load_file(MD_PATH))
	master.add_instance(acc)
	master.initialize()
	runner = ScenarioRunner.new(master)
	fired = []
	runner.step_changed.connect(func(i: int, _s: Dictionary) -> void: fired.append(i))


func _scenario(id: String, steps: Array) -> Dictionary:
	return {"id": id, "title_en": "T " + id, "title_de": "D " + id, "description_en": "desc",
		"description_de": "Beschreibung", "steps": steps}


func _run(seconds: float) -> void:
	for i in roundi(seconds / H):
		runner.before_step(H)
		master.step(H)


func test_timed_condition_and_relative_steps() -> void:
	assert_eq(runner.add(_scenario("s", [
		{"at": 1.0, "set": {"ACC.enable": true, "ACC.rate": 10.0}},
		{"when": {"var": "ACC.value", "op": ">=", "value": 5.0}, "set": {"ACC.rate": 1.0}},
		{"after": 2.0, "reset": "all"},
	])), OK)
	assert_eq(runner.start("s"), OK)
	_run(0.95)
	assert_false(acc.get_value("enable"), "not before t = 1 s")
	_run(0.1)
	assert_true(acc.get_value("enable"))
	assert_almost_eq(runner.progress, 1.0 / 3.0, 1e-6)
	_run(0.6)  # 10/s: value reaches 5 after 0.5 s, condition seen one step later
	assert_eq(acc.get_value("rate"), 1.0)
	assert_eq(fired, [0, 1])
	_run(2.1)
	assert_eq(fired, [0, 1, 2])
	assert_false(acc.get_value("enable"), "reset restores the value before the scenario")
	assert_eq(acc.get_value("rate"), 2.0)
	assert_false(runner.active, "finished after the last step")
	assert_almost_eq(runner.progress, 1.0, 1e-6)


func test_stop_restores_changed_variables() -> void:
	runner.add(_scenario("s", [{"at": 0.0, "set": {"ACC.rate": 7.0}}, {"at": 100.0, "reset": "all"}]))
	var results: Array = []
	runner.finished.connect(func(id: String, completed: bool) -> void: results.append([id, completed]))
	runner.start("s")
	_run(0.2)
	assert_eq(acc.get_value("rate"), 7.0)
	assert_true(runner.active)
	runner.stop()
	assert_eq(acc.get_value("rate"), 2.0)
	assert_false(runner.active)
	assert_eq(results, [["s", false]])


func test_pulse_holds_for_one_step() -> void:
	runner.add(_scenario("p", [{"at": 0.0, "pulse": {"ACC.enable": true}}]))
	runner.start("p")
	runner.before_step(H)
	master.step(H)
	assert_true(acc.get_value("enable"))
	assert_true(acc.get_value("enabled_out"), "the FMU saw the pulse")
	runner.before_step(H)
	assert_false(acc.get_value("enable"), "released before the next step")


func test_list_is_localized() -> void:
	runner.add(_scenario("a", [{"at": 0.0, "set": {"ACC.rate": 1.0}}]))
	runner.add(_scenario("b", [{"at": 0.0, "message_en": "look", "message_de": "schau"}]))
	var de := runner.list("de")
	assert_eq(de.size(), 2)
	assert_eq(de[0], {"id": "a", "title": "D a", "description": "Beschreibung", "steps": 1})
	assert_eq(runner.list("fr")[1].title, "T b", "fallback to English")


func test_invalid_scenarios_are_rejected() -> void:
	assert_eq(runner.add({"id": "x"}), ERR_INVALID_DATA, "texts missing")
	assert_eq(runner.add(_scenario("two", [{"at": 1.0, "after": 2.0, "set": {}}])), ERR_INVALID_DATA)
	assert_eq(runner.add(_scenario("noact", [{"at": 1.0}])), ERR_INVALID_DATA)
	assert_eq(runner.add(_scenario("op", [{"when": {"var": "ACC.value", "op": "~", "value": 1}}])),
		ERR_INVALID_DATA)
	runner.add(_scenario("out", [{"at": 0.0, "set": {"ACC.value": 1.0}}]))
	assert_eq(runner.start("out"), ERR_INVALID_DATA, "outputs are not writable")
	runner.add(_scenario("fixed", [{"at": 0.0, "set": {"ACC.limit": 1}}]))
	assert_eq(runner.start("fixed"), ERR_INVALID_DATA, "fixed parameters are not writable")
	runner.add(_scenario("unk", [{"when": {"var": "NOPE.x", "value": 1}, "set": {"ACC.rate": 1.0}}]))
	assert_eq(runner.start("unk"), ERR_INVALID_DATA)
	assert_eq(runner.start("missing"), ERR_DOES_NOT_EXIST)
	assert_false(runner.active)
	for expected in ["missing title_en", "exactly one trigger", "needs an action", "'when' needs",
			"ACC.value is not a writable", "ACC.limit is not a writable", "unknown variable NOPE.x",
			"unknown scenario"]:
		assert_push_error(expected)


func test_shipped_scenarios_are_valid() -> void:
	var loaded := runner.load_directory("res://config/scenarios")
	assert_eq(loaded, 5, "five training scenarios")
	for s in runner.list("de"):
		assert_ne(s.title, "", "German title for %s" % s.id)
