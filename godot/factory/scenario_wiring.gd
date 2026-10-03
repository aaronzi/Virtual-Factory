class_name ScenarioWiring
extends RefCounted
## Composition of the training scenarios: loads every scenario of res://config/scenarios into a
## ScenarioRunner for the factory's master, logs scenario progress and starts `--vf-scenario=<id>`.

const SCENARIO_DIR := "res://config/scenarios"


static func create(master: CoSimMaster) -> ScenarioRunner:
	var runner := ScenarioRunner.new(master)
	runner.load_directory(SCENARIO_DIR)
	runner.started.connect(func(id: String) -> void: print("[Scenario] started %s" % id))
	runner.step_changed.connect(func(i: int, step: Dictionary) -> void:
		print("[Scenario] t=%.1f s step %d: %s" % [
			master.time, i, ScenarioRunner.localized(step, "message", "en")]))
	runner.finished.connect(func(id: String, completed: bool) -> void:
		print("[Scenario] %s %s" % [id, "completed" if completed else "stopped"]))
	var id := DevTools.get_arg("vf-scenario")
	if id != "":
		runner.start(id)
	return runner
