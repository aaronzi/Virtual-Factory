extends PlcProgram
## PLC program of LINE01 (inspection & sorting). Sequence per part:
##   WAIT_PART (belt runs) -LB02↑-> POSITIONING (stop delay) -> SETTLING -> INSPECTING (trigger QA)
##   -> WAIT_ROBOT (free robot, target KLT not full) -> PICKING (until part clear) -> WAIT_PART
## When the robot reports a job done, sorted_serial/target/slot and sorted_count are set in the same scan.
## KLT exchange: automatic after exchange_delay (auto_exchange) or manual via klt_exchange_command.
## Alarms (LineAlarms): drive fault -> ABORT, protective stop / stuck light barrier -> HOLD until gone,
## robot fault -> HOLD, infeed tracking timeout -> warning; reported as alarm_code/alarm_text.

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
var _alarms := LineAlarms.new()
var _lb01_stuck: StuckSignal
var _lb02_stuck: StuckSignal
var _result_ok := false
var _last_klt_command := 0


func _on_initialize() -> void:
	_tracker = PartTracker.new(_get_var("infeed_timeout"))
	_lb01_stuck = StuckSignal.new(_get_var("sensor_blocked_timeout"))
	_lb02_stuck = StuckSignal.new(_get_var("sensor_blocked_timeout"))
	if _get_var("auto_start"):
		packml.command(C.RESET)


func _scan(dt: float) -> void:
	if _get_var("auto_start") and packml.state == S.IDLE:
		packml.command(C.START)
	var executing := packml.state == S.EXECUTE
	_tracker.update(_get_var("ac_release_count"), _get_var("ac_last_serial"), _get_var("lb01_signal"), dt,
		_get_var("cv_run"))
	if _robot.update(_get_var("rb_job_done")):
		_report_sorted()
	_handle_klt_exchange_command()
	# the sequence runs in every state so work in progress (measurement, robot job handshake) completes
	# while held/aborted; belt, cell and new robot jobs need EXECUTE (`executing`)
	_run_sequence(dt, _lb02_rise.update(_get_var("lb02_signal")), executing)
	_update_klts(dt)
	_update_alarms(dt)
	_write_outputs(executing)


## Alarm conditions; the belt command of the previous scan defines when the barriers must be free.
func _update_alarms(dt: float) -> void:
	var belt_on: bool = _get_var("cv_run")
	_alarms.update({
		100: _get_var("estop"),
		101: _get_var("cv_fault"),
		202: _get_var("rb_fault"),
		201: _get_var("rb_protective_stop"),
		302: _lb02_stuck.update(_get_var("lb02_signal"), belt_on and _seq == Seq.WAIT_PART, dt),
		301: _lb01_stuck.update(_get_var("lb01_signal"), belt_on, dt),
		401: _tracker.timeout_alarm,
	}, packml)


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
	# no new job while an exchange is pending: the part would land in the replacement KLT
	var available := not full and not klt.exchange_request
	if executing and available and _robot.is_idle() \
			and _robot.request(target, klt.next_slot, _get_var("serial_at_qs")):
		klt.place()
		_seq = Seq.PICKING


func _report_sorted() -> void:
	_set_var("sorted_serial", _robot.serial)
	_set_var("sorted_target", _robot.target)
	_set_var("sorted_slot", _robot.slot)
	_set_var("sorted_count", _get_var("sorted_count") + 1)


## klt_exchange_command (1 = KLT A, 2 = KLT B) is edge-triggered like packml_command.
func _handle_klt_exchange_command() -> void:
	var cmd: int = _get_var("klt_exchange_command")
	if cmd != _last_klt_command and _klt.has(cmd):
		_klt[cmd].request_exchange()
	_last_klt_command = cmd


func _update_klts(dt: float) -> void:
	var capacity: int = _get_var("klt_capacity")
	var auto: bool = _get_var("auto_exchange")
	var delay: float = _get_var("exchange_delay")
	var counts := {1: _get_var("klt_a_count"), 2: _get_var("klt_b_count")}
	for target: int in _klt:
		var placing := _robot.job_start() and _robot.target == target
		_klt[target].update(capacity, counts[target], auto, delay, dt, placing)


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
	var stops := _alarms.stops_line()
	_set_var("alarm_code", _alarms.code)
	_set_var("alarm_text", _alarms.text)
	_set_var("alarm_count", _alarms.count)
	_set_var("horn", stops)
	_set_var("light_green", executing)
	_set_var("light_amber", packml.state in [S.SUSPENDED, S.HELD, S.IDLE] or packml.is_acting()
		or (_alarms.code != 0 and not stops))
	_set_var("light_red", packml.state in [S.STOPPED, S.ABORTED] or stops)
