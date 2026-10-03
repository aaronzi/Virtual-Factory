extends PlcProgram
## PLC program of LINE01 (inspection & sorting). Sequence per part:
##   WAIT_PART (belt runs) -LB02↑-> POSITIONING (stop delay) -> SETTLING -> INSPECTING (trigger QA)
##   -> WAIT_ROBOT (free robot, target KLT not full) -> PICKING (until part clear) -> WAIT_PART

enum Seq { WAIT_PART, POSITIONING, SETTLING, INSPECTING, WAIT_ROBOT, PICKING }
const S := PackMLStateMachine.State
const C := PackMLStateMachine.Command

var _seq := Seq.WAIT_PART
var _tracker: PartTracker
var _robot := RobotJobHandshake.new()
var _klt := {1: KltSlotManager.new(), 2: KltSlotManager.new()}
var _lb02_rise := IecRTrig.new()
var _stop_delay := IecTon.new()
var _settle := IecTon.new()
var _result_ok := false


func _on_initialize() -> void:
	_tracker = PartTracker.new(_get_var("infeed_timeout"))
	if _get_var("auto_start"):
		packml.command(C.RESET)


func _scan(dt: float) -> void:
	if _get_var("auto_start") and packml.state == S.IDLE:
		packml.command(C.START)
	var executing := packml.state == S.EXECUTE
	_tracker.update(_get_var("ac_release_count"), _get_var("ac_last_serial"), _get_var("lb01_signal"), dt)
	_robot.update(_get_var("rb_job_done"))
	var lb02_rising := _lb02_rise.update(_get_var("lb02_signal"))
	if executing or packml.state in [S.SUSPENDED, S.HELD]:
		_run_sequence(dt, lb02_rising, executing)
	_update_klts(dt)
	_write_outputs(executing)


func _run_sequence(dt: float, lb02_rising: bool, executing: bool) -> void:
	match _seq:
		Seq.WAIT_PART:
			if lb02_rising:
				_seq = Seq.POSITIONING
		Seq.POSITIONING:
			_stop_delay.pt = _get_var("lb02_stop_delay")
			if _stop_delay.update(true, dt):
				_stop_delay.update(false, dt)
				_seq = Seq.SETTLING
		Seq.SETTLING:
			_settle.pt = _get_var("settle_time")
			if _settle.update(true, dt):
				_settle.update(false, dt)
				_seq = Seq.INSPECTING
		Seq.INSPECTING:
			if _get_var("qs_result_valid"):
				_latch_result()
				_seq = Seq.WAIT_ROBOT
		Seq.WAIT_ROBOT:
			_request_pick(executing)
		Seq.PICKING:
			if _get_var("rb_part_clear"):
				_seq = Seq.WAIT_PART


func _latch_result() -> void:
	_result_ok = _get_var("qs_result_ok")
	_set_var("serial_at_qs", _tracker.pop_at_station())
	_set_var("last_result", 1 if _result_ok else 2)
	_set_var("parts_total", _get_var("parts_total") + 1)
	var counter := "parts_ok" if _result_ok else "parts_nok"
	_set_var(counter, _get_var(counter) + 1)


func _request_pick(executing: bool) -> void:
	var target := 1 if _result_ok else 2
	var klt: KltSlotManager = _klt[target]
	var full := klt.is_full(_get_var("klt_capacity"))
	if full and packml.state == S.EXECUTE:
		packml.command(C.SUSPEND)
	elif not full and packml.state == S.SUSPENDED:
		packml.command(C.UNSUSPEND)
	if executing and not full and _robot.is_idle() and _robot.request(target, klt.next_slot):
		klt.place()
		_seq = Seq.PICKING


func _update_klts(dt: float) -> void:
	var capacity: int = _get_var("klt_capacity")
	_klt[1].update(capacity, _get_var("klt_a_count"), _get_var("auto_exchange"), _get_var("exchange_delay"), dt)
	_klt[2].update(capacity, _get_var("klt_b_count"), _get_var("auto_exchange"), _get_var("exchange_delay"), dt)


func _write_outputs(executing: bool) -> void:
	var belt_ok := executing and _seq in [Seq.WAIT_PART, Seq.POSITIONING]
	var parts_on_belt := _tracker.serials.size()
	_set_var("ac_enable", executing)
	_set_var("ac_infeed_free", not _tracker.infeed_occupied and parts_on_belt < _get_var("max_parts_on_belt"))
	_set_var("cv_run", belt_ok)
	_set_var("cv_speed_setpoint", _get_var("belt_speed"))
	_set_var("qs_trigger", _seq == Seq.INSPECTING)
	_set_var("rb_job_start", _robot.job_start())
	_set_var("rb_place_target", _robot.target)
	_set_var("rb_place_slot", _robot.slot)
	_set_var("klt_a_exchange", _klt[1].exchange_request)
	_set_var("klt_b_exchange", _klt[2].exchange_request)
	_set_var("sequence_step", _seq)
	_set_var("parts_on_belt", parts_on_belt)
	_set_var("infeed_faults", _tracker.infeed_faults)
	_set_var("light_green", executing)
	_set_var("light_amber", packml.state in [S.SUSPENDED, S.HELD, S.IDLE] or packml.is_acting())
	_set_var("light_red", packml.state in [S.STOPPED, S.ABORTED] or _get_var("rb_fault"))
