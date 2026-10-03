extends GutTest
## UnsGateway with a test FMU (Accumulator) and the in-memory MQTT loopback transport.

const Accumulator := preload("res://core/fmi/tests/accumulator_fmu.gd")
const P := preload("res://connectivity/mqtt/mqtt_packet.gd")
const MD := "res://core/fmi/tests/fixtures/modelDescription.xml"
const H := 0.01
const START_UNIX := 1790000000.0  # 2026-09-21T14:13:20Z

var master: CoSimMaster
var acc: Fmi3CoSimulation
var client: MqttClient
var transport: MqttTransport
var gateway: UnsGateway


func _registry(pulse: Array) -> Dictionary:
	return {
		"topic_root": "t/line",
		"payload": {"value_key": "v", "timestamp_key": "ts"},
		"session": {"topic": "{root}/session", "status_topic": "{root}/status", "retain": true, "qos": 1},
		"telemetry": {"topic": "{root}/{device}/{variable}", "retain": true, "qos": 0, "min_interval_s": 0.1},
		"events": {"topic": "{root}/{device}/event/{event}", "retain": false, "qos": 1, "definitions": [
			{"device": "ACC1", "event": "enabled", "trigger": "ACC1.enabled_out", "when": true,
				"fields": {"value": "ACC1.value", "rate": "ACC1.rate"}},
		]},
		"commands": {"topic": "{root}/{device}/cmd/{variable}", "ack_topic": "{root}/{device}/cmd-resp/{variable}",
			"qos": 1, "writable": {"ACC1": ["enable", "rate"]}, "pulse": pulse},
	}


func _setup(pulse := []) -> void:
	master = CoSimMaster.new()
	acc = Accumulator.new()
	acc.instantiate("ACC1", Fmi3ModelDescription.load_file(MD))
	master.add_instance(acc)
	master.initialize()
	client = MqttClient.new()
	transport = MqttTransport.new()
	gateway = UnsGateway.new(master, client, _registry(pulse), "test.layout.json", START_UNIX)
	gateway.start("ws://unused")
	client.connect_to_broker("ws://unused", transport)
	client.poll()
	client.poll()
	transport.inject(P.connack_packet(0))


## One physics tick as driven by the factory runtime.
func _tick(n := 1) -> void:
	for i in n:
		gateway.before_step()
		master.step(H)
		gateway.after_step()


## Decoded PUBLISH packets sent since the last call: [{topic, json, qos, retain}].
func _published() -> Array:
	var out := []
	for bytes in transport.sent:
		var p := P.decode(bytes)
		if p.type == P.Type.PUBLISH:
			out.append({"topic": p.topic, "json": JSON.parse_string(p.payload.get_string_from_utf8()),
				"qos": p.qos, "retain": p.retain})
	transport.sent.clear()
	return out


func _on(messages: Array, topic: String) -> Array:
	return messages.filter(func(m: Dictionary) -> bool: return m.topic == topic)


func _command(variable: String, payload: String) -> void:
	transport.inject(P.publish_packet("t/line/acc1/cmd/" + variable, payload.to_utf8_buffer(), 1, false, 3))


func test_birth_status_and_full_state_on_connect() -> void:
	_setup()
	assert_eq(transport.sent[0][9] & 0x2C, 0x2C, "will: flag, QoS 1, retain")
	_tick()
	var msgs := _published()
	var birth: Array = _on(msgs, "t/line/session")
	assert_eq(birth.size(), 1)
	assert_eq([birth[0].qos, birth[0].retain], [1, true])
	assert_eq(birth[0].json.id, gateway.session_id)
	assert_true(gateway.session_id.begins_with("S-20260921T141320Z-"), gateway.session_id)
	assert_eq(birth[0].json.devices, ["ACC1"])
	assert_eq(birth[0].json.layout, "test.layout.json")
	assert_eq(birth[0].json.started, "2026-09-21T14:13:20.000Z")
	assert_eq(_on(msgs, "t/line/status")[0].json.v, "online")
	var value: Array = _on(msgs, "t/line/acc1/value")
	assert_eq(value.size(), 1, "full state once")
	assert_eq([value[0].retain, value[0].qos], [true, 0])
	assert_eq(value[0].json.ts, "2026-09-21T14:13:20.010Z", "session start + simulation time")
	assert_eq(_on(msgs, "t/line/acc1/enabled_out").size(), 1)
	assert_eq(_on(msgs, "t/line/acc1/rate").size(), 0, "parameters are not telemetry")


func test_telemetry_on_change_with_throttled_continuous_values() -> void:
	_setup()
	_tick()
	_published()
	_tick(5)
	assert_eq(_published().size(), 0, "nothing changed")
	acc.set_value("enable", true)
	_tick(30)
	var msgs := _published()
	assert_eq(_on(msgs, "t/line/acc1/enabled_out").size(), 1, "discrete: immediately, once")
	var values: Array = _on(msgs, "t/line/acc1/value")
	assert_between(values.size(), 3, 4, "continuous: at most every 0.1 s")
	assert_almost_eq(float(values[-1].json.v), 0.5, 1e-6, "latest value at t = 0.31 s")


func test_event_fields_are_snapshots_of_the_trigger_tick() -> void:
	_setup()
	_tick(3)
	assert_eq(_on(_published(), "t/line/acc1/event/enabled").size(), 0, "no event at initialization")
	acc.set_value("enable", true)
	_tick()
	var events: Array = _on(_published(), "t/line/acc1/event/enabled")
	assert_eq(events.size(), 1)
	var e: Dictionary = events[0].json
	assert_eq([e.event, e.device, e.session, e.seq], ["enabled", "ACC1", gateway.session_id, 1.0])
	assert_almost_eq(float(e.value), 0.02, 1e-9)
	assert_eq([events[0].qos, events[0].retain], [1, false])
	acc.set_value("enable", false)
	_tick(2)
	assert_eq(_on(_published(), "t/line/acc1/event/enabled").size(), 0, "'when' filters false")
	acc.set_value("enable", true)
	_tick()
	assert_eq(_on(_published(), "t/line/acc1/event/enabled")[0].json.seq, 2.0)


func test_commands_are_validated_applied_and_acknowledged() -> void:
	_setup()
	_tick()
	_published()
	_command("rate", '{"v": 5, "corr": "c1", "source": "test"}')
	_command("rate", '{"v": "fast", "corr": "c2"}')
	transport.inject(P.publish_packet("t/line/acc1/cmd/limit", '{"v": 1}'.to_utf8_buffer(), 1, false, 4))
	_tick()
	assert_eq(acc.get_value("rate"), 5.0)
	var acks: Array = _on(_published(), "t/line/acc1/cmd-resp/rate")
	assert_eq(acks.size(), 2)
	var by_corr := {}
	for a in acks:
		by_corr[a.json.corr] = a.json
	assert_eq([by_corr.c1.accepted, by_corr.c1.v, by_corr.c1.reason], [true, 5.0, ""])
	assert_eq([by_corr.c2.accepted, by_corr.c2.v], [false, null])
	assert_true(by_corr.c1.has("ts"))


func test_pulse_command_holds_for_exactly_one_step() -> void:
	_setup(["ACC1.enable"])
	_tick()
	for corr in ["p1", "p2"]:
		_command("enable", '{"v": true, "corr": "%s"}' % corr)
	_tick()
	assert_almost_eq(acc.get_value("value"), 0.02, 1e-9, "integrated for one step")
	_tick()
	assert_false(acc.get_value("enable"), "reset to 0 before the next step")
	assert_almost_eq(acc.get_value("value"), 0.02, 1e-9, "reset step")
	_tick(2)
	assert_almost_eq(acc.get_value("value"), 0.04, 1e-9, "second pulse after one step at 0")
	var acks: Array = _on(_published(), "t/line/acc1/cmd-resp/enable")
	assert_eq(acks.map(func(a: Dictionary) -> String: return a.json.corr), ["p1", "p2"])


func test_type_conversion() -> void:
	assert_eq(UnsCommands.convert_value(Fmi3.VarType.INT32, 4.0), ["", 4])
	assert_ne(UnsCommands.convert_value(Fmi3.VarType.INT32, 4.5)[0], "")
	assert_ne(UnsCommands.convert_value(Fmi3.VarType.INT32, 3e9)[0], "")
	assert_eq(UnsCommands.convert_value(Fmi3.VarType.BOOLEAN, 1.0), ["", true])
	assert_ne(UnsCommands.convert_value(Fmi3.VarType.BOOLEAN, "yes")[0], "")
	assert_eq(UnsCommands.convert_value(Fmi3.VarType.FLOAT64, 2), ["", 2.0])
	assert_eq(UnsCommands.convert_value(Fmi3.VarType.STRING, "S1"), ["", "S1"])
