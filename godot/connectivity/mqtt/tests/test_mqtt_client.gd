extends GutTest
## MqttClient against the in-memory loopback transport (no broker needed).

const P := preload("res://connectivity/mqtt/mqtt_packet.gd")

var client: MqttClient
var transport: MqttTransport
var received := []


func before_each() -> void:
	client = MqttClient.new()
	client.client_id = "test"
	transport = MqttTransport.new()
	received.clear()
	client.message_received.connect(func(t: String, p: PackedByteArray) -> void: received.append([t, p]))


func _connect() -> void:
	client.subscribe("vf/cmd/#", 1)
	client.set_will("vf/status", "offline".to_utf8_buffer(), 1, true)
	assert_eq(client.connect_to_broker("ws://broker:9001", transport), OK)
	client.poll()  # opens the transport
	client.poll()  # transport open -> CONNECT
	transport.inject(P.connack_packet(0))
	client.poll()


func _sent_types() -> Array:
	return transport.sent.map(func(b: PackedByteArray) -> int: return b[0] >> 4)


func test_connect_sends_will_and_resubscribes() -> void:
	watch_signals(client)
	_connect()
	assert_true(client.is_broker_connected())
	assert_signal_emitted(client, "connected")
	assert_eq(_sent_types(), [P.Type.CONNECT, P.Type.SUBSCRIBE])
	assert_eq(transport.sent[0][9] & 0x04, 0x04, "will flag set")
	assert_eq(client.connections, 1)


func test_incoming_qos1_publish_is_acknowledged() -> void:
	_connect()
	transport.sent.clear()
	transport.inject(P.publish_packet("vf/cmd/x", "1".to_utf8_buffer(), 1, false, 42).slice(0, 4))
	client.poll()
	assert_eq(received.size(), 0, "fragment only")
	transport.inject(P.publish_packet("vf/cmd/x", "1".to_utf8_buffer(), 1, false, 42).slice(4))
	client.poll()
	assert_eq(received, [["vf/cmd/x", "1".to_utf8_buffer()]])
	assert_eq(transport.sent, [P.puback_packet(42)])


func test_publish_only_when_connected_with_packet_ids() -> void:
	assert_false(client.publish("t", PackedByteArray([1])), "dropped while disconnected")
	_connect()
	transport.sent.clear()
	assert_true(client.publish("t", PackedByteArray([1]), 1, true))
	assert_true(client.publish("t", PackedByteArray([2]), 1))
	var a := P.decode(transport.sent[0])
	var b := P.decode(transport.sent[1])
	assert_true(a.retain)
	assert_ne(a.packet_id, b.packet_id)
	assert_gt(a.packet_id, 0)


func test_lost_connection_reconnects_after_backoff() -> void:
	_connect()
	watch_signals(client)
	transport.close()
	client.poll()
	assert_signal_emitted(client, "disconnected")
	assert_false(client.is_broker_connected())
	assert_eq(client.state, MqttClient.State.WAITING, "waits for the backoff delay")


func test_graceful_disconnect_sends_disconnect() -> void:
	_connect()
	transport.sent.clear()
	client.disconnect_from_broker()
	assert_eq(transport.sent, [P.disconnect_packet()])
	assert_eq(client.state, MqttClient.State.IDLE)
