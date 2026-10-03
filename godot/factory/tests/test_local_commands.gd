extends GutTest

const Program := preload("res://control/sorting_line/sorting_line_program.gd")
const MD := "res://control/sorting_line/modelDescription.xml"

var master: CoSimMaster
var plc: Fmi3CoSimulation


func before_each() -> void:
	master = CoSimMaster.new()
	plc = Program.new()
	plc.instantiate("PLC01", Fmi3ModelDescription.load_file(MD))
	master.add_instance(plc)
	master.initialize()


func test_pulse_is_held_one_step_and_repeats_with_a_zero_step() -> void:
	var cmds := LocalCommands.new(master)
	cmds.write("PLC01.packml_command", 4, true)
	cmds.write("PLC01.packml_command", 4, true)
	var seen: Array[int] = []
	for i in 4:
		cmds.apply()
		seen.append(plc.get_value("packml_command"))
	assert_eq(seen, [4, 0, 4, 0] as Array[int])


func test_plain_write_stays() -> void:
	var cmds := LocalCommands.new(master)
	cmds.write("PLC01.auto_exchange", false)
	cmds.apply()
	cmds.apply()
	assert_false(plc.get_value("auto_exchange"))


func test_packml_allowed_commands() -> void:
	var s := PackMLStateMachine.State
	var c := PackMLStateMachine.Command
	assert_true(c.HOLD in PackMLStateMachine.allowed_commands(s.EXECUTE))
	assert_false(c.START in PackMLStateMachine.allowed_commands(s.EXECUTE))
	assert_eq(PackMLStateMachine.allowed_commands(s.ABORTED), [c.CLEAR] as Array[int])
