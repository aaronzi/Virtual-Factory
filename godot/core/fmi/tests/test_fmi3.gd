extends GutTest

const MD_PATH := "res://core/fmi/tests/fixtures/modelDescription.xml"
const AccumulatorFmu := preload("res://core/fmi/tests/accumulator_fmu.gd")


func _make(instance_name := "ACC") -> Fmi3CoSimulation:
	var fmu: Fmi3CoSimulation = AccumulatorFmu.new()
	assert_eq(fmu.instantiate(instance_name, Fmi3ModelDescription.load_file(MD_PATH)), Fmi3.Status.OK)
	return fmu


func test_parses_model_description() -> void:
	var md := Fmi3ModelDescription.load_file(MD_PATH)
	assert_eq(md.model_name, "Accumulator")
	assert_eq(md.model_identifier, "accumulator")
	assert_eq(md.instantiation_token, "{vf-test-accumulator-1}")
	assert_almost_eq(md.default_step_size, 0.01, 1e-9)
	assert_eq(md.variables.size(), 7)
	var rate := md.get_variable("rate")
	assert_eq(rate.value_reference, 10)
	assert_eq(rate.causality, Fmi3.Causality.PARAMETER)
	assert_eq(rate.variability, Fmi3.Variability.TUNABLE)
	assert_eq(rate.unit, "1/s")
	assert_eq(md.get_variable("label").start, "acc")
	assert_eq(md.get_variable("limit").start, 100)


func test_life_cycle_and_step() -> void:
	var fmu := _make()
	fmu.enter_initialization_mode(0.0)
	fmu.exit_initialization_mode()
	assert_eq(fmu.set_boolean(PackedInt64Array([1]), [true]), Fmi3.Status.OK)
	for i in 10:
		assert_eq(fmu.do_step(i * 0.1, 0.1).status, Fmi3.Status.OK)
	assert_almost_eq(fmu.get_float64(PackedInt64Array([20]))[0], 2.0, 1e-9)
	assert_almost_eq(fmu.current_time, 1.0, 1e-9)


func test_causality_rules() -> void:
	var fmu := _make()
	assert_eq(fmu.set_value("limit", 5), Fmi3.Status.OK, "fixed parameter settable before init")
	fmu.enter_initialization_mode()
	fmu.exit_initialization_mode()
	assert_eq(fmu.set_value("limit", 7), Fmi3.Status.ERROR, "fixed parameter not settable in step mode")
	assert_eq(fmu.set_value("rate", 3.0), Fmi3.Status.OK, "tunable parameter settable in step mode")
	assert_eq(fmu.set_value("value", 1.0), Fmi3.Status.ERROR, "outputs are never settable")
	assert_eq(fmu.set_float64(PackedInt64Array([1]), PackedFloat64Array([1.0])), Fmi3.Status.ERROR,
		"type mismatch")
	assert_eq(fmu.do_step(0.0, 0.0).status, Fmi3.Status.ERROR, "step size must be positive")


func test_fmu_state_roundtrip() -> void:
	var fmu := _make()
	fmu.enter_initialization_mode()
	fmu.exit_initialization_mode()
	fmu.set_value("enable", true)
	fmu.do_step(0.0, 1.0)
	var snapshot := fmu.get_fmu_state()
	fmu.do_step(1.0, 1.0)
	assert_almost_eq(fmu.get_value("value"), 4.0, 1e-9)
	fmu.set_fmu_state(snapshot)
	assert_almost_eq(fmu.get_value("value"), 2.0, 1e-9)
	assert_almost_eq(fmu.current_time, 1.0, 1e-9)


func test_master_connects_and_steps() -> void:
	var a := _make("A")
	var b := _make("B")
	var master := CoSimMaster.new()
	master.add_instance(a)
	master.add_instance(b)
	assert_eq(master.connect_variables("A.enabled_out", "B.enable"), OK)
	assert_ne(master.connect_variables("A.value", "B.enable"), OK, "type mismatch rejected")
	assert_ne(master.connect_variables("A.enable", "B.enable"), OK, "source must be an output")
	assert_push_error("type mismatch")
	assert_push_error("must be an output")
	master.initialize()
	a.set_value("enable", true)
	master.step(0.5)  # A steps first -> enabled_out true -> B sees it in the same step (Gauss-Seidel)
	master.step(0.5)
	assert_almost_eq(master.read("A.value"), 2.0, 1e-9)
	assert_almost_eq(master.read("B.value"), 2.0, 1e-9, "Gauss-Seidel: B sees A's output in the same step")
	assert_almost_eq(master.time, 1.0, 1e-9)
