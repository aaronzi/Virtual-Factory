extends GutTest


func test_ton() -> void:
	var t := IecTon.new(0.5)
	assert_false(t.update(true, 0.3))
	assert_true(t.update(true, 0.3))
	assert_false(t.update(false, 0.01))


func test_tof_and_tp() -> void:
	var tof := IecTof.new(0.2)
	assert_true(tof.update(true, 0.01))
	assert_true(tof.update(false, 0.1))
	assert_false(tof.update(false, 0.15))
	var tp := IecTp.new(0.2)
	assert_true(tp.update(true, 0.1))
	assert_true(tp.update(true, 0.05))
	assert_false(tp.update(true, 0.1), "pulse ends even if IN stays true")
	assert_false(tp.update(true, 0.1), "no retrigger without a new rising edge")


func test_edges_and_counter() -> void:
	var r := IecRTrig.new()
	var f := IecFTrig.new()
	assert_eq([r.update(true), r.update(true), f.update(true), f.update(false)], [true, false, false, true])
	var c := IecCtu.new(2)
	c.update(true)
	c.update(false)
	assert_true(c.update(true))
	c.update(true, true)
	assert_eq(c.cv, 0)
	assert_false(c.update(true), "held CU after reset is not a new edge")


func test_packml_happy_path_and_hold() -> void:
	var sm := PackMLStateMachine.new()
	assert_eq(sm.state, PackMLStateMachine.State.STOPPED)
	assert_false(sm.command(PackMLStateMachine.Command.START), "cannot start from STOPPED")
	sm.command(PackMLStateMachine.Command.RESET)
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.IDLE)
	sm.command(PackMLStateMachine.Command.START)
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.EXECUTE)
	sm.command(PackMLStateMachine.Command.HOLD)
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.HELD)
	sm.command(PackMLStateMachine.Command.UNHOLD)
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.EXECUTE)


func test_packml_abort_clear_and_manual_completion() -> void:
	var sm := PackMLStateMachine.new()
	sm.auto_complete = false
	sm.command(PackMLStateMachine.Command.ABORT)
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.ABORTING, "waits for state_complete")
	sm.state_complete()
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.ABORTED)
	assert_false(sm.command(PackMLStateMachine.Command.RESET))
	sm.command(PackMLStateMachine.Command.CLEAR)
	sm.state_complete()
	sm.update(0.01)
	assert_eq(sm.state, PackMLStateMachine.State.STOPPED)
