class_name MqttClient
extends RefCounted
## Small MQTT 3.1.1 client over TCP (mqtt://) or WebSocket (ws://), driven by poll() from the game loop
## (no threads, never blocks the frame).
##
## - Clean session; reconnects with exponential backoff (1 s .. 30 s) and re-subscribes afterwards.
## - Keepalive: PINGREQ after keepalive_s / 2 without traffic; connection dropped if no PINGRESP.
## - QoS 0 and 1. Outgoing QoS 1 gets packet ids, but unacknowledged messages are NOT resent after a
##   reconnect (subscribers get the retained state again; events sent during an outage are lost).
## - Incoming QoS 1 messages are acknowledged with PUBACK. QoS 2 is not supported.
## - A broker outage is reported with one warning; the next one only after a successful connection.
## - Optional user name / password in CONNECT (secure profile); CONNACK 4/5 (bad credentials / not
##   authorised) is reported like an outage and retried with backoff.

signal connected
signal disconnected
signal message_received(topic: String, payload: PackedByteArray)

enum State { IDLE, WAITING, CONNECTING, AWAITING_CONNACK, CONNECTED }

const MIN_BACKOFF_S := 1.0
const MAX_BACKOFF_S := 30.0
const CONNECT_TIMEOUT_MS := 10000

var client_id := "vf-%08x" % (randi() & 0x7FFFFFFF)
var keepalive_s := 30
var broker_url := ""
## Broker account (secure profile, ADR-0027); empty = anonymous.
var username := ""
var password := ""
var state := State.IDLE
## Number of successful connections (reconnects = connections - 1).
var connections := 0
var _will := {}
var _transport: MqttTransport
var _parser := MqttStreamParser.new()
var _subscriptions := {}  # topic filter -> qos
var _next_packet_id := 1
var _backoff_s := MIN_BACKOFF_S
var _retry_at_ms := 0
var _attempt_started_ms := 0
var _last_send_ms := 0
var _ping_sent_ms := -1
var _outage_warned := false


## Sets the last-will message the broker publishes if the connection drops without DISCONNECT.
func set_will(topic: String, payload: PackedByteArray, qos := 0, retain := false) -> void:
	_will = {"topic": topic, "payload": payload, "qos": qos, "retain": retain}


## Starts connecting to `url`. `transport` overrides the one derived from the URL (tests).
func connect_to_broker(url: String, transport: MqttTransport = null) -> Error:
	_transport = transport if transport != null else MqttTransport.for_url(url)
	if _transport == null:
		push_warning("MQTT: unsupported broker URL '%s' (use mqtt:// or ws://)" % url)
		return ERR_INVALID_PARAMETER
	broker_url = url
	state = State.WAITING
	_retry_at_ms = 0
	return OK


func is_broker_connected() -> bool:
	return state == State.CONNECTED


## Adds a subscription (kept across reconnects). Sent immediately when connected.
func subscribe(topic: String, qos := 0) -> void:
	_subscriptions[topic] = qos
	if state == State.CONNECTED:
		_send(MqttPacket.subscribe_packet(_packet_id(), {topic: qos}))


## Publishes a message. Returns false (message dropped) when not connected.
func publish(topic: String, payload: PackedByteArray, qos := 0, retain := false) -> bool:
	if state != State.CONNECTED:
		return false
	var id := _packet_id() if qos > 0 else 0
	return _send(MqttPacket.publish_packet(topic, payload, qos, retain, id))


## Graceful disconnect (no will message); stops reconnecting. Tries briefly to flush queued data.
func disconnect_from_broker() -> void:
	if state == State.CONNECTED:
		_send(MqttPacket.disconnect_packet())
		_transport.flush(200)
	if _transport != null:
		_transport.close()
	var was_connected := state == State.CONNECTED
	state = State.IDLE
	if was_connected:
		disconnected.emit()


## Drives connection handling, reading, keepalive and reconnects. Call once per frame.
func poll() -> void:
	if state == State.IDLE:
		return
	var now := Time.get_ticks_msec()
	if state == State.WAITING:
		if now >= _retry_at_ms:
			_start_attempt(now)
		return
	_transport.poll()
	if _transport.state == MqttTransport.State.CLOSED:
		_connection_lost("connection closed")
		return
	if state == State.CONNECTING and _transport.state == MqttTransport.State.OPEN:
		state = State.AWAITING_CONNACK
		_send(MqttPacket.connect_packet(client_id, keepalive_s, _will, username, password))
	if state != State.CONNECTED and now - _attempt_started_ms > CONNECT_TIMEOUT_MS:
		_connection_lost("connect timeout")
		return
	_read_packets()
	if state == State.CONNECTED:
		_keepalive(now)


func _start_attempt(now: int) -> void:
	_parser.reset()
	_ping_sent_ms = -1
	_attempt_started_ms = now
	if _transport.open(broker_url) != OK:
		_connection_lost("cannot open " + broker_url)
		return
	state = State.CONNECTING


func _read_packets() -> void:
	var data := _transport.receive()
	if data.is_empty():
		return
	_parser.feed(data)
	while state != State.WAITING:
		var packet := _parser.next()
		if _parser.error != "":
			_connection_lost("protocol error: " + _parser.error)
			return
		if packet.is_empty():
			return
		_handle_packet(packet)


func _handle_packet(packet: Dictionary) -> void:
	match packet.type:
		MqttPacket.Type.CONNACK:
			_on_connack(packet.return_code)
		MqttPacket.Type.PUBLISH:
			if packet.qos == 1:
				_send(MqttPacket.puback_packet(packet.packet_id))
			message_received.emit(packet.topic, packet.payload)
		MqttPacket.Type.PINGRESP:
			_ping_sent_ms = -1
		MqttPacket.Type.SUBACK:
			if 0x80 in packet.return_codes:
				push_warning("MQTT: broker refused a subscription (packet %d)" % packet.packet_id)


func _on_connack(return_code: int) -> void:
	if return_code != 0:
		_connection_lost("broker refused connection (CONNACK %d)" % return_code)
		return
	state = State.CONNECTED
	connections += 1
	_backoff_s = MIN_BACKOFF_S
	_outage_warned = false
	print("MQTT: connected to %s as %s" % [broker_url, client_id])
	if not _subscriptions.is_empty():
		_send(MqttPacket.subscribe_packet(_packet_id(), _subscriptions))
	connected.emit()


func _keepalive(now: int) -> void:
	if keepalive_s <= 0:
		return
	if _ping_sent_ms >= 0 and now - _ping_sent_ms > keepalive_s * 1000:
		_connection_lost("no PINGRESP")
	elif _ping_sent_ms < 0 and now - _last_send_ms >= keepalive_s * 500:
		_ping_sent_ms = now
		_send(MqttPacket.pingreq_packet())


func _connection_lost(reason: String) -> void:
	var was_connected := state == State.CONNECTED
	_transport.close()
	state = State.WAITING
	_retry_at_ms = Time.get_ticks_msec() + int(_backoff_s * 1000.0)
	if not _outage_warned:
		_outage_warned = true
		push_warning("MQTT: broker %s unavailable (%s); retrying in the background" % [broker_url, reason])
	_backoff_s = minf(_backoff_s * 2.0, MAX_BACKOFF_S)
	if was_connected:
		disconnected.emit()


func _send(data: PackedByteArray) -> bool:
	_last_send_ms = Time.get_ticks_msec()
	return _transport.send(data)


func _packet_id() -> int:
	var id := _next_packet_id
	_next_packet_id = _next_packet_id % 65535 + 1
	return id
