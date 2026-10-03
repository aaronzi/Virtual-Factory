extends GutTest
## Safety circuit: fence door and E-stop both stop the robot; the E-stop also aborts the line (alarm 100).

const Program := preload("res://control/sorting_line/sorting_line_program.gd")
const Robot := preload("res://devices/ur5e/model/ur5e_model.gd")

var master: CoSimMaster
var commands: LocalCommands
var safety: SafetyCircuit


func before_each() -> void:
	master = CoSimMaster.new()
	var plc: Fmi3CoSimulation = Program.new()
	plc.instantiate("PLC01", Fmi3ModelDescription.load_file("res://control/sorting_line/modelDescription.xml"))
	master.add_instance(plc)
	var robot: Fmi3CoSimulation = Robot.new()
	robot.instantiate("RB01", Fmi3ModelDescription.load_file("res://devices/ur5e/model/modelDescription.xml"))
	master.add_instance(robot)
	master.initialize()
	commands = LocalCommands.new(master)
	safety = SafetyCircuit.new()
	safety.setup(master, commands)
	add_child_autofree(safety)


func _robot_stopped() -> bool:
	commands.apply()
	safety._physics_process(0.0)
	return bool(master.read(SafetyCircuit.ROBOT_STOP))


func test_door_follows_an_external_write() -> void:
	commands.write(SafetyCircuit.ROBOT_STOP, true)
	assert_true(_robot_stopped())
	assert_true(safety.is_door_open())


func test_door_stops_the_robot() -> void:
	safety.toggle_door()
	assert_true(_robot_stopped())
	assert_false(master.read(SafetyCircuit.PLC_ESTOP))
	safety.toggle_door()
	assert_false(_robot_stopped())


func test_estop_keeps_the_robot_stopped_when_the_door_closes() -> void:
	safety.toggle_door()
	safety.toggle_estop()
	assert_true(_robot_stopped())
	assert_true(master.read(SafetyCircuit.PLC_ESTOP))
	safety.toggle_door()
	assert_false(safety.is_door_open())
	assert_true(_robot_stopped(), "E-stop still latched")
	safety.toggle_estop()
	assert_false(_robot_stopped())
	assert_false(master.read(SafetyCircuit.PLC_ESTOP))


func test_nothing_releases_the_robot_while_the_estop_is_latched() -> void:
	safety.toggle_estop()
	assert_true(_robot_stopped())
	commands.write(SafetyCircuit.ROBOT_STOP, false)  # e.g. a scenario reset or an MQTT command
	commands.apply()
	safety._physics_process(0.0)
	assert_true(_robot_stopped())
