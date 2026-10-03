extends SceneTree
## Headless integration run of the complete line. Run with fixed FPS so it is faster than real time:
##   godot --headless --fixed-fps 60 -s res://tests/integration/line_run.gd -- --vf-sim-seconds=600
## Exits with code 1 if any production invariant is violated.

const MAIN := "res://factory/main.tscn"


func _initialize() -> void:
	var seconds := 600.0
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--vf-sim-seconds="):
			seconds = arg.get_slice("=", 1).to_float()
	var main: Node = load(MAIN).instantiate()
	root.add_child(main)
	var factory: Node = main.get_node("Factory")
	var frames := roundi(seconds * 60.0)
	for i in frames:
		await physics_frame
	quit(_check(factory, seconds))


func _check(f: Node, seconds: float) -> int:
	var total: int = f.read("PLC01.parts_total")
	var ok: int = f.read("PLC01.parts_ok")
	var nok: int = f.read("PLC01.parts_nok")
	var takt: float = f.read("AC01.takt_time")
	var report := {
		"sim_seconds": seconds, "released": f.read("AC01.release_count"), "inspected": total, "ok": ok,
		"nok": nok, "klt_a": f.read("KLTA01.fill_count"), "klt_b": f.read("KLTB01.fill_count"),
		"klt_a_exchanges": f.read("KLTA01.exchange_count"), "klt_b_exchanges": f.read("KLTB01.exchange_count"),
		"robot_cycles": f.read("RB01.cycle_count"), "robot_fault": f.read("RB01.fault"),
		"infeed_faults": f.read("PLC01.infeed_faults"), "line_energy_kwh": _energy(f),
	}
	print("LINE RUN REPORT ", JSON.stringify(report))
	var problems: Array[String] = []
	if total < floori(seconds / takt) - 3:
		problems.append("throughput too low: %d inspected" % total)
	if ok + nok != total:
		problems.append("OK + NOK != total")
	if report.robot_fault:
		problems.append("robot fault")
	if report.infeed_faults > 0:
		problems.append("infeed tracking faults")
	var placed: int = report.klt_a + report.klt_b + 12 * (report.klt_a_exchanges + report.klt_b_exchanges)
	if absi(placed - report.robot_cycles) > 1:
		problems.append("placed parts (%d) != robot cycles (%d)" % [placed, report.robot_cycles])
	if absi(report.klt_a + 12 * report.klt_a_exchanges - ok) > 1:
		problems.append("KLT A content does not match OK count")
	for p in problems:
		printerr("LINE RUN FAILED: ", p)
	return 1 if problems.size() > 0 else 0


func _energy(f: Node) -> float:
	var e := 0.0
	for id in ["AC01", "CV01", "LB01", "LB02", "QS01", "RB01"]:
		e += f.read(id + ".energy")
	return e
