extends GutTest
## PlcBackplane (CPU side of the OPC UA path, ADR-0024) and the UNS gateway split: a test FMU (Accumulator)
## on the OPC UA path, the in-memory loopback transport in place of TCP / MQTT.

const Accumulator := preload("res://core/fmi/tests/accumulator_fmu.gd")
const P := preload("res://connectivity/mqtt/mqtt_packet.gd")
const MD := "res://core/fmi/tests/fixtures/modelDescription.xml"
const H := 0.01
const START_UNIX := 1790000000.0  # 2026-09-21T14:13:20Z

var master: CoSimMaster
var acc: Fmi3CoSimulation
var config: UnsConfig
var transport: MqttTransport
var link: PlcBackplane


func _registry(opcua_enabled := true) -> Dictionary:
	return {
		"topic_root": "t/line",
		"payload": {"value_key": "v", "timestamp_key": "ts"},
		"telemetry": {"topic": "{root}/{device}/{variable}", "retain": true, "qos": 0},
		"events": {"topic": "{root}/{device}/event/{event}", "definitions": [
			{"device": "ACC1", "event": "enabled", "trigger": "ACC1.enabled_out", "when": true,
				"fields": {"value": "ACC1.value"}},
		]},
		"commands": {"topic": "{root}/{device}/cmd/{variable}", "ack_topic": "{root}/{device}/cmd-resp/{variable}",
			"writable": {"ACC1": ["enable", "rate"]}, "pulse": ["ACC1.enable"]},
		"opcua": {"enabled": opcua_enabled, "servers": {"ACC1": {"backplane": "tcp://unused:4841"}}},
	}


func before_each() -> void:
	master = CoSimMaster.new()
	acc = Accumulator.new()
	acc.instantiate("ACC1", Fmi3ModelDescription.load_file(MD))
	master.add_instance(acc)
	master.initialize()
	config = UnsConfig.new(_registry(), START_UNIX)
	transport = MqttTransport.new()
	link = PlcBackplane.new(master, config, "ACC1", "S-test")
	assert_eq(link.start("tcp://unused:4841", transport), OK)


## Connect, hello, welcome from the module: the link is up after two ticks.
func _link() -> void:
	_tick()
	transport.inject('{"type":"welcome","endpoint":"opc.tcp://test"}\n'.to_utf8_buffer())
	_tick()


func _tick(n := 1) -> void:
	for i in n:
		link.before_step()
		master.step(H)
		link.after_step()


## Messages sent to the communication module since the last call.
func _sent() -> Array:
	var out := []
	for bytes in transport.sent:
		for line in bytes.get_string_from_utf8().split("\n", false):
			out.append(JSON.parse_string(line))
	transport.sent.clear()
	return out


func _of(messages: Array, kind: String) -> Array:
	return messages.filter(func(m: Dictionary) -> bool: return m.type == kind)


func test_hello_then_full_image_after_welcome_then_changes_only() -> void:
	_tick()
	var msgs := _sent()
	assert_eq(msgs.size(), 1, "only hello until the module answers")
	assert_eq(msgs[0].type, "hello")
	assert_eq([msgs[0].device, msgs[0].session, msgs[0].protocol], ["ACC1", "S-test", 1.0])
	assert_false(link.is_linked())
	transport.inject('{"type":"welcome","endpoint":"opc.tcp://test"}\n'.to_utf8_buffer())
	_tick()
	assert_true(link.is_linked())
	var image: Dictionary = _of(_sent(), "image")[0]
	assert_eq(image.ts, "2026-09-21T14:13:20.020Z", "simulation time base")
	assert_eq(image["values"].keys().size(), 6, "inputs, parameters and outputs (not time)")
	assert_eq(image["values"].rate, 2.0)
	_tick(3)
	assert_eq(_of(_sent(), "image").size(), 0, "nothing changed")
	acc.set_value("rate", 4.0)
	_tick()
	assert_eq(_of(_sent(), "image")[0]["values"], {"rate": 4.0})


func test_events_carry_the_uns_payload() -> void:
	_link()
	_sent()
	acc.set_value("enable", true)
	_tick()
	var events := _of(_sent(), "event")
	assert_eq(events.size(), 1)
	var payload: Dictionary = events[0].payload
	assert_eq([payload.event, payload.device, payload.session, payload.seq], ["enabled", "ACC1", "S-test", 1.0])
	assert_almost_eq(float(payload.value), 0.02, 1e-9, "snapshot of the trigger tick")


func test_writes_are_applied_between_steps_and_answered() -> void:
	_link()
	_sent()
	transport.inject('{"type":"write","id":7,"variable":"rate","v":5}\n'.to_utf8_buffer())
	transport.inject('{"type":"write","id":8,"variable":"limit","v":1}\n{"type":"wri'.to_utf8_buffer())
	_tick()
	assert_eq(acc.get_value("rate"), 5.0)
	var results := _of(_sent(), "result")
	assert_eq(results.size(), 2)
	var by_id := {}
	for r in results:
		by_id[int(r.id)] = r
	assert_eq([by_id[7].accepted, by_id[7].v], [true, 5.0])
	assert_false(by_id[8].accepted, "limit is not writable")
	transport.inject('te","id":9,"variable":"enable","v":true}\n'.to_utf8_buffer())
	_tick()
	assert_true(_of(_sent(), "result")[0].accepted, "message split across reads")
	_tick()
	assert_false(acc.get_value("enable"), "pulse input reset after one step")


func test_reconnect_sends_hello_and_full_image_again() -> void:
	_link()
	_sent()
	transport.close()
	_tick()
	assert_eq(_sent().size(), 0, "nothing sent while unlinked")
	assert_false(link.is_linked())
	link._retry_at_ms = 0  # skip the backoff
	_link()
	var msgs := _sent()
	assert_eq(msgs[0].type, "hello")
	assert_eq(_of(msgs, "image")[0]["values"].size(), 6)


func test_uns_gateway_leaves_opcua_devices_to_the_backplane() -> void:
	var client := MqttClient.new()
	var mqtt := MqttTransport.new()
	var gateway := UnsGateway.new(master, client, _registry(), "test.layout.json", START_UNIX)
	gateway.start("ws://unused")
	assert_eq(gateway.commands.topics(), [], "no command subscriptions for ACC1")
	assert_eq(gateway.telemetry.points.size(), 0, "no direct telemetry for ACC1")
	assert_eq(gateway.events.definitions.size(), 0, "no direct events for ACC1")
	var direct := UnsGateway.new(master, client, _registry(false), "test.layout.json", START_UNIX)
	assert_eq(direct.telemetry.points.size(), 2, "OPC UA path disabled: published directly")
	assert_eq(direct.commands.topics().size(), 2)
	mqtt.close()
